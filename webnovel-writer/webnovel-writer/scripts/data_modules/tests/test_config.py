#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import importlib
from pathlib import Path

TEST_ROOT = Path(__file__).resolve().parents[2]
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from data_modules import config as config_module
from scripts.data_modules.config import DataModulesConfig, get_config, set_project_root, validate_config


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
    monkeypatch.setattr(config_module, '_get_app_root_env_path', lambda: tmp_path / 'missing.env')

    config_module._load_dotenv()
    assert os.environ.get('WEBNOVEL_RAG_BASE_URL') == 'https://api.siliconflow.cn/v1'
    assert os.environ.get('WEBNOVEL_RAG_API_KEY') == 'sk-test'


def test_load_dotenv_falls_back_to_app_root_env(monkeypatch, tmp_path):
    app_root_env = tmp_path / 'app-root.env'
    app_root_env.write_text('WEBNOVEL_RAG_API_KEY=sk-app-root\n', encoding='utf-8')
    empty_cwd = tmp_path / 'workspace'
    empty_cwd.mkdir()

    monkeypatch.chdir(empty_cwd)
    monkeypatch.delenv('WEBNOVEL_RAG_API_KEY', raising=False)
    monkeypatch.setattr(config_module, '_get_app_root_env_path', lambda: app_root_env)

    config_module._load_dotenv()

    assert os.environ.get('WEBNOVEL_RAG_API_KEY') == 'sk-app-root'


def test_project_dotenv_overrides_non_explicit_runtime_fallbacks(monkeypatch, tmp_path):
    env_path = tmp_path / '.env'
    env_path.write_text(
        'WEBNOVEL_RAG_BASE_URL=http://127.0.0.1:9/v1\nWEBNOVEL_RAG_API_KEY=project-key\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('WEBNOVEL_RAG_BASE_URL', 'https://fallback.invalid/v1')
    monkeypatch.setenv('WEBNOVEL_RAG_API_KEY', 'fallback-key')
    monkeypatch.setattr(config_module, '_INITIAL_ENV_KEYS', frozenset())
    monkeypatch.setattr(config_module, '_get_app_root_env_path', lambda: tmp_path / 'missing.env')

    cfg = DataModulesConfig.from_project_root(tmp_path)

    assert cfg.embed_base_url == 'http://127.0.0.1:9/v1'
    assert cfg.embed_api_key == 'project-key'


def test_project_dotenv_does_not_override_explicit_env(monkeypatch, tmp_path):
    env_path = tmp_path / '.env'
    env_path.write_text(
        'WEBNOVEL_RAG_BASE_URL=http://127.0.0.1:9/v1\nWEBNOVEL_RAG_API_KEY=project-key\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('WEBNOVEL_RAG_BASE_URL', 'https://explicit.invalid/v1')
    monkeypatch.setenv('WEBNOVEL_RAG_API_KEY', 'explicit-key')
    monkeypatch.setattr(
        config_module,
        '_INITIAL_ENV_KEYS',
        frozenset({'WEBNOVEL_RAG_BASE_URL', 'WEBNOVEL_RAG_API_KEY'}),
    )
    monkeypatch.setattr(config_module, '_get_app_root_env_path', lambda: tmp_path / 'missing.env')

    cfg = DataModulesConfig.from_project_root(tmp_path)

    assert cfg.embed_base_url == 'https://explicit.invalid/v1'
    assert cfg.embed_api_key == 'explicit-key'


def test_project_dotenv_supports_utf8_bom(monkeypatch, tmp_path):
    env_path = tmp_path / '.env'
    env_path.write_bytes(
        '\ufeffWEBNOVEL_RAG_BASE_URL=http://127.0.0.1:9/v1\nWEBNOVEL_RAG_API_KEY=project-key\n'.encode('utf-8')
    )
    monkeypatch.delenv('WEBNOVEL_RAG_BASE_URL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_API_KEY', raising=False)
    monkeypatch.setattr(config_module, '_INITIAL_ENV_KEYS', frozenset())
    monkeypatch.setattr(config_module, '_get_app_root_env_path', lambda: tmp_path / 'missing.env')

    cfg = DataModulesConfig.from_project_root(tmp_path)

    assert cfg.embed_base_url == 'http://127.0.0.1:9/v1'
    assert cfg.embed_api_key == 'project-key'


def test_load_runtime_env_switches_project_specific_rag_values(monkeypatch, tmp_path):
    cwd = tmp_path / 'cwd'
    cwd.mkdir()
    project_one = tmp_path / 'project-one'
    project_two = tmp_path / 'project-two'
    project_one.mkdir()
    project_two.mkdir()
    (project_one / '.env').write_text(
        'WEBNOVEL_RAG_BASE_URL=https://one.invalid/v1\nWEBNOVEL_RAG_API_KEY=one-key\n',
        encoding='utf-8',
    )
    (project_two / '.env').write_text(
        'WEBNOVEL_RAG_BASE_URL=https://two.invalid/v1\nWEBNOVEL_RAG_API_KEY=two-key\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(cwd)
    monkeypatch.delenv('WEBNOVEL_RAG_BASE_URL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_API_KEY', raising=False)
    monkeypatch.setattr(config_module, '_INITIAL_ENV_KEYS', frozenset())
    monkeypatch.setattr(config_module, '_get_app_root_env_path', lambda: tmp_path / 'missing.env')

    config_module.load_runtime_env(project_one)
    assert os.environ.get('WEBNOVEL_RAG_BASE_URL') == 'https://one.invalid/v1'
    assert os.environ.get('WEBNOVEL_RAG_API_KEY') == 'one-key'

    config_module.load_runtime_env(project_two)
    assert os.environ.get('WEBNOVEL_RAG_BASE_URL') == 'https://two.invalid/v1'
    assert os.environ.get('WEBNOVEL_RAG_API_KEY') == 'two-key'


def test_load_runtime_env_clears_previous_project_values_when_next_project_omits_them(monkeypatch, tmp_path):
    cwd = tmp_path / 'cwd'
    cwd.mkdir()
    project_one = tmp_path / 'project-one'
    project_two = tmp_path / 'project-two'
    project_one.mkdir()
    project_two.mkdir()
    (project_one / '.env').write_text(
        'WEBNOVEL_RAG_BASE_URL=https://one.invalid/v1\nWEBNOVEL_RAG_API_KEY=one-key\n',
        encoding='utf-8',
    )
    (project_two / '.env').write_text(
        'WEBNOVEL_RAG_API_KEY=two-key\n',
        encoding='utf-8',
    )
    monkeypatch.chdir(cwd)
    monkeypatch.delenv('WEBNOVEL_RAG_BASE_URL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_API_KEY', raising=False)
    monkeypatch.setattr(config_module, '_INITIAL_ENV_KEYS', frozenset())
    monkeypatch.setattr(config_module, '_get_app_root_env_path', lambda: tmp_path / 'missing.env')

    config_module.load_runtime_env(project_one)
    assert os.environ.get('WEBNOVEL_RAG_BASE_URL') == 'https://one.invalid/v1'
    assert os.environ.get('WEBNOVEL_RAG_API_KEY') == 'one-key'

    config_module.load_runtime_env(project_two)

    assert os.environ.get('WEBNOVEL_RAG_API_KEY') == 'two-key'
    assert os.environ.get('WEBNOVEL_RAG_BASE_URL') is None

    cfg = DataModulesConfig.from_project_root(project_two)
    assert cfg.embed_base_url == 'https://api.siliconflow.cn/v1'
    assert cfg.embed_api_key == 'two-key'


def test_legacy_and_canonical_config_imports_share_single_module_instance():
    package_root = Path(__file__).resolve().parents[3]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))

    legacy = importlib.import_module('data_modules.config')
    canonical = importlib.import_module('scripts.data_modules.config')

    assert legacy is canonical


def test_rag_defaults_and_validation(monkeypatch, tmp_path):
    monkeypatch.delenv('WEBNOVEL_RAG_BASE_URL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_API_KEY', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_EMBED_MODEL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_RERANK_MODEL', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_MAX_RETRIES', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_RETRY_INITIAL_DELAY_MS', raising=False)
    monkeypatch.delenv('WEBNOVEL_RAG_RETRY_MAX_DELAY_MS', raising=False)
    monkeypatch.setattr(config_module, '_get_app_root_env_path', lambda: tmp_path / 'missing.env')

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
    monkeypatch.setattr(config_module, '_INITIAL_ENV_KEYS', frozenset({'WEBNOVEL_RAG_API_KEY'}))
    cfg2 = DataModulesConfig.from_project_root(tmp_path)
    assert validate_config(cfg2) is True

