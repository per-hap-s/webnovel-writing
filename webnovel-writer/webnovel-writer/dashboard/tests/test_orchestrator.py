from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from dashboard.llm_runner import StepResult
from dashboard.orchestrator import OrchestrationService


def step_result(step_name: str, *, success: bool = True, payload: dict | None = None, error: dict | None = None) -> StepResult:
    payload = payload if payload is not None else {'result': 'ok'}
    return StepResult(
        step_name=step_name,
        success=success,
        return_code=0 if success else 1,
        timing_ms=100,
        stdout=json.dumps(payload, ensure_ascii=False) if payload is not None else '',
        stderr='',
        structured_output=payload,
        prompt_file='prompt.md',
        output_file='output.txt',
        error=error,
    )


class MappingRunner:
    def probe(self):
        return {'provider': 'codex-cli', 'installed': True, 'configured': True}

    def run(self, step_spec, workspace, prompt_bundle):
        return step_result(step_spec['name'])


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / 'novel'
    (project_root / '.webnovel').mkdir(parents=True)
    (project_root / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')
    outline_dir = project_root / '大纲'
    outline_dir.mkdir(parents=True)
    (outline_dir / '总纲.md').write_text('# outline\n', encoding='utf-8')
    return project_root


def test_probe_rag_returns_client_probe(tmp_path: Path):
    project_root = make_project(tmp_path)

    with patch('dashboard.orchestrator.get_client') as mock_get_client:
        mock_get_client.return_value.probe.return_value = {'provider': 'siliconflow', 'configured': True}
        service = OrchestrationService(project_root, runner=MappingRunner())
        result = service.probe_rag()

    assert result['provider'] == 'siliconflow'
    mock_get_client.return_value.probe.assert_called_once()


def test_retry_keeps_failed_step_and_queues_again(tmp_path: Path):
    project_root = make_project(tmp_path)

    class FailingRunner(MappingRunner):
        def run(self, step_spec, workspace, prompt_bundle):
            return step_result(step_spec['name'], success=False, payload=None, error={'code': 'STEP_FAILED', 'message': 'failed'})

    workflow = {'name': 'write', 'version': 1, 'steps': [{'name': 'context', 'type': 'llm'}, {'name': 'draft', 'type': 'llm'}]}
    service = OrchestrationService(project_root, runner=FailingRunner())
    task = service.store.create_task('write', {'chapter': 1}, workflow)

    asyncio.run(service._run_task(task['id']))
    failed_task = service.get_task(task['id'])
    assert failed_task['status'] == 'failed'
    assert failed_task['current_step'] == 'context'

    retried = service.retry_task(task['id'])
    assert retried['status'] == 'queued'
