#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / 'novel'
    (project_root / '.webnovel').mkdir(parents=True)
    (project_root / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')
    (project_root / '大纲').mkdir(parents=True)
    (project_root / '大纲' / '总纲.md').write_text('# 总纲\n', encoding='utf-8')
    return project_root


def make_mock_responses(path: Path) -> Path:
    payload = {
        'plan': {'volume_plan': {'title': '卷一'}, 'chapters': [{'chapter': 1, 'goal': '起势'}]},
        'context': {'task_brief': {}, 'contract_v2': {}, 'draft_prompt': 'x'},
        'draft': {'chapter_file': '正文/第0001章.md', 'content': 'draft', 'word_count': 1200},
        'consistency-review': {'score': 90, 'issues': []},
        'continuity-review': {'score': 88, 'issues': []},
        'ooc-review': {'score': 86, 'issues': []},
        'polish': {
            'chapter_file': '正文/第0001章.md',
            'content': 'cli polished content',
            'anti_ai_force_check': 'pass',
            'change_summary': [],
        },
        'data-sync': {
            'files_written': ['正文/第0001章.md', '.webnovel/summaries/ch0001.md'],
            'summary_file': '.webnovel/summaries/ch0001.md',
            'state_updated': True,
            'index_updated': True,
            'summary_content': '# CLI 摘要\n\n这是 mock runner 生成的摘要。\n',
            'chapter_meta': {'hook': {'type': 'cliff', 'strength': 'strong'}},
        },
        'resume': {'resume_plan': {'next_action': '继续第2章'}, 'detected_breakpoint': {'chapter': 1}},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def run_cli(project_root: Path, responses: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env['WEBNOVEL_LLM_PROVIDER'] = 'mock'
    env['WEBNOVEL_MOCK_RESPONSES_FILE'] = str(responses)
    env['PYTHONUTF8'] = '1'
    return subprocess.run(
        [sys.executable, str(ROOT / 'webnovel.py'), '--project-root', str(project_root), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        check=False,
    )


def test_root_cli_runs_workflows_with_mock_runner(tmp_path: Path):
    project_root = make_project(tmp_path)
    responses = make_mock_responses(tmp_path / 'responses.json')

    plan = run_cli(project_root, responses, 'plan', '1')
    write = run_cli(project_root, responses, 'write', '1')
    review = run_cli(project_root, responses, 'review', '1-1')
    resume = run_cli(project_root, responses, 'resume')

    state = json.loads((project_root / '.webnovel' / 'state.json').read_text(encoding='utf-8'))

    assert plan.returncode == 0, plan.stderr or plan.stdout
    assert write.returncode == 0, write.stderr or write.stdout
    assert review.returncode == 0, review.stderr or review.stdout
    assert resume.returncode == 0, resume.stderr or resume.stdout
    assert (project_root / '正文' / '第0001章.md').read_text(encoding='utf-8') == 'cli polished content'
    assert (project_root / '.webnovel' / 'summaries' / 'ch0001.md').read_text(encoding='utf-8').startswith('# CLI 摘要')
    assert state['progress']['current_chapter'] == 1
    assert state['chapter_meta']['0001']['hook']['type'] == 'cliff'
