#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path

import pytest


def _ensure_scripts_dir():
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def test_build_chapter_context_payload_includes_disabled_rag_assist(tmp_path):
    _ensure_scripts_dir()

    from extract_chapter_context import build_chapter_context_payload
    from scripts.data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()

    state = {
        'progress': {'current_chapter': 3, 'total_words': 9000},
        'protagonist_state': {'power': {'realm': 'qi', 'layer': 2}, 'location': 'sect', 'golden_finger': {'name': 'system', 'level': 1}},
        'strand_tracker': {'history': [{'chapter': 2, 'dominant': 'quest'}]},
    }
    (cfg.webnovel_dir / 'state.json').write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')

    payload = build_chapter_context_payload(tmp_path, 3)
    assert 'rag_assist' in payload
    assert isinstance(payload['rag_assist'], dict)


def test_load_rag_assist_propagates_rag_error(tmp_path, monkeypatch):
    _ensure_scripts_dir()

    import extract_chapter_context as module

    from scripts.data_modules.api_client import RAGRequestError
    from scripts.data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (cfg.vector_db).write_text('seed', encoding='utf-8')

    monkeypatch.setattr(module, '_build_rag_query', lambda outline, chapter_num, min_chars, max_chars: 'hero relationship query')
    monkeypatch.setattr(module, '_search_with_rag', lambda **kwargs: (_ for _ in ()).throw(RAGRequestError('RAG_TIMEOUT', 'embedding request timed out', {'stage': 'embedding'})))

    with pytest.raises(RAGRequestError):
        module._load_rag_assist(tmp_path, 3, 'outline')


def test_extract_chapter_outline_supports_volume_plan_from_state(tmp_path):
    _ensure_scripts_dir()

    from extract_chapter_context import extract_chapter_outline
    from scripts.data_modules.config import DataModulesConfig

    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    outline_dir = tmp_path / '大纲'
    outline_dir.mkdir(exist_ok=True)
    (outline_dir / 'volume-01-plan.md').write_text(
        '\n'.join(
            [
                '# Volume 1 Plan',
                '',
                '## Chapter Beats',
                '- Chapter 1: 开篇先用异常监控制造第一重疑点。',
                '- Chapter 2: 主角被迫接单，确认规则与代价。',
            ]
        ),
        encoding='utf-8',
    )

    state = {
        'planning': {
            'volume_plans': {
                '1': {
                    'outline_file': '大纲/volume-01-plan.md',
                }
            },
            'latest_volume': '1',
        },
        'progress': {
            'volumes_planned': [{'volume': 1, 'chapters_range': '1-50'}],
        },
    }
    (cfg.webnovel_dir / 'state.json').write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')

    outline = extract_chapter_outline(tmp_path, 1)
    assert 'Chapter 1' in outline
    assert '异常监控' in outline

