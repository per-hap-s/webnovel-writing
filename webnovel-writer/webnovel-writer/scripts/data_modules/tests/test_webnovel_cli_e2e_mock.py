#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from dashboard.orchestrator import OrchestrationService
from scripts.init_project import build_bootstrap_planning_profile, save_planning_profile, sync_master_outline_with_profile


ROOT = Path(__file__).resolve().parents[4]


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / 'novel'
    (project_root / '.webnovel').mkdir(parents=True)
    title = '测试长篇'
    genre = '都市异能'
    planning_profile = build_bootstrap_planning_profile(title=title, genre=genre)
    outline_text = sync_master_outline_with_profile(
        '',
        title=title,
        genre=genre,
        target_chapters=120,
        profile=planning_profile,
    )
    save_planning_profile(project_root, planning_profile, title=title, genre=genre)
    (project_root / '.webnovel' / 'state.json').write_text(
        json.dumps(
            {
                'project_info': {
                    'title': title,
                    'genre': genre,
                    'target_chapters': 120,
                },
                'planning': {
                    'profile': planning_profile,
                },
                'progress': {
                    'current_chapter': 0,
                    'total_words': 0,
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding='utf-8',
    )
    (project_root / '大纲').mkdir(parents=True)
    (project_root / '大纲' / '总纲.md').write_text(outline_text, encoding='utf-8')
    return project_root


def make_mock_responses(path: Path) -> Path:
    chapter_content = "\n".join(
        [
            "夜雨压着旧城的霓虹往下坠，林夜站在便利店门口盯着巷口那辆迟迟没有熄火的黑色轿车。",
            "他知道自己只要转身离开，就能把今晚的麻烦先拖到明天，但那份刚拿到的纸质档案偏偏在掌心发烫。",
            "档案里写着一个已经死去三年的名字，而那个人今晚却在监控截图里重新出现，还把目光投向了他租住的旧楼。",
            "林夜压下心里的惧意，先给唯一能信半分的顾迟发去定位，再把兜里的备用钥匙扣进指缝，沿着积水最深的地方往巷子里走。",
            "他必须在对方反应过来之前确认那份档案到底是谁塞给自己的，也必须弄清这场看似偶然的重逢为什么偏偏落在今夜。",
            "等他推开尽头那扇被雨浸得发胀的铁门时，门后的脚步声已经先一步停住，像是有人早就知道他一定会来。",
        ]
    )
    payload = {
        'plan': {'volume_plan': {'title': '卷一'}, 'chapters': [{'chapter': 1, 'goal': '起势'}]},
        'context': {'task_brief': {}, 'contract_v2': {}, 'draft_prompt': 'x'},
        'draft': {'chapter_file': '正文/第0001章.md', 'content': chapter_content, 'word_count': len(''.join(chapter_content.split()))},
        'consistency-review': {'overall_score': 90, 'pass': True, 'issues': [], 'metrics': {}, 'summary': '一致性通过'},
        'continuity-review': {'overall_score': 88, 'pass': True, 'issues': [], 'metrics': {}, 'summary': '连续性通过'},
        'ooc-review': {'overall_score': 86, 'pass': True, 'issues': [], 'metrics': {}, 'summary': '角色一致性通过'},
        'polish': {
            'chapter_file': '正文/第0001章.md',
            'content': chapter_content,
            'word_count': len(''.join(chapter_content.split())),
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


def _resume_after_brief_approval(project_root: Path, responses: Path) -> dict:
    previous_provider = os.environ.get('WEBNOVEL_LLM_PROVIDER')
    previous_responses = os.environ.get('WEBNOVEL_MOCK_RESPONSES_FILE')
    previous_utf8 = os.environ.get('PYTHONUTF8')
    os.environ['WEBNOVEL_LLM_PROVIDER'] = 'mock'
    os.environ['WEBNOVEL_MOCK_RESPONSES_FILE'] = str(responses)
    os.environ['PYTHONUTF8'] = '1'
    try:
        service = OrchestrationService(project_root)
        approved = service.approve_chapter_brief(1, reason='cli e2e test approval')
        asyncio.run(service._run_task(approved['id'], resume_from_step='chapter-brief-approval'))
        completed = service.get_task(approved['id'])
        assert completed is not None
        return completed
    finally:
        if previous_provider is None:
            os.environ.pop('WEBNOVEL_LLM_PROVIDER', None)
        else:
            os.environ['WEBNOVEL_LLM_PROVIDER'] = previous_provider
        if previous_responses is None:
            os.environ.pop('WEBNOVEL_MOCK_RESPONSES_FILE', None)
        else:
            os.environ['WEBNOVEL_MOCK_RESPONSES_FILE'] = previous_responses
        if previous_utf8 is None:
            os.environ.pop('PYTHONUTF8', None)
        else:
            os.environ['PYTHONUTF8'] = previous_utf8


def test_root_cli_runs_workflows_with_mock_runner(tmp_path: Path):
    project_root = make_project(tmp_path)
    responses = make_mock_responses(tmp_path / 'responses.json')

    plan = run_cli(project_root, responses, 'plan', '1')
    write = run_cli(project_root, responses, 'write', '1')
    write_payload = json.loads(write.stdout)
    resumed_write = _resume_after_brief_approval(project_root, responses)
    review = run_cli(project_root, responses, 'review', '1-1')
    resume = run_cli(project_root, responses, 'resume')
    resume_payload = json.loads(resume.stdout)

    state = json.loads((project_root / '.webnovel' / 'state.json').read_text(encoding='utf-8'))

    assert plan.returncode == 0, plan.stderr or plan.stdout
    assert write.returncode == 1, write.stderr or write.stdout
    assert write_payload['status'] == 'awaiting_chapter_brief_approval'
    assert resumed_write['status'] == 'completed'
    assert review.returncode == 0, review.stderr or review.stdout
    assert resume.returncode == 1, resume.stderr or resume.stdout
    assert resume_payload['error']['code'] == 'NO_RESUMABLE_TASK'
    assert (project_root / '正文' / '第1卷' / '第0001章.md').read_text(encoding='utf-8').startswith('夜雨压着旧城的霓虹往下坠')
    assert (project_root / '.webnovel' / 'summaries' / 'ch0001.md').read_text(encoding='utf-8').startswith('# CLI 摘要')
    assert state['progress']['current_chapter'] == 1
    assert state['chapter_meta']['0001']['hook']['type'] == 'cliff'
