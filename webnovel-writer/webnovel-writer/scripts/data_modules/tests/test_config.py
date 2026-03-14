#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parents[2]
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from data_modules import config as config_module
from data_modules.config import DataModulesConfig, get_config, set_project_root, validate_config


def test_config_paths_and_defaults(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    assert cfg.project_root == tmp_path
    assert cfg.webnovel_dir.name == '.webnovel'
    assert cfg.state_file.name == 'state.json'
    assert cfg.index_db.name == 'index.db'
    assert cfg.rag_db.name == 'rag.db'
    assert cfg.vector_db.name == 'vectors.db'

    cfg.ensure_dirs()
    assert cfg.webnovel_dir.exists()


def test_get_config_and_set_project_root(tmp_path):
    set_project_root(tmp_path)
    cfg = get_config()
    assert cfg.project_root == tmp_path


def test_load_dotenv_reads_new_rag_variables(monkeypatch, tmp_path):
    env_path = tmp_path / '.env'
    env_path.write_text('WEBNOVEL_RAG_BASE_URL=https://api.siliconflow.cn/v1\nWEBNOVEL_RAG_API_KEY=sk-test\n', encoding='utf-8')

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('WEBNOVEL_RAG_BASE_URL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_API_KEY', raising=False)

    config_module._load_dotenv()
    assert os.environ.get('WEBNOVEL_RAG_BASE_URL') == 'https://api.siliconflow.cn/v1'
    assert os.environ.get('WEBNOVEL_RAG_API_KEY') == 'sk-test'


def test_rag_defaults_and_validation(monkeypatch, tmp_path):
    monkeypatch.delenv('WEBNOVEL_RAG_BASE_URL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_API_KEY', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_EMBED_MODEL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_RERANK_MODEL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_MAX_RETRIES', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_RETRY_INITIAL_DELAY_MS', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_RETRY_MAX_DELAY_MS', raising=False)

    cfg = DataModulesConfig.from_project_root(tmp_path)
    assert cfg.embed_base_url == 'https://api.siliconflow.cn/v1'
    assert cfg.rerank_base_url == 'https://api.siliconflow.cn/v1'
    assert cfg.embed_model == 'BAAI/bge-m3'
    assert cfg.rerank_model == 'BAAI/bge-reranker-v2-m3'
    assert cfg.api_max_retries == 6
    assert cfg.api_retry_delay == 0.5
    assert cfg.api_retry_max_delay_ms == 8000
    assert validate_config(cfg) is False

    monkeypatch.setenv('WEBNOVEL_RAG_API_KEY', 'sk-test')
    cfg2 = DataModulesConfig.from_project_root(tmp_path)
    assert validate_config(cfg2) is True
