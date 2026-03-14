from __future__ import annotations

import json
from pathlib import Path


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = DASHBOARD_ROOT.parent
WORKFLOW_DIR = PACKAGE_ROOT / 'workflow_specs'
APP_PATH = DASHBOARD_ROOT / 'frontend' / 'src' / 'App.jsx'
ENV_EXAMPLE_PATH = PACKAGE_ROOT / '.env.example'
REVIEW_STEP_NAMES = {'consistency-review', 'continuity-review', 'ooc-review'}
EXPECTED_REVIEW_KEYS = ['overall_score', 'pass', 'issues', 'metrics', 'summary']


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def test_review_workflow_matches_write_checker_schema():
    write_workflow = _load_json(WORKFLOW_DIR / 'write.json')
    review_workflow = _load_json(WORKFLOW_DIR / 'review.json')

    write_steps = {step['name']: step for step in write_workflow['steps'] if step['name'] in REVIEW_STEP_NAMES}
    review_steps = {step['name']: step for step in review_workflow['steps'] if step['name'] in REVIEW_STEP_NAMES}

    assert set(write_steps) == REVIEW_STEP_NAMES
    assert set(review_steps) == REVIEW_STEP_NAMES

    for step_name in sorted(REVIEW_STEP_NAMES):
        assert review_steps[step_name]['required_output_keys'] == EXPECTED_REVIEW_KEYS
        assert review_steps[step_name]['required_output_keys'] == write_steps[step_name]['required_output_keys']
        assert review_steps[step_name]['output_schema'].keys() == write_steps[step_name]['output_schema'].keys()


def test_frontend_control_page_wires_rag_status():
    source = APP_PATH.read_text(encoding='utf-8-sig')
    assert "fetchJSON('/api/rag/status').then(setRagStatus).catch(() => setRagStatus(null))" in source
    assert 'label={formatRagStatusLabel(ragStatus)}' in source
    assert '<MetricCard label="RAG"' in source


def test_frontend_exposes_writing_model_status():
    source = APP_PATH.read_text(encoding='utf-8-sig')
    assert 'formatWritingModelPill' in source
    assert 'formatWritingModelDetail' in source
    assert 'Codex CLI' in source
    assert 'API / ${model}' in source
    assert '<MetricCard label="' in source and 'formatWritingModelDetail(llmStatus)' in source


def test_frontend_reads_project_info_from_state_json_shape():
    source = APP_PATH.read_text(encoding='utf-8-sig')
    assert 'const projectMeta = projectInfo?.project_info || projectInfo || {}' in source
    assert 'projectMeta?.project_name' in source
    assert 'projectMeta?.title' in source
    assert 'projectMeta?.genre' in source


def test_frontend_translates_review_gate_block_event():
    source = APP_PATH.read_text(encoding='utf-8-sig')
    assert "'Review gate blocked execution':" in source


def test_frontend_separates_project_bootstrap_from_analysis_init():
    source = APP_PATH.read_text(encoding='utf-8-sig')
    assert "const PROJECT_BOOTSTRAP_TEMPLATE = {" in source
    assert "endpoint: '/api/project/bootstrap'" in source
    assert "fields: ['project_root', 'title', 'genre']" in source
    assert "{ key: 'init'," in source
    assert "fields: ['project_root']" in source


def test_env_example_documents_codex_and_api_writing_models():
    source = ENV_EXAMPLE_PATH.read_text(encoding='utf-8-sig')
    assert 'WEBNOVEL_LLM_PROVIDER=codex-cli' in source
    assert 'WEBNOVEL_CODEX_BIN=codex.cmd' in source
    assert '# WEBNOVEL_LLM_PROVIDER=openai-compatible' in source
    assert '# WEBNOVEL_LLM_MODEL=gpt-5.4' in source
    assert 'WEBNOVEL_RAG_BASE_URL=https://api.siliconflow.cn/v1' in source
