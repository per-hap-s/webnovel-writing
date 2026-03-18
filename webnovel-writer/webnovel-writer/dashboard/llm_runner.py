from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union
from urllib import error as urlerror
from urllib import request as urlrequest

from scripts.data_modules.config import load_runtime_env

STEP_ERROR_MESSAGES = {
    "LLM_NOT_CONFIGURED": "请先配置写作模型的 API Key 和模型名称。",
    "LLM_TIMEOUT": "写作模型请求超时。",
    "LLM_CONNECTION_ERROR": "写作模型接口连接失败。",
    "LLM_HTTP_ERROR": "写作模型接口请求失败。",
    "LLM_INVALID_RESPONSE": "写作模型返回的数据格式无效。",
    "LLM_REQUEST_FAILED": "写作模型接口连接失败。",
    "LLM_RESPONSE_INVALID": "写作模型返回的数据格式无效。",
    "INVALID_STEP_OUTPUT": "步骤输出中不包含有效 JSON 对象。",
    "CODEX_CLI_NOT_FOUND": "未找到 Codex CLI 可执行文件。",
    "CODEX_AUTH_REQUIRED": "Codex CLI 尚未登录。",
    "CODEX_TIMEOUT": "Codex 步骤执行超时。",
    "CODEX_EXEC_ERROR": "Codex CLI 调用失败。",
    "CODEX_STEP_FAILED": "Codex 步骤执行失败。",
}


def _ensure_str(data: Union[str, bytes, None]) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


@dataclass
class JsonExtractionResult:
    payload: Optional[Dict[str, Any]]
    stage: str
    recovered: bool
    error: Optional[str] = None
    missing_required_keys: tuple[str, ...] = ()


def _finalize_extraction_result(
    payload: Optional[Dict[str, Any]],
    *,
    stage: str,
    recovered: bool,
    error: Optional[str] = None,
    required_keys: Optional[list[str]] = None,
) -> JsonExtractionResult:
    missing_required_keys: tuple[str, ...] = ()
    if payload is not None and required_keys:
        missing_required_keys = tuple(key for key in required_keys if key not in payload)
    return JsonExtractionResult(
        payload=payload,
        stage=stage,
        recovered=recovered,
        error=error,
        missing_required_keys=missing_required_keys,
    )


def _balanced_json_candidates(raw: str) -> tuple[list[str], bool]:
    candidates: list[str] = []
    start: Optional[int] = None
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(raw):
        if start is None:
            if char == "{":
                start = index
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                candidates.append(raw[start : index + 1])
                start = None

    return candidates, start is not None


def _repair_truncated_json_object(raw: str) -> Optional[str]:
    start: Optional[int] = None
    stack: list[str] = []
    in_string = False
    escape = False

    for index, char in enumerate(raw):
        if start is None:
            if char == "{":
                start = index
                stack = ["}"]
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            stack.append("}")
            continue
        if char == "[":
            stack.append("]")
            continue
        if char in {"}", "]"}:
            if not stack or stack[-1] != char:
                return None
            stack.pop()
            if not stack:
                # The object already closed cleanly; this is not a truncation case.
                return None

    if start is None or not stack:
        return None
    candidate = raw[start:]
    trailing_closers = ""
    if in_string:
        while candidate and candidate[-1] in {"}", "]"} and stack and stack[-1] == candidate[-1]:
            trailing_closers = candidate[-1] + trailing_closers
            stack.pop()
            candidate = candidate[:-1]
    suffix = ""
    if in_string:
        suffix = "\\\"" if escape else "\""
    return candidate + suffix + trailing_closers + "".join(reversed(stack))


def _extract_text_from_content_part(part: Any) -> str:
    if isinstance(part, str):
        return part
    if isinstance(part, dict):
        text_value = part.get("text")
        if isinstance(text_value, str):
            return text_value
        if isinstance(text_value, dict):
            nested_value = text_value.get("value")
            if isinstance(nested_value, str):
                return nested_value
        for key in ("value", "content", "output_text"):
            candidate = part.get(key)
            if isinstance(candidate, str):
                return candidate
    return ""


def _extract_message_content(choice: Dict[str, Any]) -> str:
    message = choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [_extract_text_from_content_part(part) for part in content]
            return "\n".join(part for part in text_parts if part).strip()
    for key in ("output_text", "content", "text"):
        candidate = choice.get(key)
        if isinstance(candidate, str):
            return candidate
    return ""


def extract_json_payload_details(raw: str, required_keys: Optional[list[str]] = None) -> JsonExtractionResult:
    raw = (raw or "").strip()
    if not raw:
        return _finalize_extraction_result(None, stage="empty", recovered=False, error="empty output", required_keys=required_keys)

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return _finalize_extraction_result(parsed, stage="strict_json", recovered=False, required_keys=required_keys)
        return _finalize_extraction_result(
            None,
            stage="json_non_object",
            recovered=False,
            error="top-level JSON value is not an object",
            required_keys=required_keys,
        )
    except json.JSONDecodeError:
        pass

    for fence_match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", raw, flags=re.IGNORECASE):
        fence_body = fence_match.group(1).strip()
        try:
            parsed = json.loads(fence_body)
            if isinstance(parsed, dict):
                return _finalize_extraction_result(parsed, stage="json_fence", recovered=True, required_keys=required_keys)
        except json.JSONDecodeError:
            candidates, _ = _balanced_json_candidates(fence_body)
            for candidate in candidates:
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return _finalize_extraction_result(parsed, stage="json_fence", recovered=True, required_keys=required_keys)

    candidates, truncated = _balanced_json_candidates(raw)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return _finalize_extraction_result(
                parsed,
                stage="balanced_object",
                recovered=(candidate != raw),
                required_keys=required_keys,
            )

    if truncated:
        repaired_candidate = _repair_truncated_json_object(raw)
        if repaired_candidate:
            try:
                parsed = json.loads(repaired_candidate)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return _finalize_extraction_result(
                    parsed,
                    stage="json_truncated_repaired",
                    recovered=True,
                    required_keys=required_keys,
                )
        return _finalize_extraction_result(
            None,
            stage="json_truncated",
            recovered=False,
            error="JSON object appears truncated",
            required_keys=required_keys,
        )
    if "{" in raw:
        return _finalize_extraction_result(
            None,
            stage="json_invalid",
            recovered=False,
            error="JSON object found but could not be parsed",
            required_keys=required_keys,
        )
    return _finalize_extraction_result(
        None,
        stage="no_json",
        recovered=False,
        error="no JSON object found in output",
        required_keys=required_keys,
    )


def extract_json_payload(raw: str) -> Optional[Dict[str, Any]]:
    return extract_json_payload_details(raw).payload


@dataclass
class StepResult:
    step_name: str
    success: bool
    return_code: int
    timing_ms: int
    stdout: str
    stderr: str
    structured_output: Optional[Dict[str, Any]]
    prompt_file: str
    output_file: str
    error: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_name": self.step_name,
            "success": self.success,
            "return_code": self.return_code,
            "timing_ms": self.timing_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "structured_output": self.structured_output,
            "prompt_file": self.prompt_file,
            "output_file": self.output_file,
            "error": self.error,
            "metadata": self.metadata,
        }


class LLMRunner:
    runs_dirname = "llm-runs"

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        load_runtime_env(self.project_root)
        self.timeout_ms = int(os.environ.get("WEBNOVEL_LLM_TIMEOUT_MS", "120000"))
        self.health_ttl_seconds = int(os.environ.get("WEBNOVEL_LLM_HEALTH_TTL_SECONDS", "30"))
        self.health_timeout_seconds = int(os.environ.get("WEBNOVEL_LLM_HEALTH_TIMEOUT_SECONDS", "10"))

    def probe(self) -> Dict[str, Any]:
        raise NotImplementedError

    def run(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        progress_callback: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
    ) -> StepResult:
        run_dir = self._prepare_run_dir(prompt_bundle, step_spec)
        prompt_file = run_dir / "prompt.md"
        bundle_file = run_dir / "prompt-bundle.json"
        output_file = run_dir / "raw-output.txt"
        request_file = run_dir / "request.json"

        prompt_text = self._build_prompt(step_spec, prompt_bundle)
        prompt_file.write_text(prompt_text, encoding="utf-8")
        bundle_file.write_text(json.dumps(prompt_bundle, ensure_ascii=False, indent=2), encoding="utf-8")
        self._write_json_artifact(
            request_file,
            self._build_request_metadata(step_spec, Path(workspace).resolve(), prompt_bundle),
        )

        started_at = time.perf_counter()
        try:
            result = self._execute(
                step_spec,
                Path(workspace).resolve(),
                prompt_bundle,
                prompt_text,
                prompt_file,
                output_file,
                progress_callback,
            )
        except Exception as exc:
            self._write_json_artifact(
                run_dir / "error.json",
                {
                    "success": False,
                    "step_name": str(step_spec.get("name") or ""),
                    "error": {
                        "code": "LLM_RUNNER_EXCEPTION",
                        "message": str(exc),
                    },
                },
            )
            raise
        if result.timing_ms == 0:
            result.timing_ms = int((time.perf_counter() - started_at) * 1000)
        normalized = self._normalize_result(result)
        self._write_outcome_artifacts(run_dir, normalized)
        return normalized

    def _prepare_run_dir(self, prompt_bundle: Dict[str, Any], step_spec: Dict[str, Any]) -> Path:
        runs_root = self.project_root / ".webnovel" / "observability" / self.runs_dirname
        run_dir = runs_root / f"{prompt_bundle['task_id']}-{step_spec['name']}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _build_request_metadata(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
    ) -> Dict[str, Any]:
        timeout_method = getattr(self, "_timeout_seconds_for_step", None)
        timeout_seconds: Optional[int] = None
        if callable(timeout_method):
            try:
                timeout_seconds = int(timeout_method(step_spec.get("name")))
            except Exception:
                timeout_seconds = None
        return {
            "task_id": prompt_bundle.get("task_id"),
            "step_name": str(step_spec.get("name") or ""),
            "workspace": str(workspace),
            "runner": self.__class__.__name__,
            "provider": getattr(self, "provider", None),
            "model": getattr(self, "model", None),
            "base_url": getattr(self, "base_url", None),
            "timeout_seconds": timeout_seconds,
            "context_metrics": prompt_bundle.get("context_metrics"),
            "requested_at": datetime.now(timezone.utc).isoformat(),
        }

    def _write_json_artifact(self, path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def _write_outcome_artifacts(self, run_dir: Path, result: StepResult) -> None:
        result_payload = {
            "success": result.success,
            "step_name": result.step_name,
            "return_code": result.return_code,
            "timing_ms": result.timing_ms,
            "structured_output": result.structured_output,
            "metadata": result.metadata,
            "prompt_file": result.prompt_file,
            "output_file": result.output_file,
        }
        result_file = run_dir / "result.json"
        error_file = run_dir / "error.json"
        if result.success:
            self._write_json_artifact(result_file, result_payload)
            if error_file.exists():
                error_file.unlink()
            return
        self._write_json_artifact(
            error_file,
            result_payload | {"error": result.error, "stderr": result.stderr, "stdout": result.stdout},
        )
        if result_file.exists():
            result_file.unlink()

    def _build_prompt(self, step_spec: Dict[str, Any], prompt_bundle: Dict[str, Any]) -> str:
        payload = json.dumps(prompt_bundle.get("input", {}), ensure_ascii=False, indent=2)
        schema_hint = json.dumps(step_spec.get("output_schema", {}), ensure_ascii=False, indent=2)
        instructions = (step_spec.get("instructions", "") or "").strip()
        step_name = str(step_spec.get("name") or "").strip().lower()
        if step_name == "context":
            instructions = (
                f"{instructions}\n\n"
                "Additional hard requirements for this step:\n"
                "- Return concise JSON only.\n"
                "- `task_brief` and `contract_v2` must stay compact and structured.\n"
                "- `draft_prompt` must be a short plain-text string, not a full document dump.\n"
                "- If line breaks are needed inside `draft_prompt`, encode them as escaped \\n inside the JSON string.\n"
                "- Do not include markdown fences, commentary, or raw multi-line prose outside the JSON object."
            ).strip()
        elif step_name in {"plan", "draft", "polish", "data-sync"}:
            instructions = (
                f"{instructions}\n\n"
                "Additional hard requirements for this step:\n"
                "- Return exactly one complete JSON object and nothing else.\n"
                "- Do not use markdown fences, bullet lists, or explanatory prose outside the JSON object.\n"
                "- Keep string fields concise enough to fit inside a single valid JSON response.\n"
                "- Do not omit required keys, and do not rename contract fields.\n"
                "- Before finishing, check that every string is properly closed and the full object is syntactically valid JSON."
            ).strip()

        reference_docs = prompt_bundle.get("reference_documents", [])
        if reference_docs:
            reference_blocks = []
            for item in reference_docs:
                title = item.get("path", "reference")
                content = item.get("content", "")
                reference_blocks.append(f"## {title}\n```text\n{content}\n```")
            references_block = "\n\n".join(reference_blocks)
        else:
            references_block = "No inline references were provided."

        project_docs = prompt_bundle.get("project_context", [])
        if project_docs:
            project_blocks = []
            for item in project_docs:
                title = item.get("path", "project-context")
                content = item.get("content", "")
                project_blocks.append(f"## {title}\n```text\n{content}\n```")
            project_block = "\n\n".join(project_blocks)
        else:
            project_block = "No project snapshot was provided."

        return (
            "You are the structured workflow engine for Webnovel Writer.\n"
            "Return exactly one JSON object with no prose before or after it.\n\n"
            f"# Task\n{instructions}\n\n"
            f"# Reference Documents\n{references_block}\n\n"
            f"# Project Snapshot\n{project_block}\n\n"
            f"# Input Payload\n```json\n{payload}\n```\n\n"
            f"# Output Contract\nReturn exactly one JSON object matching this shape:\n```json\n{schema_hint}\n```\n"
        )

    def _normalize_result(self, result: StepResult) -> StepResult:
        if not result.error:
            return result

        error = dict(result.error)
        code = str(error.get("code") or "").strip()
        normalized_message = STEP_ERROR_MESSAGES.get(code)
        if normalized_message:
            error["message"] = normalized_message
        result.error = error
        return result

    def _execute(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        prompt_text: str,
        prompt_file: Path,
        output_file: Path,
        progress_callback: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
    ) -> StepResult:
        raise NotImplementedError


class MockRunner(LLMRunner):
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.responses_file = (os.environ.get("WEBNOVEL_MOCK_RESPONSES_FILE") or "").strip()

    def _is_configured(self) -> bool:
        return bool(self.responses_file and Path(self.responses_file).is_file())

    def probe(self) -> Dict[str, Any]:
        configured = self._is_configured()
        return {
            "provider": "mock",
            "mode": "mock",
            "installed": configured,
            "configured": configured,
            "model": "mock-json",
            "base_url": None,
            "binary": None,
            "version": None,
            "connection_status": "connected" if configured else "not_configured",
            "connection_checked_at": datetime.now(timezone.utc).isoformat(),
            "connection_error": None,
        }

    def _load_payloads(self) -> Dict[str, Any]:
        if not self._is_configured():
            return {}
        raw = Path(self.responses_file).read_text(encoding="utf-8-sig")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}

    def _normalize_payload(self, step_spec: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(payload)
        step_name = str(step_spec.get("name") or "")
        if step_name.endswith("-review"):
            score = normalized.get("overall_score", normalized.get("score", 0))
            normalized.setdefault("overall_score", score)
            normalized.setdefault("pass", True)
            normalized.setdefault("issues", [])
            normalized.setdefault("metrics", {})
            normalized.setdefault("summary", "")
        return normalized

    def _execute(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        prompt_text: str,
        prompt_file: Path,
        output_file: Path,
        progress_callback: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
    ) -> StepResult:
        payloads = self._load_payloads()
        if not payloads:
            message = "请设置 WEBNOVEL_MOCK_RESPONSES_FILE 指向有效 JSON 文件。"
            output_file.write_text(message, encoding="utf-8")
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=78,
                timing_ms=0,
                stdout="",
                stderr=message,
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "MOCK_NOT_CONFIGURED", "message": message},
            )

        payload = payloads.get(step_spec["name"])
        if not isinstance(payload, dict):
            message = f"mock responses 缺少步骤输出: {step_spec['name']}"
            output_file.write_text(message, encoding="utf-8")
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=65,
                timing_ms=0,
                stdout="",
                stderr=message,
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "MOCK_STEP_MISSING", "message": message},
            )

        payload = self._normalize_payload(step_spec, payload)
        raw = json.dumps(payload, ensure_ascii=False)
        output_file.write_text(raw, encoding="utf-8")
        return StepResult(
            step_name=step_spec["name"],
            success=True,
            return_code=0,
            timing_ms=0,
            stdout=raw,
            stderr="",
            structured_output=payload,
            prompt_file=str(prompt_file),
            output_file=str(output_file),
        )


class OpenAICompatibleRunner(LLMRunner):
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.provider = os.environ.get("WEBNOVEL_LLM_PROVIDER", "openai-compatible").strip() or "openai-compatible"
        self.model = (os.environ.get("WEBNOVEL_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "").strip()
        self.api_key = (os.environ.get("WEBNOVEL_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
        self.base_url = (
            os.environ.get("WEBNOVEL_LLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.temperature = float(os.environ.get("WEBNOVEL_LLM_TEMPERATURE", "0.1"))
        self.max_request_retries = max(0, int(os.environ.get("WEBNOVEL_LLM_MAX_RETRIES", "2")))
        self.retry_backoff_seconds = max(0.1, float(os.environ.get("WEBNOVEL_LLM_RETRY_BACKOFF_SECONDS", "1.0")))
        self._health_checked_at_epoch = 0.0
        self._connection_status = "not_checked"
        self._connection_checked_at: Optional[str] = None
        self._connection_error: Optional[Dict[str, Any]] = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def _health_cache_valid(self) -> bool:
        return self._health_checked_at_epoch > 0 and (time.time() - self._health_checked_at_epoch) < self.health_ttl_seconds

    def _set_connection_state(self, status: str, error: Optional[Dict[str, Any]] = None) -> None:
        self._connection_status = status
        self._connection_error = error
        self._connection_checked_at = datetime.now(timezone.utc).isoformat()
        self._health_checked_at_epoch = time.time()

    def _check_connection(self, force: bool = False) -> None:
        if not self.is_configured():
            self._set_connection_state("not_configured", None)
            return
        if not force and self._health_cache_valid():
            return

        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "health-check"}],
        }
        req = urlrequest.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urlrequest.urlopen(req, timeout=self.health_timeout_seconds) as response:
                raw_response = response.read().decode("utf-8")
            data = json.loads(raw_response)
            if not isinstance(data.get("choices"), list):
                self._set_connection_state(
                    "failed",
                    {"code": "LLM_RESPONSE_INVALID", "message": "写作模型健康检查返回格式无效。"},
                )
                return
            self._set_connection_state("connected", None)
        except urlerror.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self._set_connection_state(
                "failed",
                {
                    "code": "LLM_HTTP_ERROR",
                    "message": "写作模型健康检查失败。",
                    "original_message": body or str(exc),
                    "status_code": int(exc.code),
                },
            )
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            self._set_connection_state(
                "failed",
                {
                    "code": "LLM_REQUEST_FAILED",
                    "message": "写作模型连接失败。",
                    "original_message": str(exc),
                },
            )
        except json.JSONDecodeError as exc:
            self._set_connection_state(
                "failed",
                {
                    "code": "LLM_RESPONSE_INVALID",
                    "message": "写作模型健康检查返回的 JSON 无法解析。",
                    "original_message": str(exc),
                },
            )

    def probe(self) -> Dict[str, Any]:
        self._check_connection()
        return {
            "provider": self.provider,
            "mode": "api",
            "installed": self.is_configured(),
            "configured": self.is_configured(),
            "model": self.model or None,
            "base_url": self.base_url,
            "binary": None,
            "version": None,
            "connection_status": self._connection_status,
            "connection_checked_at": self._connection_checked_at,
            "connection_error": self._connection_error,
        }

    def _execute(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        prompt_text: str,
        prompt_file: Path,
        output_file: Path,
        progress_callback: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
    ) -> StepResult:
        if not self.is_configured():
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=78,
                timing_ms=0,
                stdout="",
                stderr="LLM API 未配置",
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={
                    "code": "LLM_NOT_CONFIGURED",
                    "message": "请设置 WEBNOVEL_LLM_API_KEY 和 WEBNOVEL_LLM_MODEL。",
                },
            )

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "Return exactly one JSON object. Do not wrap it in markdown fences.",
                },
                {"role": "user", "content": prompt_text},
            ],
        }
        req = urlrequest.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urlrequest.urlopen(req, timeout=max(1, self.timeout_ms // 1000)) as response:
                raw_response = response.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            raw_response = exc.read().decode("utf-8", errors="replace")
            output_file.write_text(raw_response, encoding="utf-8")
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=int(exc.code),
                timing_ms=0,
                stdout="",
                stderr=raw_response,
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "LLM_HTTP_ERROR", "message": raw_response or str(exc)},
            )
        except (urlerror.URLError, TimeoutError) as exc:
            output_file.write_text(str(exc), encoding="utf-8")
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=124,
                timing_ms=0,
                stdout="",
                stderr=str(exc),
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "LLM_REQUEST_FAILED", "message": str(exc)},
            )

        output_file.write_text(raw_response, encoding="utf-8")
        parsed = json.loads(raw_response)
        content = _ensure_str(_extract_message_content(parsed.get("choices", [{}])[0]))
        structured_output = extract_json_payload(content)
        if structured_output is None:
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=65,
                timing_ms=0,
                stdout=content,
                stderr="",
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "INVALID_STEP_OUTPUT", "message": STEP_ERROR_MESSAGES["INVALID_STEP_OUTPUT"]},
            )

        return StepResult(
            step_name=step_spec["name"],
            success=True,
            return_code=0,
            timing_ms=0,
            stdout=content,
            stderr="",
            structured_output=structured_output,
            prompt_file=str(prompt_file),
            output_file=str(output_file),
        )


    def _check_connection(self, force: bool = False) -> None:
        if not self.is_configured():
            self._set_connection_state("not_configured", None)
            return
        if not force and self._health_cache_valid():
            return

        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "health-check"}],
        }
        req = urlrequest.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urlrequest.urlopen(req, timeout=self.health_timeout_seconds) as response:
                raw_response = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw_response)
            if not isinstance(data.get("choices"), list):
                self._set_connection_state(
                    "failed",
                    {"code": "LLM_INVALID_RESPONSE", "message": "写作模型健康检查返回格式无效。"},
                )
                return
            self._set_connection_state("connected", None)
        except urlerror.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self._set_connection_state(
                "failed",
                {
                    "code": "LLM_HTTP_ERROR",
                    "message": "写作模型健康检查失败。",
                    "original_message": body or str(exc),
                    "status_code": int(exc.code),
                },
            )
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            error_code = "LLM_TIMEOUT" if self._is_timeout_error(exc) else "LLM_CONNECTION_ERROR"
            self._set_connection_state(
                "failed",
                {
                    "code": error_code,
                    "message": STEP_ERROR_MESSAGES[error_code],
                    "original_message": str(exc),
                },
            )
        except json.JSONDecodeError as exc:
            self._set_connection_state(
                "failed",
                {
                    "code": "LLM_INVALID_RESPONSE",
                    "message": "写作模型健康检查返回的 JSON 无法解析。",
                    "original_message": str(exc),
                },
            )

    def _execute(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        prompt_text: str,
        prompt_file: Path,
        output_file: Path,
        progress_callback: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
    ) -> StepResult:
        if not self.is_configured():
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=78,
                timing_ms=0,
                stdout="",
                stderr="LLM API not configured",
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={
                    "code": "LLM_NOT_CONFIGURED",
                    "message": STEP_ERROR_MESSAGES["LLM_NOT_CONFIGURED"],
                },
            )

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "Return exactly one JSON object. Do not wrap it in markdown fences.",
                },
                {"role": "user", "content": prompt_text},
            ],
        }
        req = urlrequest.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        step_name = step_spec.get("name")
        timeout_seconds = self._timeout_seconds_for_step(step_name)
        max_attempts = self._max_attempts_for_step(step_name)
        last_result: Optional[StepResult] = None

        for attempt in range(1, max_attempts + 1):
            attempt_output_file = self._attempt_output_file(output_file, attempt)
            metadata: Dict[str, Any] = {
                "attempt": attempt,
                "timeout_seconds": timeout_seconds,
                "retry_count": attempt - 1,
            }
            try:
                if progress_callback:
                    progress_callback("request_dispatched", {"attempt": attempt, "retry_count": attempt - 1})
                    progress_callback("awaiting_model_response", {"attempt": attempt, "retry_count": attempt - 1})
                with urlrequest.urlopen(req, timeout=timeout_seconds) as response:
                    raw_response = response.read().decode("utf-8", errors="replace")
                attempt_output_file.write_text(raw_response, encoding="utf-8")
            except urlerror.HTTPError as exc:
                raw_response = exc.read().decode("utf-8", errors="replace")
                attempt_output_file.write_text(raw_response, encoding="utf-8")
                error_info = self._http_error_info(exc, raw_response, attempt, timeout_seconds)
                self._write_attempt_metadata(attempt_output_file, metadata | error_info)
                last_result = StepResult(
                    step_name=step_spec["name"],
                    success=False,
                    return_code=int(exc.code),
                    timing_ms=0,
                    stdout="",
                    stderr=raw_response,
                    structured_output=None,
                    prompt_file=str(prompt_file),
                    output_file=str(attempt_output_file),
                    error=error_info,
                    metadata=metadata,
                )
                if self._should_retry_error(error_info) and attempt < max_attempts:
                    if progress_callback:
                        progress_callback(
                            "step_retry_scheduled",
                            {
                                "attempt": attempt + 1,
                                "retry_count": attempt,
                                "error_code": error_info.get("code"),
                                "http_status": error_info.get("http_status"),
                            },
                        )
                    self._sleep_before_retry(attempt, step_name)
                    continue
                output_file.write_text(raw_response, encoding="utf-8")
                return last_result
            except (urlerror.URLError, TimeoutError, OSError) as exc:
                raw_error = str(exc)
                attempt_output_file.write_text(raw_error, encoding="utf-8")
                error_info = self._request_error_info(exc, attempt, timeout_seconds)
                self._write_attempt_metadata(attempt_output_file, metadata | error_info)
                last_result = StepResult(
                    step_name=step_spec["name"],
                    success=False,
                    return_code=124 if error_info["code"] == "LLM_TIMEOUT" else 111,
                    timing_ms=0,
                    stdout="",
                    stderr=raw_error,
                    structured_output=None,
                    prompt_file=str(prompt_file),
                    output_file=str(attempt_output_file),
                    error=error_info,
                    metadata=metadata,
                )
                if self._should_retry_error(error_info) and attempt < max_attempts:
                    if progress_callback:
                        progress_callback(
                            "step_retry_scheduled",
                            {
                                "attempt": attempt + 1,
                                "retry_count": attempt,
                                "error_code": error_info.get("code"),
                            },
                        )
                    self._sleep_before_retry(attempt, step_name)
                    continue
                output_file.write_text(raw_error, encoding="utf-8")
                return last_result

            if progress_callback:
                progress_callback("response_received", {"attempt": attempt, "retry_count": attempt - 1})
            try:
                if progress_callback:
                    progress_callback("parsing_output", {"attempt": attempt, "retry_count": attempt - 1})
                parsed = json.loads(raw_response)
            except json.JSONDecodeError as exc:
                error_info = {
                    "code": "LLM_INVALID_RESPONSE",
                    "message": str(exc),
                    "attempt": attempt,
                    "retryable": False,
                    "timeout_seconds": timeout_seconds,
                }
                self._write_attempt_metadata(attempt_output_file, metadata | error_info | {"parse_stage": "raw_response_invalid_json"})
                output_file.write_text(raw_response, encoding="utf-8")
                return StepResult(
                    step_name=step_spec["name"],
                    success=False,
                    return_code=65,
                    timing_ms=0,
                    stdout=raw_response,
                    stderr="",
                    structured_output=None,
                    prompt_file=str(prompt_file),
                    output_file=str(attempt_output_file),
                    error=error_info,
                    metadata=metadata,
                )

            choices = parsed.get("choices")
            if not isinstance(choices, list) or not choices:
                error_info = {
                    "code": "LLM_INVALID_RESPONSE",
                    "message": "response.choices is missing or empty",
                    "attempt": attempt,
                    "retryable": False,
                    "timeout_seconds": timeout_seconds,
                }
                self._write_attempt_metadata(attempt_output_file, metadata | error_info | {"parse_stage": "choices_missing"})
                output_file.write_text(raw_response, encoding="utf-8")
                return StepResult(
                    step_name=step_spec["name"],
                    success=False,
                    return_code=65,
                    timing_ms=0,
                    stdout=raw_response,
                    stderr="",
                    structured_output=None,
                    prompt_file=str(prompt_file),
                    output_file=str(attempt_output_file),
                    error=error_info,
                    metadata=metadata,
                )

            content = _ensure_str(_extract_message_content(choices[0]))
            extraction = extract_json_payload_details(content, required_keys=step_spec.get("required_output_keys"))
            metadata.update(
                {
                    "parse_stage": extraction.stage,
                    "json_extraction_recovered": extraction.recovered,
                    "missing_required_keys": list(extraction.missing_required_keys),
                }
            )
            self._write_attempt_metadata(attempt_output_file, metadata)
            output_file.write_text(raw_response, encoding="utf-8")

            if extraction.payload is None:
                error_info = {
                    "code": "INVALID_STEP_OUTPUT",
                    "message": STEP_ERROR_MESSAGES["INVALID_STEP_OUTPUT"],
                    "attempt": attempt,
                    "retryable": False,
                    "timeout_seconds": timeout_seconds,
                    "parse_stage": extraction.stage,
                    "raw_output_present": bool(content.strip()),
                }
                return StepResult(
                    step_name=step_spec["name"],
                    success=False,
                    return_code=65,
                    timing_ms=0,
                    stdout=content,
                    stderr="",
                    structured_output=None,
                    prompt_file=str(prompt_file),
                    output_file=str(attempt_output_file),
                    error=error_info,
                    metadata=metadata,
                )

            return StepResult(
                step_name=step_spec["name"],
                success=True,
                return_code=0,
                timing_ms=0,
                stdout=content,
                stderr="",
                structured_output=extraction.payload,
                prompt_file=str(prompt_file),
                output_file=str(attempt_output_file),
                metadata=metadata,
            )

        if last_result is not None:
            return last_result
        raise RuntimeError(f"failed to execute step: {step_spec.get('name')}")

    def _timeout_seconds_for_step(self, step_name: Any) -> int:
        base_timeout_seconds = max(1, self.timeout_ms // 1000)
        normalized = str(step_name or "").strip().lower()
        if normalized in {"draft", "polish", "data-sync"}:
            return max(base_timeout_seconds, 240)
        if normalized == "plan":
            return max(base_timeout_seconds, 300)
        if normalized == "context" or "review" in normalized:
            return max(base_timeout_seconds, 150)
        return base_timeout_seconds

    def _max_retries_for_step(self, step_name: Any) -> int:
        normalized = str(step_name or "").strip().lower()
        if normalized == "plan":
            return min(self.max_request_retries, 1)
        return self.max_request_retries

    def _max_attempts_for_step(self, step_name: Any) -> int:
        return self._max_retries_for_step(step_name) + 1

    def _retry_backoff_seconds_for_step(self, step_name: Any) -> float:
        normalized = str(step_name or "").strip().lower()
        if normalized == "plan":
            return max(self.retry_backoff_seconds, 2.0)
        return self.retry_backoff_seconds

    def _attempt_output_file(self, output_file: Path, attempt: int) -> Path:
        if attempt == 1:
            return output_file
        return output_file.with_name(f"{output_file.stem}.attempt-{attempt}{output_file.suffix}")

    def _write_attempt_metadata(self, output_file: Path, payload: Dict[str, Any]) -> None:
        meta_file = output_file.with_name(f"{output_file.stem}.meta.json")
        meta_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _is_timeout_error(self, exc: BaseException) -> bool:
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return True
        if isinstance(exc, urlerror.URLError):
            reason = getattr(exc, "reason", None)
            return isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower()
        return "timed out" in str(exc).lower()

    def _http_error_info(self, exc: urlerror.HTTPError, raw_response: str, attempt: int, timeout_seconds: int) -> Dict[str, Any]:
        status_code = int(exc.code)
        return {
            "code": "LLM_HTTP_ERROR",
            "message": raw_response or str(exc),
            "attempt": attempt,
            "retryable": 500 <= status_code < 600,
            "http_status": status_code,
            "timeout_seconds": timeout_seconds,
        }

    def _request_error_info(self, exc: BaseException, attempt: int, timeout_seconds: int) -> Dict[str, Any]:
        error_code = "LLM_TIMEOUT" if self._is_timeout_error(exc) else "LLM_CONNECTION_ERROR"
        return {
            "code": error_code,
            "message": str(exc),
            "attempt": attempt,
            "retryable": True,
            "timeout_seconds": timeout_seconds,
        }

    def _should_retry_error(self, error: Dict[str, Any]) -> bool:
        if not bool(error.get("retryable")):
            return False
        code = str(error.get("code") or "")
        if code in {"LLM_TIMEOUT", "LLM_CONNECTION_ERROR"}:
            return True
        if code == "LLM_HTTP_ERROR":
            status_code = int(error.get("http_status") or 0)
            return 500 <= status_code < 600
        return False

    def _sleep_before_retry(self, attempt: int, step_name: Any) -> None:
        time.sleep(self._retry_backoff_seconds_for_step(step_name) * (2 ** max(0, attempt - 1)))


class CodexCliRunner(LLMRunner):
    runs_dirname = "codex-runs"

    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.binary = self._discover_binary()[0]

    def _binary_candidates(self) -> list[str]:
        explicit = (os.environ.get("WEBNOVEL_CODEX_BIN") or "").strip()
        if explicit:
            return [explicit]
        if os.name == "nt":
            return ["codex.cmd", "codex.exe", "codex"]
        return ["codex"]

    def _discover_binary(self) -> tuple[str, Optional[str]]:
        candidates = self._binary_candidates()
        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return candidate, resolved
        return candidates[0], None

    def probe(self) -> Dict[str, Any]:
        binary, resolved_binary = self._discover_binary()
        self.binary = binary
        exists = resolved_binary is not None
        version = None
        if exists:
            try:
                completed = subprocess.run(
                    [resolved_binary, "--version"],
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    check=False,
                )
                version = (completed.stdout or completed.stderr).strip() or None
            except OSError:
                exists = False
                resolved_binary = None
        return {
            "provider": "codex-cli",
            "mode": "cli",
            "binary": binary,
            "resolved_binary": resolved_binary,
            "installed": exists,
            "configured": exists,
            "version": version,
            "model": None,
            "base_url": None,
            "connection_status": "connected" if exists else "failed",
            "connection_checked_at": datetime.now(timezone.utc).isoformat(),
            "connection_error": None if exists else {
                "code": "CODEX_CLI_NOT_FOUND",
                "message": "未找到 Codex CLI 可执行文件。",
                "original_message": f"Missing CLI executable: {binary}",
            },
        }

    def _timeout_seconds_for_step(self, step_name: Any) -> int:
        return max(1, self.timeout_ms // 1000)

    def _base_metadata(self, step_name: Any) -> Dict[str, Any]:
        return {
            "attempt": 1,
            "timeout_seconds": self._timeout_seconds_for_step(step_name),
            "retry_count": 0,
        }

    def _parse_structured_output(self, step_spec: Dict[str, Any], content: str) -> tuple[JsonExtractionResult, Dict[str, Any]]:
        extraction = extract_json_payload_details(content, required_keys=step_spec.get("required_output_keys"))
        metadata = {
            "parse_stage": extraction.stage,
            "json_extraction_recovered": extraction.recovered,
            "missing_required_keys": list(extraction.missing_required_keys),
        }
        return extraction, metadata

    def _execute(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        prompt_text: str,
        prompt_file: Path,
        output_file: Path,
        progress_callback: Optional[Callable[[str, Optional[Dict[str, Any]]], None]] = None,
    ) -> StepResult:
        binary, resolved_binary = self._discover_binary()
        self.binary = binary
        base_metadata = self._base_metadata(step_spec.get("name"))
        if resolved_binary is None:
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=127,
                timing_ms=0,
                stdout="",
                stderr="Codex CLI not found",
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "CODEX_CLI_NOT_FOUND", "message": STEP_ERROR_MESSAGES["CODEX_CLI_NOT_FOUND"]},
                metadata=base_metadata | {
                    "parse_stage": "not_started",
                    "json_extraction_recovered": False,
                    "missing_required_keys": [],
                },
            )

        last_message_file = output_file.with_name("assistant-last-message.txt")
        try:
            completed = subprocess.run(
                [resolved_binary, "exec", "-o", str(last_message_file), "-"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                encoding="utf-8",
                input=prompt_text,
                timeout=max(1, self.timeout_ms // 1000),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial_stdout = _ensure_str(exc.stdout)
            partial_stderr = _ensure_str(exc.stderr)
            output_file.write_text(partial_stdout + "\n" + partial_stderr, encoding="utf-8")
            assistant_message = ""
            if last_message_file.exists():
                assistant_message = last_message_file.read_text(encoding="utf-8")
            content = assistant_message or partial_stdout
            extraction, parse_metadata = self._parse_structured_output(step_spec, content)
            metadata = base_metadata | parse_metadata
            if extraction.payload is not None:
                return StepResult(
                    step_name=step_spec["name"],
                    success=True,
                    return_code=0,
                    timing_ms=0,
                    stdout=content,
                    stderr=partial_stderr,
                    structured_output=extraction.payload,
                    prompt_file=str(prompt_file),
                    output_file=str(output_file),
                    metadata=metadata,
                )
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=124,
                timing_ms=0,
                stdout=partial_stdout,
                stderr=partial_stderr,
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={
                    "code": "CODEX_TIMEOUT",
                    "message": STEP_ERROR_MESSAGES["CODEX_TIMEOUT"],
                    "attempt": 1,
                    "retryable": False,
                    "timeout_seconds": metadata["timeout_seconds"],
                    "parse_stage": parse_metadata["parse_stage"],
                    "raw_output_present": bool(content.strip()),
                },
                metadata=metadata,
            )
        except OSError as exc:
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=126,
                timing_ms=0,
                stdout="",
                stderr=str(exc),
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "CODEX_EXEC_ERROR", "message": str(exc)},
                metadata=base_metadata | {
                    "parse_stage": "not_started",
                    "json_extraction_recovered": False,
                    "missing_required_keys": [],
                },
            )

        stdout = _ensure_str(completed.stdout)
        stderr = _ensure_str(completed.stderr)
        output_file.write_text(stdout + ("\n" if stdout and stderr else "") + stderr, encoding="utf-8")

        assistant_message = ""
        if last_message_file.exists():
            assistant_message = last_message_file.read_text(encoding="utf-8")
        content = assistant_message or stdout
        extraction, parse_metadata = self._parse_structured_output(step_spec, content)
        metadata = base_metadata | parse_metadata
        error = None
        success = completed.returncode == 0
        if not success:
            error = self._map_error(stderr or stdout)
        elif extraction.payload is None:
            success = False
            error = {
                "code": "INVALID_STEP_OUTPUT",
                "message": STEP_ERROR_MESSAGES["INVALID_STEP_OUTPUT"],
                "attempt": 1,
                "retryable": False,
                "timeout_seconds": metadata["timeout_seconds"],
                "parse_stage": parse_metadata["parse_stage"],
                "raw_output_present": bool(content.strip()),
            }

        return StepResult(
            step_name=step_spec["name"],
            success=success,
            return_code=int(completed.returncode),
            timing_ms=0,
            stdout=content,
            stderr=stderr,
            structured_output=extraction.payload,
            prompt_file=str(prompt_file),
            output_file=str(output_file),
            error=error,
            metadata=metadata,
        )

    def _map_error(self, raw: str) -> Dict[str, str]:
        text = (raw or "").lower()
        if "login" in text or "auth" in text:
            return {"code": "CODEX_AUTH_REQUIRED", "message": raw.strip() or "需要先登录 Codex"}
        if "not found" in text:
            return {"code": "CODEX_CLI_NOT_FOUND", "message": raw.strip() or "未找到 Codex CLI"}
        return {"code": "CODEX_STEP_FAILED", "message": raw.strip() or "Codex 步骤执行失败"}


def create_default_runner(project_root: Path) -> LLMRunner:
    load_runtime_env(project_root)
    provider = (os.environ.get("WEBNOVEL_LLM_PROVIDER") or "openai-compatible").strip().lower()
    api_runner = OpenAICompatibleRunner(project_root)
    if provider == "mock":
        return MockRunner(project_root)
    if provider in {"codex", "codex-cli", "cli"}:
        return CodexCliRunner(project_root)
    if api_runner.is_configured():
        return api_runner
    cli_runner = CodexCliRunner(project_root)
    if cli_runner.probe().get("installed"):
        return cli_runner
    return api_runner
