import io
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError

import dashboard.llm_runner as llm_runner_module
from dashboard.llm_runner import CodexCliRunner, MockRunner, OpenAICompatibleRunner, create_default_runner


def test_codex_cli_runner_reports_missing_binary(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_CODEX_BIN', 'definitely-not-a-real-codex-binary')
    runner = CodexCliRunner(project_root)
    result = runner.run(
        {'name': 'context', 'instructions': 'do', 'output_schema': {}},
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is False
    assert result.error['code'] == 'CODEX_CLI_NOT_FOUND'
    assert result.error['message'] == '未找到 Codex CLI 可执行文件。'


def test_api_runner_reports_missing_configuration(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.chdir(tmp_path)
    for key in ['WEBNOVEL_LLM_PROVIDER', 'WEBNOVEL_LLM_API_KEY', 'WEBNOVEL_LLM_MODEL', 'WEBNOVEL_LLM_BASE_URL', 'OPENAI_API_KEY', 'OPENAI_MODEL', 'OPENAI_BASE_URL']:
        monkeypatch.delenv(key, raising=False)

    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {'name': 'context', 'instructions': 'do', 'output_schema': {}},
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is False
    assert result.error['code'] == 'LLM_NOT_CONFIGURED'
    assert result.error['message'] == '请先配置写作模型的 API Key 和模型名称。'

def test_mock_runner_uses_response_file(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    responses = project_root / 'responses.json'
    responses.write_text('{"context": {"task_brief": {}, "contract_v2": {}, "draft_prompt": "x"}}', encoding='utf-8')
    monkeypatch.setenv('WEBNOVEL_MOCK_RESPONSES_FILE', str(responses))

    runner = MockRunner(project_root)
    result = runner.run(
        {'name': 'context', 'instructions': 'do', 'output_schema': {}},
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert runner.probe()['configured'] is True
    assert result.success is True
    assert result.structured_output['draft_prompt'] == 'x'


def test_create_default_runner_reads_project_dotenv(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    (project_root / '.env').write_text('WEBNOVEL_LLM_PROVIDER=codex-cli\nWEBNOVEL_CODEX_BIN=codex.cmd\n', encoding='utf-8')
    monkeypatch.delenv('WEBNOVEL_LLM_PROVIDER', raising=False)
    monkeypatch.delenv('WEBNOVEL_CODEX_BIN', raising=False)

    runner = create_default_runner(project_root)

    assert isinstance(runner, CodexCliRunner)
    assert runner.binary == 'codex.cmd'


def test_codex_cli_runner_prefers_cmd_binary_on_windows(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.delenv('WEBNOVEL_CODEX_BIN', raising=False)
    monkeypatch.setattr(llm_runner_module.os, 'name', 'nt', raising=False)

    def fake_which(name: str):
        if name == 'codex.cmd':
            return r'C:\Tools\codex.cmd'
        return None

    monkeypatch.setattr(llm_runner_module.shutil, 'which', fake_which)
    monkeypatch.setattr(
        llm_runner_module.subprocess,
        'run',
        lambda *args, **kwargs: SimpleNamespace(stdout='codex 0.0.0', stderr=''),
    )

    runner = CodexCliRunner(project_root)
    probe = runner.probe()

    assert probe['installed'] is True
    assert probe['binary'] == 'codex.cmd'
    assert probe['resolved_binary'] == r'C:\Tools\codex.cmd'


def test_api_runner_probe_checks_connectivity(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"choices": [{"message": {"content": "ok"}}]}'

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', lambda req, timeout=0: FakeResponse())

    runner = OpenAICompatibleRunner(project_root)
    probe = runner.probe()

    assert probe['configured'] is True
    assert probe['connection_status'] == 'connected'
    assert probe['connection_error'] is None


def test_api_runner_probe_reports_connectivity_failure(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')

    def fake_urlopen(req, timeout=0):
        raise HTTPError(req.full_url, 503, 'Service Unavailable', hdrs=None, fp=io.BytesIO(b'upstream down'))

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', fake_urlopen)

    runner = OpenAICompatibleRunner(project_root)
    probe = runner.probe()

    assert probe['connection_status'] == 'failed'
    assert probe['connection_error']['code'] == 'LLM_HTTP_ERROR'
    assert probe['connection_error']['message'] == '写作模型健康检查失败。'
