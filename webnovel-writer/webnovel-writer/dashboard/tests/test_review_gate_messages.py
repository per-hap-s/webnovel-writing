from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dashboard.llm_runner import StepResult
from dashboard.orchestrator import OrchestrationService


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / 'novel'
    (project_root / '.webnovel').mkdir(parents=True)
    (project_root / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')
    (project_root / '大纲').mkdir(parents=True)
    (project_root / '大纲' / '总纲.md').write_text('# 总纲\n', encoding='utf-8')
    return project_root


class TimelineBlockingRunner:
    def __init__(self):
        self.calls = []

    def probe(self):
        return {'provider': 'timeline-block', 'installed': True}

    def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
        self.calls.append(step_spec['name'])
        if step_spec['name'] == 'consistency-review':
            payload = {
                'agent': 'consistency-review',
                'chapter': 1,
                'overall_score': 60,
                'pass': False,
                'issues': [
                    {
                        'type': 'TIMELINE_ISSUE',
                        'severity': 'high',
                        'description': 'timeline conflict',
                    }
                ],
                'metrics': {},
                'summary': 'blocking review summary',
            }
        else:
            payload = {
                'chapter_file': '正文/第0001章.md',
                'content': 'draft',
                'anti_ai_force_check': 'pass',
                'change_summary': [],
            }
        return StepResult(
            step_name=step_spec['name'],
            success=True,
            return_code=0,
            timing_ms=100,
            stdout=json.dumps(payload, ensure_ascii=False),
            stderr='',
            structured_output=payload,
            prompt_file='prompt.md',
            output_file='output.txt',
        )



def test_review_gate_emits_readable_event_messages(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = TimelineBlockingRunner()
    service = OrchestrationService(project_root, runner=runner)
    workflow = {
        'name': 'write',
        'version': 1,
        'steps': [
            {
                'name': 'consistency-review',
                'type': 'llm',
                'required_output_keys': ['overall_score', 'pass', 'issues', 'metrics', 'summary'],
            },
            {'name': 'review-summary', 'type': 'internal'},
            {
                'name': 'polish',
                'type': 'llm',
                'required_output_keys': ['chapter_file', 'content', 'anti_ai_force_check', 'change_summary'],
            },
        ],
    }
    service._load_workflow = lambda task_type: workflow
    task = service.store.create_task('write', {'chapter': 1, 'require_manual_approval': False}, workflow)

    asyncio.run(service._run_task(task['id']))

    result = service.get_task(task['id'])
    events = service.get_events(task['id'])
    messages = [event['message'] for event in events]

    assert result['status'] == 'failed'
    assert result['error']['code'] == 'REVIEW_GATE_BLOCKED'
    assert result['error']['message'].startswith('审查关卡阻止继续执行：[high]')
    assert 'Review summary prepared' in messages
    assert 'Review gate blocked execution' in messages

