#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import sys
from pathlib import Path

import pytest

TEST_ROOT = Path(__file__).resolve().parents[2]
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import data_modules.rag_adapter as rag_module
from data_modules.api_client import RAGRequestError
from data_modules.config import DataModulesConfig
from data_modules.rag_adapter import RAGAdapter


class StubClient:
    async def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]

    async def embed_batch(self, texts, skip_failures=True):
        return [[1.0, 0.0] for _ in texts]

    async def rerank(self, query, documents, top_n=None):
        top_n = top_n or len(documents)
        return [{"index": i, "relevance_score": 1.0 / (i + 1)} for i in range(min(top_n, len(documents)))]


class StubClientEmbedFailure(StubClient):
    async def embed_batch(self, texts, skip_failures=True):
        raise RAGRequestError('RAG_TIMEOUT', 'embedding request timed out', {'stage': 'embedding'})


class StubClientRerankFailure(StubClient):
    async def rerank(self, query, documents, top_n=None):
        raise RAGRequestError('RAG_SERVICE_UNAVAILABLE', 'rerank service is unavailable', {'stage': 'rerank'})


@pytest.fixture
def temp_project(tmp_path, monkeypatch):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    monkeypatch.setattr(rag_module, 'get_client', lambda config: StubClient())
    return cfg


@pytest.mark.asyncio
async def test_store_and_search(temp_project):
    adapter = RAGAdapter(temp_project)
    chunks = [
        {'chapter': 1, 'scene_index': 1, 'content': 'hero trains in the sect'},
        {'chapter': 1, 'scene_index': 2, 'content': 'master teaches alchemy'},
    ]
    stored = await adapter.store_chunks(chunks)
    assert stored == 2

    vec_results = await adapter.vector_search('hero', top_k=2)
    assert len(vec_results) == 2

    bm25_results = adapter.bm25_search('hero', top_k=2)
    assert bm25_results


@pytest.mark.asyncio
async def test_store_chunks_propagates_embedding_failure(tmp_path, monkeypatch):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    monkeypatch.setattr(rag_module, 'get_client', lambda config: StubClientEmbedFailure())

    adapter = RAGAdapter(cfg)
    with pytest.raises(RAGRequestError) as exc_info:
        await adapter.store_chunks([{'chapter': 1, 'scene_index': 1, 'content': 'x'}])

    assert exc_info.value.code == 'RAG_TIMEOUT'


@pytest.mark.asyncio
async def test_hybrid_search_propagates_rerank_failure(tmp_path, monkeypatch):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    monkeypatch.setattr(rag_module, 'get_client', lambda config: StubClientRerankFailure())
    adapter = RAGAdapter(cfg)
    adapter.api_client = StubClientRerankFailure()
    await adapter.store_chunks([{'chapter': 1, 'scene_index': 1, 'content': 'hero trains'}])

    with pytest.raises(RAGRequestError) as exc_info:
        await adapter.hybrid_search('hero', vector_top_k=3, bm25_top_k=3, rerank_top_n=1)

    assert exc_info.value.details['stage'] == 'rerank'


def test_cli_search_reports_rag_error(tmp_path, monkeypatch, capsys):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    monkeypatch.setattr(rag_module, 'get_client', lambda config: StubClient())
    adapter = RAGAdapter(cfg)
    asyncio.run(adapter.store_chunks([{'chapter': 1, 'scene_index': 1, 'content': 'hero trains'}]))

    monkeypatch.setattr(rag_module, 'get_client', lambda config: StubClientRerankFailure())
    monkeypatch.setattr(sys, 'argv', ['rag_adapter', '--project-root', str(tmp_path), 'search', '--query', 'hero', '--mode', 'hybrid', '--top-k', '5'])
    exit_code = rag_module.main()
    captured = capsys.readouterr()
    assert exit_code == 1
    assert 'RAG_SERVICE_UNAVAILABLE' in captured.out
