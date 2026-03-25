#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

import pytest

TEST_ROOT = Path(__file__).resolve().parents[2]
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from scripts.data_modules.api_client import EmbeddingAPIClient, ModalAPIClient, RAGRequestError, RerankAPIClient, get_client
from scripts.data_modules.config import DataModulesConfig


class FakeResponse:
    def __init__(self, status, json_data=None, text_data=''):
        self.status = status
        self._text = text_data if text_data else json.dumps(json_data or {}, ensure_ascii=False)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self._text


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.closed = False
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self._responses:
            raise AssertionError('No more responses')
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_embedding_client_retries_retryable_errors(tmp_path, monkeypatch):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.embed_api_key = 'sk-test'
    config.api_max_retries = 2
    config.api_retry_delay = 0
    client = EmbeddingAPIClient(config)

    fake_session = FakeSession([
        FakeResponse(503, text_data='busy'),
        FakeResponse(200, json_data={'data': [{'index': 0, 'embedding': [0.1, 0.2]}]}),
    ])

    async def fake_get_session():
        return fake_session

    monkeypatch.setattr(client, '_get_session', fake_get_session)
    result = await client.embed(['hello'])
    assert result == [[0.1, 0.2]]
    assert fake_session.calls[0][0].endswith('/embeddings')
    assert client.stats.total_calls == 1


@pytest.mark.asyncio
async def test_embedding_client_raises_structured_error_for_auth_failure(tmp_path, monkeypatch):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.embed_api_key = 'sk-test'
    config.api_max_retries = 3
    config.api_retry_delay = 0
    client = EmbeddingAPIClient(config)

    fake_session = FakeSession([FakeResponse(401, text_data='unauthorized')])

    async def fake_get_session():
        return fake_session

    monkeypatch.setattr(client, '_get_session', fake_get_session)
    with pytest.raises(RAGRequestError) as exc_info:
        await client.embed(['hello'])

    error = exc_info.value
    assert error.code == 'RAG_AUTH_FAILED'
    assert error.details['stage'] == 'embedding'
    assert error.details['attempts'] == 1
    assert error.details['retryable'] is False


@pytest.mark.asyncio
async def test_embedding_client_retries_timeout_and_tracks_last_error(tmp_path, monkeypatch):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.embed_api_key = 'sk-test'
    config.api_max_retries = 2
    config.api_retry_delay = 0
    client = EmbeddingAPIClient(config)

    fake_session = FakeSession([asyncio.TimeoutError(), asyncio.TimeoutError()])

    async def fake_get_session():
        return fake_session

    monkeypatch.setattr(client, '_get_session', fake_get_session)
    with pytest.raises(RAGRequestError) as exc_info:
        await client.embed(['hello'])

    assert exc_info.value.code == 'RAG_TIMEOUT'
    assert client.last_error['code'] == 'RAG_TIMEOUT'
    assert client.last_error_at is not None


@pytest.mark.asyncio
async def test_embedding_batch_raises_when_skip_failures_disabled(tmp_path, monkeypatch):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.embed_batch_size = 2
    client = EmbeddingAPIClient(config)

    async def fake_embed(texts):
        if texts == ['c']:
            raise RAGRequestError('RAG_SERVICE_UNAVAILABLE', 'embedding service is unavailable', {'stage': 'embedding'})
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(client, 'embed', fake_embed)

    with pytest.raises(RAGRequestError):
        await client.embed_batch(['a', 'b', 'c'], skip_failures=False)


@pytest.mark.asyncio
async def test_rerank_client_raises_request_invalid_without_retry(tmp_path, monkeypatch):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.rerank_api_key = 'sk-test'
    config.api_max_retries = 4
    config.api_retry_delay = 0
    client = RerankAPIClient(config)

    fake_session = FakeSession([FakeResponse(400, text_data='bad request')])

    async def fake_get_session():
        return fake_session

    monkeypatch.setattr(client, '_get_session', fake_get_session)
    with pytest.raises(RAGRequestError) as exc_info:
        await client.rerank('q', ['doc'])

    assert exc_info.value.code == 'RAG_REQUEST_INVALID'
    assert exc_info.value.details['attempts'] == 1
    assert len(fake_session.calls) == 1


@pytest.mark.asyncio
async def test_rerank_client_uses_siliconflow_url(tmp_path, monkeypatch):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.rerank_api_key = 'sk-test'
    client = RerankAPIClient(config)

    fake_session = FakeSession([FakeResponse(200, json_data={'results': [{'index': 0, 'relevance_score': 0.9}]})])

    async def fake_get_session():
        return fake_session

    monkeypatch.setattr(client, '_get_session', fake_get_session)
    result = await client.rerank('q', ['doc'], top_n=1)
    assert result[0]['index'] == 0
    assert fake_session.calls[0][0].endswith('/rerank')


def test_modal_client_probe_reports_retry_policy(tmp_path, monkeypatch):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.embed_api_key = 'sk-test'
    config.rerank_api_key = 'sk-test'
    client = ModalAPIClient(config)
    monkeypatch.setattr(client, '_check_connection', lambda force=False: None)

    probe = client.probe()
    assert probe['provider'] == 'siliconflow'
    assert probe['configured'] is True
    assert probe['embed_model'] == 'BAAI/bge-m3'
    assert probe['rerank_model'] == 'BAAI/bge-reranker-v2-m3'
    assert probe['retry_policy']['max_retries'] == 6


def test_get_client_reuses_equivalent_config_and_refreshes_on_change(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.embed_api_key = 'sk-test'
    client1 = get_client(cfg)
    client1._embed_client.last_error = {'code': 'RAG_TIMEOUT'}

    cfg_same = DataModulesConfig.from_project_root(tmp_path)
    cfg_same.embed_api_key = 'sk-test'
    client2 = get_client(cfg_same)
    assert client2 is client1
    assert client2._embed_client.last_error == {'code': 'RAG_TIMEOUT'}

    cfg_changed = DataModulesConfig.from_project_root(tmp_path)
    cfg_changed.embed_api_key = 'sk-test'
    cfg_changed.embed_model = 'different-model'
    client3 = get_client(cfg_changed)
    assert client3 is not client1


def test_modal_client_probe_checks_connectivity(tmp_path, monkeypatch):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.embed_api_key = 'sk-test'
    config.rerank_api_key = 'sk-test'
    client = ModalAPIClient(config)

    class SyncResponse:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(self.payload, ensure_ascii=False).encode('utf-8')

    responses = [
        SyncResponse({'data': [{'index': 0, 'embedding': [0.1, 0.2]}]}),
        SyncResponse({'results': [{'index': 0, 'relevance_score': 0.9}]}),
    ]

    monkeypatch.setattr('data_modules.api_client.urlrequest.urlopen', lambda req, timeout=0: responses.pop(0))

    probe = client.probe()

    assert probe['connection_status'] == 'connected'
    assert probe['connection_error'] is None


def test_modal_client_probe_reports_connectivity_failure(tmp_path, monkeypatch):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.embed_api_key = 'sk-test'
    config.rerank_api_key = 'sk-test'
    client = ModalAPIClient(config)

    def fake_urlopen(req, timeout=0):
        raise HTTPError(req.full_url, 503, 'Service Unavailable', hdrs=None, fp=io.BytesIO(b'busy'))

    monkeypatch.setattr('data_modules.api_client.urlrequest.urlopen', fake_urlopen)

    probe = client.probe()

    assert probe['connection_status'] == 'failed'
    assert probe['connection_error']['code'] == 'RAG_SERVICE_UNAVAILABLE'

