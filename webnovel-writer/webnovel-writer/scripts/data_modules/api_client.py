#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Modules - RAG API client.

This module is intentionally narrowed to the current production path:
- SiliconFlow hosted embeddings
- SiliconFlow hosted rerank
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

import aiohttp

from .config import get_config


@dataclass
class APIStats:
    total_calls: int = 0
    total_time: float = 0.0
    errors: int = 0


@dataclass
class RAGRequestError(Exception):
    code: str
    message: str
    details: Dict[str, Any]

    def __str__(self) -> str:
        return self.message

    def to_error_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": dict(self.details),
        }


def _sanitize_error_message(text: str, max_length: int = 160) -> str:
    if not text:
        return "(empty response)"

    sanitized = text
    sensitive_patterns = [
        (r'api[_-]?key["\s:=]+[^,}\s"]+', 'api_key=***'),
        (r'token["\s:=]+[^,}\s"]+', 'token=***'),
        (r'password["\s:=]+[^,}\s"]+', 'password=***'),
        (r'secret["\s:=]+[^,}\s"]+', 'secret=***'),
        (r'authorization["\s:=]+[^,}\s"]+', 'authorization=***'),
        (r'Bearer\s+\S+', 'Bearer ***'),
    ]
    for pattern, replacement in sensitive_patterns:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

    return sanitized[:max_length] + ("..." if len(sanitized) > max_length else "")


class _BaseRAGAPIClient:
    stage_name = "unknown"

    def __init__(self, config=None):
        self.config = config or get_config()
        self.stats = APIStats()
        self._warmed_up = False
        self._session: Optional[aiohttp.ClientSession] = None
        self.last_error: Optional[Dict[str, Any]] = None
        self.last_error_at: Optional[str] = None

    @property
    def provider(self) -> str:
        return "siliconflow"

    @property
    def max_retries(self) -> int:
        return max(1, int(getattr(self.config, "api_max_retries", 6) or 6))

    @property
    def initial_delay(self) -> float:
        return max(0.0, float(getattr(self.config, "api_retry_delay", 0.5) or 0.5))

    @property
    def max_delay(self) -> float:
        return max(self.initial_delay, int(getattr(self.config, "api_retry_max_delay_ms", 8000) or 8000) / 1000.0)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(limit=200, limit_per_host=100)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def _retry_delay_for_attempt(self, attempt_index: int) -> float:
        return min(self.initial_delay * (2 ** attempt_index), self.max_delay)

    def _record_success(self) -> None:
        self.last_error = None
        self.last_error_at = None
        self._warmed_up = True

    def _record_failure(self, error: RAGRequestError) -> None:
        self.stats.errors += 1
        self.last_error = error.to_error_dict()
        self.last_error_at = datetime.now(timezone.utc).isoformat()

    def _timeout_seconds(self) -> int:
        if not self._warmed_up:
            return int(getattr(self.config, "cold_start_timeout", 300) or 300)
        return int(getattr(self.config, "normal_timeout", 180) or 180)

    def _build_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _make_error(
        self,
        *,
        code: str,
        message: str,
        status_code: Optional[int],
        retryable: bool,
        attempts: int,
        last_error: str,
    ) -> RAGRequestError:
        return RAGRequestError(
            code=code,
            message=message,
            details={
                "provider": self.provider,
                "stage": self.stage_name,
                "model": self.model_name,
                "status_code": status_code,
                "retryable": retryable,
                "attempts": attempts,
                "last_error": _sanitize_error_message(last_error),
            },
        )

    def _map_status_error(self, status: int, body: str, attempts: int) -> RAGRequestError:
        retryable = status in {408, 429, 500, 502, 503, 504}
        if status in {401, 403}:
            return self._make_error(
                code="RAG_AUTH_FAILED",
                message=f"{self.stage_name} authentication failed",
                status_code=status,
                retryable=False,
                attempts=attempts,
                last_error=body,
            )
        if status == 429:
            return self._make_error(
                code="RAG_RATE_LIMITED",
                message=f"{self.stage_name} request was rate limited",
                status_code=status,
                retryable=True,
                attempts=attempts,
                last_error=body,
            )
        if status == 408:
            return self._make_error(
                code="RAG_TIMEOUT",
                message=f"{self.stage_name} request timed out",
                status_code=status,
                retryable=True,
                attempts=attempts,
                last_error=body,
            )
        if status in {400, 404, 422}:
            return self._make_error(
                code="RAG_REQUEST_INVALID",
                message=f"{self.stage_name} request was rejected",
                status_code=status,
                retryable=False,
                attempts=attempts,
                last_error=body,
            )
        if status >= 500:
            return self._make_error(
                code="RAG_SERVICE_UNAVAILABLE",
                message=f"{self.stage_name} service is unavailable",
                status_code=status,
                retryable=True,
                attempts=attempts,
                last_error=body,
            )
        return self._make_error(
            code="RAG_REQUEST_INVALID",
            message=f"{self.stage_name} request failed",
            status_code=status,
            retryable=retryable,
            attempts=attempts,
            last_error=body,
        )

    async def _request_json(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        started_at = time.time()
        session = await self._get_session()
        last_error: Optional[RAGRequestError] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                async with session.post(
                    self.url,
                    json=payload,
                    headers=self._build_headers(),
                    timeout=aiohttp.ClientTimeout(total=self._timeout_seconds()),
                ) as resp:
                    body = await resp.text()
                    if resp.status == 200:
                        try:
                            data = json.loads(body)
                        except json.JSONDecodeError as exc:
                            last_error = self._make_error(
                                code="RAG_RESPONSE_INVALID",
                                message=f"{self.stage_name} returned invalid JSON",
                                status_code=resp.status,
                                retryable=False,
                                attempts=attempt,
                                last_error=str(exc),
                            )
                            break
                        self.stats.total_calls += 1
                        self.stats.total_time += time.time() - started_at
                        self._record_success()
                        return data

                    last_error = self._map_status_error(resp.status, body, attempt)
                    if last_error.details.get("retryable") and attempt < self.max_retries:
                        await asyncio.sleep(self._retry_delay_for_attempt(attempt - 1))
                        continue
                    break
            except asyncio.TimeoutError:
                last_error = self._make_error(
                    code="RAG_TIMEOUT",
                    message=f"{self.stage_name} request timed out",
                    status_code=None,
                    retryable=True,
                    attempts=attempt,
                    last_error=f"timeout after {self._timeout_seconds()}s",
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self._retry_delay_for_attempt(attempt - 1))
                    continue
                break
            except (aiohttp.ClientError, OSError) as exc:
                last_error = self._make_error(
                    code="RAG_SERVICE_UNAVAILABLE",
                    message=f"{self.stage_name} service is unavailable",
                    status_code=None,
                    retryable=True,
                    attempts=attempt,
                    last_error=str(exc),
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(self._retry_delay_for_attempt(attempt - 1))
                    continue
                break
            except Exception as exc:
                last_error = self._make_error(
                    code="RAG_RESPONSE_INVALID",
                    message=f"{self.stage_name} request failed unexpectedly",
                    status_code=None,
                    retryable=False,
                    attempts=attempt,
                    last_error=str(exc),
                )
                break

        if last_error is None:
            last_error = self._make_error(
                code="RAG_SERVICE_UNAVAILABLE",
                message=f"{self.stage_name} service is unavailable",
                status_code=None,
                retryable=False,
                attempts=self.max_retries,
                last_error="request failed without a captured error",
            )
        self._record_failure(last_error)
        raise last_error


class EmbeddingAPIClient(_BaseRAGAPIClient):
    stage_name = "embedding"

    @property
    def api_key(self) -> str:
        return str(self.config.embed_api_key or "").strip()

    @property
    def model_name(self) -> str:
        return str(self.config.embed_model or "").strip()

    @property
    def url(self) -> str:
        return self.config.embed_base_url.rstrip("/") + "/embeddings"

    async def embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        if not texts:
            return []
        payload = {
            "model": self.model_name,
            "input": texts,
            "encoding_format": "float",
        }
        data = await self._request_json(payload)
        raw_items = data.get("data")
        if not isinstance(raw_items, list):
            error = self._make_error(
                code="RAG_RESPONSE_INVALID",
                message="embedding response is missing data[]",
                status_code=200,
                retryable=False,
                attempts=1,
                last_error=json.dumps(data, ensure_ascii=False),
            )
            self._record_failure(error)
            raise error
        try:
            sorted_items = sorted(raw_items, key=lambda item: int(item.get("index", 0)))
            return [list(item["embedding"]) for item in sorted_items]
        except Exception as exc:
            error = self._make_error(
                code="RAG_RESPONSE_INVALID",
                message="embedding response shape is invalid",
                status_code=200,
                retryable=False,
                attempts=1,
                last_error=str(exc),
            )
            self._record_failure(error)
            raise error

    async def embed_batch(self, texts: List[str], *, skip_failures: bool = True) -> List[Optional[List[float]]]:
        if not texts:
            return []

        all_embeddings: List[Optional[List[float]]] = []
        batch_size = int(self.config.embed_batch_size or 64)
        batches = [texts[i:i + batch_size] for i in range(0, len(texts), batch_size)]
        results = await asyncio.gather(*(self.embed(batch) for batch in batches), return_exceptions=True)

        for batch, result in zip(batches, results):
            if isinstance(result, Exception):
                if skip_failures:
                    all_embeddings.extend([None] * len(batch))
                    continue
                raise result
            if result and len(result) == len(batch):
                all_embeddings.extend(result)
                continue
            if skip_failures:
                all_embeddings.extend([None] * len(batch))
            else:
                raise self._make_error(
                    code="RAG_RESPONSE_INVALID",
                    message="embedding batch response length mismatch",
                    status_code=200,
                    retryable=False,
                    attempts=1,
                    last_error=f"expected {len(batch)} items, got {len(result or [])}",
                )
        return all_embeddings[: len(texts)]

    async def warmup(self):
        await self.embed(["test"])


class RerankAPIClient(_BaseRAGAPIClient):
    stage_name = "rerank"

    @property
    def api_key(self) -> str:
        return str(self.config.rerank_api_key or "").strip()

    @property
    def model_name(self) -> str:
        return str(self.config.rerank_model or "").strip()

    @property
    def url(self) -> str:
        return self.config.rerank_base_url.rstrip("/") + "/rerank"

    async def rerank(self, query: str, documents: List[str], top_n: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        if not documents:
            return []
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "query": query,
            "documents": documents,
        }
        if top_n:
            payload["top_n"] = top_n
        data = await self._request_json(payload)
        raw_results = data.get("results")
        if not isinstance(raw_results, list):
            error = self._make_error(
                code="RAG_RESPONSE_INVALID",
                message="rerank response is missing results[]",
                status_code=200,
                retryable=False,
                attempts=1,
                last_error=json.dumps(data, ensure_ascii=False),
            )
            self._record_failure(error)
            raise error
        return raw_results

    async def warmup(self):
        await self.rerank("test", ["doc1", "doc2"], top_n=1)


class SiliconFlowRAGClient:
    def __init__(self, config=None):
        self.config = config or get_config()
        self._embed_client = EmbeddingAPIClient(self.config)
        self._rerank_client = RerankAPIClient(self.config)
        self.sem_embed = asyncio.Semaphore(int(self.config.embed_concurrency or 64))
        self.sem_rerank = asyncio.Semaphore(int(self.config.rerank_concurrency or 32))
        self.health_ttl_seconds = int(os.environ.get("WEBNOVEL_RAG_HEALTH_TTL_SECONDS", "30"))
        self.health_timeout_seconds = int(os.environ.get("WEBNOVEL_RAG_HEALTH_TIMEOUT_SECONDS", "10"))
        self._connection_status = "not_checked"
        self._connection_checked_at: Optional[str] = None
        self._connection_error: Optional[Dict[str, Any]] = None
        self._health_checked_at_mono = 0.0

    @property
    def stats(self) -> Dict[str, APIStats]:
        return {
            "embed": self._embed_client.stats,
            "rerank": self._rerank_client.stats,
        }

    async def close(self):
        await self._embed_client.close()
        await self._rerank_client.close()

    async def warmup(self):
        await asyncio.gather(self._embed_client.warmup(), self._rerank_client.warmup())

    async def embed(self, texts: List[str]) -> Optional[List[List[float]]]:
        return await self._embed_client.embed(texts)

    async def embed_batch(self, texts: List[str], *, skip_failures: bool = True) -> List[Optional[List[float]]]:
        return await self._embed_client.embed_batch(texts, skip_failures=skip_failures)

    async def rerank(self, query: str, documents: List[str], top_n: Optional[int] = None) -> Optional[List[Dict[str, Any]]]:
        return await self._rerank_client.rerank(query, documents, top_n)

    def _health_cache_valid(self) -> bool:
        return self._health_checked_at_mono > 0 and (time.monotonic() - self._health_checked_at_mono) < self.health_ttl_seconds

    def _set_connection_state(self, status: str, error: Optional[Dict[str, Any]] = None) -> None:
        self._connection_status = status
        self._connection_error = error
        self._connection_checked_at = datetime.now(timezone.utc).isoformat()
        self._health_checked_at_mono = time.monotonic()

    def _sync_request_json(self, client: _BaseRAGAPIClient, payload: Dict[str, Any]) -> Dict[str, Any]:
        request = urlrequest.Request(
            client.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=client._build_headers(),
            method="POST",
        )
        try:
            with urlrequest.urlopen(request, timeout=self.health_timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urlerror.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            error = client._map_status_error(int(exc.code), body, 1)
            client._record_failure(error)
            raise error
        except TimeoutError:
            error = client._make_error(
                code="RAG_TIMEOUT",
                message=f"{client.stage_name} request timed out",
                status_code=None,
                retryable=True,
                attempts=1,
                last_error=f"timeout after {self.health_timeout_seconds}s",
            )
            client._record_failure(error)
            raise error
        except (urlerror.URLError, OSError) as exc:
            error = client._make_error(
                code="RAG_SERVICE_UNAVAILABLE",
                message=f"{client.stage_name} service is unavailable",
                status_code=None,
                retryable=True,
                attempts=1,
                last_error=str(exc),
            )
            client._record_failure(error)
            raise error

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            error = client._make_error(
                code="RAG_RESPONSE_INVALID",
                message=f"{client.stage_name} returned invalid JSON",
                status_code=200,
                retryable=False,
                attempts=1,
                last_error=str(exc),
            )
            client._record_failure(error)
            raise error

        client.stats.total_calls += 1
        client._record_success()
        return data

    def _check_connection(self, force: bool = False) -> None:
        configured = bool(self.config.embed_api_key and self.config.rerank_api_key and self.config.embed_model and self.config.rerank_model)
        if not configured:
            self._set_connection_state("not_configured", None)
            return
        if not force and self._health_cache_valid():
            return

        try:
            embed_data = self._sync_request_json(
                self._embed_client,
                {"model": self.config.embed_model, "input": ["health-check"], "encoding_format": "float"},
            )
            if not isinstance(embed_data.get("data"), list):
                error = self._embed_client._make_error(
                    code="RAG_RESPONSE_INVALID",
                    message="embedding response is missing data[]",
                    status_code=200,
                    retryable=False,
                    attempts=1,
                    last_error=json.dumps(embed_data, ensure_ascii=False),
                )
                self._embed_client._record_failure(error)
                raise error

            rerank_data = self._sync_request_json(
                self._rerank_client,
                {"model": self.config.rerank_model, "query": "health-check", "documents": ["health-check"], "top_n": 1},
            )
            if not isinstance(rerank_data.get("results"), list):
                error = self._rerank_client._make_error(
                    code="RAG_RESPONSE_INVALID",
                    message="rerank response is missing results[]",
                    status_code=200,
                    retryable=False,
                    attempts=1,
                    last_error=json.dumps(rerank_data, ensure_ascii=False),
                )
                self._rerank_client._record_failure(error)
                raise error

            self._set_connection_state("connected", None)
        except RAGRequestError as exc:
            self._set_connection_state("failed", exc.to_error_dict())

    def probe(self) -> Dict[str, Any]:
        configured = bool(self.config.embed_api_key and self.config.rerank_api_key and self.config.embed_model and self.config.rerank_model)
        self._check_connection()
        latest_error = self._embed_client.last_error or self._rerank_client.last_error
        latest_error_at = self._embed_client.last_error_at or self._rerank_client.last_error_at
        if self._embed_client.last_error_at and self._rerank_client.last_error_at:
            if self._rerank_client.last_error_at > self._embed_client.last_error_at:
                latest_error = self._rerank_client.last_error
                latest_error_at = self._rerank_client.last_error_at
        return {
            "provider": "siliconflow",
            "configured": configured,
            "base_url": self.config.embed_base_url,
            "embed_model": self.config.embed_model,
            "rerank_model": self.config.rerank_model,
            "retry_policy": {
                "max_retries": self._embed_client.max_retries,
                "initial_delay_ms": int(self._embed_client.initial_delay * 1000),
                "max_delay_ms": int(self._embed_client.max_delay * 1000),
            },
            "last_error": latest_error,
            "last_error_at": latest_error_at,
            "connection_status": self._connection_status,
            "connection_checked_at": self._connection_checked_at,
            "connection_error": self._connection_error,
        }

    def print_stats(self):
        print("\n[API STATS]")
        for name, stats in self.stats.items():
            if stats.total_calls <= 0:
                continue
            avg_time = stats.total_time / stats.total_calls
            print(f"  {name.upper()}: {stats.total_calls} calls, {stats.total_time:.1f}s total, {avg_time:.2f}s avg, {stats.errors} errors")


ModalAPIClient = SiliconFlowRAGClient

_client: Optional[SiliconFlowRAGClient] = None


def _client_matches_config(client: SiliconFlowRAGClient, config) -> bool:
    existing = client.config
    return all(
        [
            str(getattr(existing, "project_root", "")) == str(getattr(config, "project_root", "")),
            str(existing.embed_base_url) == str(config.embed_base_url),
            str(existing.embed_model) == str(config.embed_model),
            str(existing.embed_api_key) == str(config.embed_api_key),
            str(existing.rerank_base_url) == str(config.rerank_base_url),
            str(existing.rerank_model) == str(config.rerank_model),
            str(existing.rerank_api_key) == str(config.rerank_api_key),
            int(existing.api_max_retries) == int(config.api_max_retries),
            float(existing.api_retry_delay) == float(config.api_retry_delay),
            int(existing.api_retry_max_delay_ms) == int(config.api_retry_max_delay_ms),
        ]
    )


def get_client(config=None) -> SiliconFlowRAGClient:
    global _client
    if _client is None:
        _client = SiliconFlowRAGClient(config)
        return _client

    if config is not None and not _client_matches_config(_client, config):
        _client = SiliconFlowRAGClient(config)
    return _client
