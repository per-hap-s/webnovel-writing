from __future__ import annotations

import json
from pathlib import Path


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = DASHBOARD_ROOT.parent
WORKFLOW_DIR = PACKAGE_ROOT / 'workflow_specs'
APP_PATH = DASHBOARD_ROOT / 'frontend' / 'src' / 'App.jsx'
CONTROL_PAGE_PATH = DASHBOARD_ROOT / 'frontend' / 'src' / 'controlPage.jsx'
PROJECT_BOOTSTRAP_SECTION_PATH = DASHBOARD_ROOT / 'frontend' / 'src' / 'projectBootstrapSection.jsx'
FRONTEND_SRC_ROOT = DASHBOARD_ROOT / 'frontend' / 'src'
ENV_EXAMPLE_PATH = PACKAGE_ROOT / '.env.example'
REVIEW_STEP_NAMES = {'consistency-review', 'continuity-review', 'ooc-review'}
EXPECTED_REVIEW_KEYS = ['overall_score', 'pass', 'issues', 'metrics', 'summary']


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _read_frontend_sources(*names: str) -> str:
    paths = [FRONTEND_SRC_ROOT / name for name in names] if names else sorted(FRONTEND_SRC_ROOT.glob('*.*'))
    return '\n'.join(
        path.read_text(encoding='utf-8-sig')
        for path in paths
        if path.is_file()
    )


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
    source = _read_frontend_sources('App.jsx', 'controlPage.jsx')
    assert "fetchJSON('/api/rag/status', params)" in source
    assert 'setRagStatus(ragResult.value)' in source
    assert 'setRagStatusError(normalizeError(ragResult.reason))' in source
    assert 'UI_COPY.retrievalEngine' in source
    assert '<MetricCard label={UI_COPY.retrievalEngine}' in source


def test_frontend_exposes_writing_model_status():
    app_source = APP_PATH.read_text(encoding='utf-8-sig')
    control_source = CONTROL_PAGE_PATH.read_text(encoding='utf-8-sig')
    assert 'formatWritingModelPill' in app_source
    source = f'{app_source}\n{control_source}'
    assert 'formatWritingModelDetail' in source
    assert "llmStatus.mode === 'cli'" in source
    assert "llmStatus.mode === 'api'" in source
    assert '<MetricCard label={UI_COPY.writingEngine}' in source
    assert 'formatWritingModelDetail(llmStatus)' in source


def test_frontend_status_copy_flows_through_shared_helpers():
    app_source = APP_PATH.read_text(encoding='utf-8-sig')
    control_source = CONTROL_PAGE_PATH.read_text(encoding='utf-8-sig')
    helper_source = (FRONTEND_SRC_ROOT / 'serviceStatus.js').read_text(encoding='utf-8-sig')

    assert "from './serviceStatus.js'" in app_source
    assert "from './serviceStatus.js'" in control_source
    assert 'formatRagStatusLabel' in helper_source
    assert 'formatRagDetail' in helper_source
    assert 'formatWritingModelPill' in helper_source
    assert 'formatWritingModelDetail' in helper_source


def test_frontend_reads_project_info_from_state_json_shape():
    source = _read_frontend_sources('App.jsx', 'controlPage.jsx')
    assert 'const projectMeta = projectInfo?.project_info || projectInfo || {}' in source
    assert 'projectMeta?.project_name' in source
    assert 'projectMeta?.title' in source
    assert 'projectMeta?.genre' in source


def test_frontend_translates_review_gate_block_event():
    source = _read_frontend_sources('dashboardPageCommon.jsx')
    assert "'Review gate blocked execution':" in source


def test_frontend_separates_project_bootstrap_from_analysis_init():
    app_source = _read_frontend_sources('App.jsx', 'controlPage.jsx')
    bootstrap_source = PROJECT_BOOTSTRAP_SECTION_PATH.read_text(encoding='utf-8-sig')
    assert "{ key: 'init', title: '补齐旧项目骨架', fields: ['project_root'] }" in app_source
    assert "ProjectBootstrapSection" in app_source
    assert "postJSON('/api/project/bootstrap'" in bootstrap_source
    assert "project_root: form.project_root" in bootstrap_source
    assert "title: form.title" in bootstrap_source
    assert "genre: form.genre" in bootstrap_source


def test_env_example_documents_codex_and_api_writing_models():
    source = ENV_EXAMPLE_PATH.read_text(encoding='utf-8-sig')
    assert 'WEBNOVEL_LLM_PROVIDER=codex-cli' in source
    assert 'WEBNOVEL_CODEX_BIN=codex.cmd' in source
    assert '# WEBNOVEL_LLM_PROVIDER=openai-compatible' in source
    assert '# WEBNOVEL_LLM_MODEL=gpt-5.4' in source
    assert 'WEBNOVEL_RAG_BASE_URL=https://api.siliconflow.cn/v1' in source
