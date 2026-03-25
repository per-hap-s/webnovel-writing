import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError

import dashboard.llm_runner as llm_runner_module
from dashboard.llm_runner import CodexCliRunner, MockRunner, OpenAICompatibleRunner, create_default_runner


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._body


def build_chat_completion_response(content: str) -> bytes:
    return json.dumps(
        {
            'choices': [
                {
                    'message': {
                        'content': content,
                    }
                }
            ]
        },
        ensure_ascii=False,
    ).encode('utf-8')


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


def test_codex_cli_runner_recovers_fenced_json_and_records_parse_metadata(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setattr(llm_runner_module.shutil, 'which', lambda _: r'C:\Tools\codex.cmd')

    def fake_run(args, **kwargs):
        Path(args[3]).write_text(
            '```json\n{"task_brief": {}, "contract_v2": {}, "draft_prompt": "short prompt"}\n```',
            encoding='utf-8',
        )
        return SimpleNamespace(returncode=0, stdout='wrapped json', stderr='')

    monkeypatch.setattr(llm_runner_module.subprocess, 'run', fake_run)
    runner = CodexCliRunner(project_root)
    result = runner.run(
        {
            'name': 'context',
            'instructions': 'do',
            'required_output_keys': ['task_brief', 'contract_v2', 'draft_prompt'],
            'output_schema': {},
        },
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is True
    assert result.structured_output['draft_prompt'] == 'short prompt'
    assert result.metadata['parse_stage'] == 'json_fence'
    assert result.metadata['json_extraction_recovered'] is True
    assert result.metadata['missing_required_keys'] == []


def test_codex_cli_runner_repairs_truncated_string_json_and_reports_missing_keys(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setattr(llm_runner_module.shutil, 'which', lambda _: r'C:\Tools\codex.cmd')

    def fake_run(args, **kwargs):
        Path(args[3]).write_text('{"task_brief": {"chapter": "unfinished}', encoding='utf-8')
        return SimpleNamespace(returncode=0, stdout='partial json', stderr='')

    monkeypatch.setattr(llm_runner_module.subprocess, 'run', fake_run)
    runner = CodexCliRunner(project_root)
    result = runner.run(
        {
            'name': 'context',
            'instructions': 'do',
            'required_output_keys': ['task_brief', 'contract_v2', 'draft_prompt'],
            'output_schema': {},
        },
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is True
    assert result.structured_output['task_brief']['chapter'] == 'unfinished'
    assert result.metadata['parse_stage'] == 'json_truncated_repaired'
    assert result.metadata['json_extraction_recovered'] is True
    assert result.metadata['missing_required_keys'] == ['contract_v2', 'draft_prompt']


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


def test_api_runner_recovers_json_wrapped_in_text(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '0')

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"Here is the result:\\n```json\\n{\\"volume_plan\\": {\\"title\\": \\"Vol 1\\"}, \\"chapters\\": []}\\n```"}}]}'

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', lambda req, timeout=0: FakeResponse())
    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {'name': 'plan', 'instructions': 'do', 'required_output_keys': ['volume_plan', 'chapters'], 'output_schema': {}},
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is True
    assert result.structured_output['volume_plan']['title'] == 'Vol 1'
    assert result.metadata['json_extraction_recovered'] is True
    run_dir = project_root / '.webnovel' / 'observability' / 'llm-runs' / 'task-1-plan'
    assert json.loads((run_dir / 'request.json').read_text(encoding='utf-8'))['step_name'] == 'plan'
    assert json.loads((run_dir / 'result.json').read_text(encoding='utf-8'))['success'] is True
    assert not (run_dir / 'error.json').exists()


def test_api_runner_extracts_text_from_content_parts(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '0')

    payload = {'volume_plan': {'title': '卷一'}, 'chapters': []}
    response_body = json.dumps(
        {
            'choices': [
                {
                    'message': {
                        'content': [
                            {'type': 'text', 'text': json.dumps(payload, ensure_ascii=False)},
                        ],
                    }
                }
            ]
        },
        ensure_ascii=False,
    ).encode('utf-8')

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return response_body

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', lambda req, timeout=0: FakeResponse())
    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {'name': 'plan', 'instructions': 'do', 'required_output_keys': ['volume_plan', 'chapters'], 'output_schema': {}},
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is True
    assert result.structured_output['volume_plan']['title'] == '卷一'


def test_api_runner_recovers_single_missing_closing_brace_in_content(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '0')

    payload = {
        'volume_plan': {'title': '卷一', 'chapter_range': '1-50'},
        'chapters': [{'chapter': 1, 'title': '雨夜预警'}],
    }
    truncated_content = json.dumps(payload, ensure_ascii=False)[:-1]
    response_body = json.dumps(
        {
            'choices': [
                {
                    'message': {
                        'content': truncated_content,
                        'reasoning_content': 'structured plan reasoning',
                    }
                }
            ]
        },
        ensure_ascii=False,
    ).encode('utf-8')

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return response_body

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', lambda req, timeout=0: FakeResponse())
    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {'name': 'plan', 'instructions': 'do', 'required_output_keys': ['volume_plan', 'chapters'], 'output_schema': {}},
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is True
    assert result.structured_output['volume_plan']['title'] == '卷一'
    assert result.metadata['parse_stage'] == 'json_truncated_repaired'
    assert result.metadata['json_extraction_recovered'] is True


def test_api_runner_classifies_timeout_and_connection_errors(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '0')

    runner = OpenAICompatibleRunner(project_root)
    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', lambda req, timeout=0: (_ for _ in ()).throw(TimeoutError('request timed out')))
    timeout_result = runner.run(
        {'name': 'polish', 'instructions': 'do', 'output_schema': {}},
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )
    assert timeout_result.error['code'] == 'LLM_TIMEOUT'
    timeout_run_dir = project_root / '.webnovel' / 'observability' / 'llm-runs' / 'task-1-polish'
    timeout_error = json.loads((timeout_run_dir / 'error.json').read_text(encoding='utf-8'))
    assert timeout_error['error']['code'] == 'LLM_TIMEOUT'
    assert (timeout_run_dir / 'request.json').is_file()

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', lambda req, timeout=0: (_ for _ in ()).throw(URLError('connection refused')))
    connection_result = runner.run(
        {'name': 'data-sync', 'instructions': 'do', 'output_schema': {}},
        project_root,
        {'task_id': 'task-2', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )
    assert connection_result.error['code'] == 'LLM_CONNECTION_ERROR'
    connection_run_dir = project_root / '.webnovel' / 'observability' / 'llm-runs' / 'task-2-data-sync'
    connection_error = json.loads((connection_run_dir / 'error.json').read_text(encoding='utf-8'))
    assert connection_error['error']['code'] == 'LLM_CONNECTION_ERROR'


def test_api_runner_retries_retryable_http_5xx(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '1')
    monkeypatch.setattr(llm_runner_module.time, 'sleep', lambda _: None)

    calls = {'count': 0}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return '{"choices":[{"message":{"content":"{\\"chapter_file\\": \\"正文/ch0001.md\\", \\"content\\": \\"text\\", \\"anti_ai_force_check\\": \\"pass\\", \\"change_summary\\": []}"}}]}'.encode('utf-8')

    def fake_urlopen(req, timeout=0):
        calls['count'] += 1
        if calls['count'] == 1:
            raise HTTPError(req.full_url, 503, 'Service Unavailable', hdrs=None, fp=io.BytesIO(b'upstream down'))
        return FakeResponse()

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', fake_urlopen)
    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {'name': 'polish', 'instructions': 'do', 'required_output_keys': ['chapter_file', 'content', 'anti_ai_force_check', 'change_summary'], 'output_schema': {}},
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is True
    assert calls['count'] == 2
    assert result.metadata['retry_count'] == 1


def test_api_runner_falls_back_to_mini_after_primary_timeout_retries_exhaust(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '1')
    monkeypatch.setenv('WEBNOVEL_LLM_ENABLE_FALLBACK', 'true')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_MODEL', 'gpt-5.4-mini')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_STEPS', 'draft,polish')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_ON', 'LLM_TIMEOUT,LLM_HTTP_ERROR')
    monkeypatch.setattr(llm_runner_module.time, 'sleep', lambda _: None)

    calls: list[str] = []

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode('utf-8'))
        model = payload['model']
        calls.append(model)
        if model == 'gpt-5.4':
            raise TimeoutError('request timed out')
        return FakeResponse(
            build_chat_completion_response(
                '{"chapter_file":"正文/ch0001.md","content":"正文","anti_ai_force_check":"pass","change_summary":[]}'
            )
        )

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', fake_urlopen)
    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {
            'name': 'draft',
            'instructions': 'do',
            'required_output_keys': ['chapter_file', 'content', 'anti_ai_force_check', 'change_summary'],
            'output_schema': {},
        },
        project_root,
        {'task_id': 'task-1', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is True
    assert calls == ['gpt-5.4', 'gpt-5.4', 'gpt-5.4-mini']
    assert result.metadata['primary_model'] == 'gpt-5.4'
    assert result.metadata['fallback_model'] == 'gpt-5.4-mini'
    assert result.metadata['effective_model'] == 'gpt-5.4-mini'
    assert result.metadata['fallback_used'] is True
    assert result.metadata['fallback_trigger_error_code'] == 'LLM_TIMEOUT'
    assert result.metadata['fallback_trigger_http_status'] is None
    assert result.metadata['attempt_models'] == ['gpt-5.4', 'gpt-5.4', 'gpt-5.4-mini']


def test_api_runner_falls_back_after_retryable_5xx_when_primary_retries_exhaust(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '0')
    monkeypatch.setenv('WEBNOVEL_LLM_ENABLE_FALLBACK', 'true')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_MODEL', 'gpt-5.4-mini')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_STEPS', 'draft,polish')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_ON', 'LLM_TIMEOUT,LLM_HTTP_ERROR')

    calls: list[str] = []

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode('utf-8'))
        model = payload['model']
        calls.append(model)
        if model == 'gpt-5.4':
            raise HTTPError(req.full_url, 502, 'Bad Gateway', hdrs=None, fp=io.BytesIO(b'upstream bad gateway'))
        return FakeResponse(build_chat_completion_response('{"volume_plan":{"title":"卷一"},"chapters":[]}'))

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', fake_urlopen)
    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {
            'name': 'polish',
            'instructions': 'do',
            'required_output_keys': ['volume_plan', 'chapters'],
            'output_schema': {},
        },
        project_root,
        {'task_id': 'task-2', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is True
    assert calls == ['gpt-5.4', 'gpt-5.4-mini']
    assert result.metadata['fallback_used'] is True
    assert result.metadata['fallback_trigger_error_code'] == 'LLM_HTTP_ERROR'
    assert result.metadata['fallback_trigger_http_status'] == 502


def test_api_runner_does_not_fallback_on_http_4xx(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '1')
    monkeypatch.setenv('WEBNOVEL_LLM_ENABLE_FALLBACK', 'true')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_MODEL', 'gpt-5.4-mini')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_STEPS', 'draft,polish')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_ON', 'LLM_TIMEOUT,LLM_HTTP_ERROR')

    calls: list[str] = []

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode('utf-8'))
        calls.append(payload['model'])
        raise HTTPError(req.full_url, 429, 'Too Many Requests', hdrs=None, fp=io.BytesIO(b'rate limit'))

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', fake_urlopen)
    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {'name': 'draft', 'instructions': 'do', 'output_schema': {}},
        project_root,
        {'task_id': 'task-3', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is False
    assert calls == ['gpt-5.4']
    assert result.error['code'] == 'LLM_HTTP_ERROR'
    assert result.error['http_status'] == 429
    assert result.error['fallback_used'] is False
    assert result.error['effective_model'] == 'gpt-5.4'
    assert result.error['fallback_exhausted'] is False
    assert result.error['original_message'] == 'rate limit'
    assert result.error['message'] == llm_runner_module.STEP_ERROR_MESSAGES['LLM_HTTP_ERROR']


def test_api_runner_does_not_fallback_on_invalid_step_output(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '1')
    monkeypatch.setenv('WEBNOVEL_LLM_ENABLE_FALLBACK', 'true')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_MODEL', 'gpt-5.4-mini')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_STEPS', 'draft,polish')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_ON', 'LLM_TIMEOUT,LLM_HTTP_ERROR')

    calls: list[str] = []

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode('utf-8'))
        calls.append(payload['model'])
        return FakeResponse(build_chat_completion_response('not json at all'))

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', fake_urlopen)
    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {'name': 'draft', 'instructions': 'do', 'output_schema': {}},
        project_root,
        {'task_id': 'task-4', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is False
    assert calls == ['gpt-5.4']
    assert result.error['code'] == 'INVALID_STEP_OUTPUT'
    assert result.error['fallback_used'] is False
    assert result.metadata['attempt_models'] == ['gpt-5.4']


def test_api_runner_marks_fallback_exhausted_when_primary_and_fallback_both_fail(tmp_path: Path, monkeypatch):
    project_root = tmp_path / 'novel'
    project_root.mkdir()
    monkeypatch.setenv('WEBNOVEL_LLM_PROVIDER', 'openai-compatible')
    monkeypatch.setenv('WEBNOVEL_LLM_API_KEY', 'sk-test')
    monkeypatch.setenv('WEBNOVEL_LLM_MODEL', 'gpt-5.4')
    monkeypatch.setenv('WEBNOVEL_LLM_BASE_URL', 'http://127.0.0.1:8317/v1')
    monkeypatch.setenv('WEBNOVEL_LLM_MAX_RETRIES', '0')
    monkeypatch.setenv('WEBNOVEL_LLM_ENABLE_FALLBACK', 'true')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_MODEL', 'gpt-5.4-mini')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_STEPS', 'draft,polish')
    monkeypatch.setenv('WEBNOVEL_LLM_FALLBACK_ON', 'LLM_TIMEOUT,LLM_HTTP_ERROR')

    calls: list[str] = []

    def fake_urlopen(req, timeout=0):
        payload = json.loads(req.data.decode('utf-8'))
        calls.append(payload['model'])
        raise TimeoutError(f"{payload['model']} timed out")

    monkeypatch.setattr(llm_runner_module.urlrequest, 'urlopen', fake_urlopen)
    runner = OpenAICompatibleRunner(project_root)
    result = runner.run(
        {'name': 'draft', 'instructions': 'do', 'output_schema': {}},
        project_root,
        {'task_id': 'task-5', 'references': [], 'reference_documents': [], 'project_context': [], 'input': {}, 'step_spec': {}},
    )

    assert result.success is False
    assert calls == ['gpt-5.4', 'gpt-5.4-mini']
    assert result.error['code'] == 'LLM_TIMEOUT'
    assert result.error['fallback_used'] is True
    assert result.error['effective_model'] == 'gpt-5.4-mini'
    assert result.error['fallback_exhausted'] is True
    assert result.metadata['attempt_models'] == ['gpt-5.4', 'gpt-5.4-mini']
