import json
from pathlib import Path

from dashboard.orchestrator import OrchestrationService


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    outline_dir = project_root / "大纲"
    director_dir = webnovel_dir / "director"
    story_dir = webnovel_dir / "story-director"

    director_dir.mkdir(parents=True)
    story_dir.mkdir(parents=True)
    outline_dir.mkdir(parents=True)

    state = {
        "project_info": {"title": "夜档案", "genre": "都市悬疑"},
        "progress": {
            "current_chapter": 0,
            "total_words": 0,
            "current_volume": 1,
            "volumes_planned": [{"volume": 1, "chapters_range": "1-50"}],
        },
        "planning": {
            "volume_plans": {
                "1": {
                    "outline_file": "大纲/volume-01-plan.md",
                    "chapter_count": 50,
                }
            }
        },
        "plot_threads": {"active_threads": [], "foreshadowing": []},
        "chapter_meta": {},
        "disambiguation_warnings": [],
        "disambiguation_pending": [],
    }
    (webnovel_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (outline_dir / "volume-01-plan.md").write_text(
        "# Volume 1 Plan\n\n## Chapter Beats\n"
        "- Chapter 1: 顾临在夜班监控里发现人数对不上，并第一次察觉异常会篡改记录。\n",
        encoding="utf-8",
    )
    return project_root


def test_get_chapter_brief_rebuilds_stale_placeholder_brief_from_outline(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)
    stale_brief = {
        "chapter": 1,
        "chapter_goal": "第1章优先推进“推进当前卷主线”并抬升下一步行动压力。",
        "primary_conflict": "本章主冲突必须服务于当前大纲推进点：⚠️ 未找到第 1 章的大纲",
        "must_advance_threads": ["推进当前卷主线", "保持章末钩子连续驱动"],
        "setup_targets": ["补一条可回收的新线索"],
        "ending_hook_target": "章末把行动压力切到下一章的更高风险场景。",
    }
    service._write_director_brief(1, stale_brief)

    refreshed = service.get_chapter_brief(1)

    assert "未找到第 1 章的大纲" not in refreshed["primary_conflict"]
    assert "推进当前卷主线" not in refreshed["chapter_goal"]
    assert "保持章末钩子连续驱动" not in refreshed["must_advance_threads"]
    assert refreshed["must_advance_threads"]
    assert refreshed["must_advance_threads"] != stale_brief["must_advance_threads"]
    persisted = json.loads((project_root / ".webnovel" / "director" / "ch0001.json").read_text(encoding="utf-8"))
    assert persisted["chapter_goal"] == refreshed["chapter_goal"]


def test_get_director_hub_rebuilds_stale_placeholder_story_plan_from_outline(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)
    stale_plan = {
        "anchor_chapter": 1,
        "planning_horizon": 4,
        "priority_threads": ["推进当前卷主线", "保持章末钩子连续驱动"],
        "chapters": [
            {
                "chapter": 1,
                "role": "current-execution",
                "chapter_goal": "第1章优先推进“推进当前卷主线”并抬升下一步行动压力。",
                "must_advance_threads": ["推进当前卷主线", "保持章末钩子连续驱动"],
                "optional_payoffs": [],
                "forbidden_resolutions": ["不要在第1章彻底解决 推进当前卷主线"],
                "ending_hook_target": "章末把行动压力切到下一章的更高风险场景。",
            }
        ],
        "rationale": "当前 story plan 根据 active foreshadowing、knowledge conflicts、最近导演执行结果生成。",
    }
    service._write_story_plan(1, stale_plan)

    hub = service.get_director_hub()
    refreshed = hub["story_plan"]
    current_slot = next(item for item in refreshed["chapters"] if item["chapter"] == 1)

    assert "推进当前卷主线" not in refreshed["priority_threads"]
    assert "保持章末钩子连续驱动" not in refreshed["priority_threads"]
    assert any("人数对不上" in item or "篡改记录" in item for item in refreshed["priority_threads"])
    assert "推进当前卷主线" not in current_slot["chapter_goal"]
    persisted = json.loads((project_root / ".webnovel" / "story-director" / "plan-ch0001.json").read_text(encoding="utf-8"))
    assert persisted["priority_threads"] == refreshed["priority_threads"]


def test_get_continuity_ledger_hides_non_actionable_placeholder_threads(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)
    state_path = project_root / ".webnovel" / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["plot_threads"]["active_threads"] = [
        {"title": "推进当前卷主线", "stage": "active"},
        {"title": "保持章末钩子连续驱动", "stage": "active"},
        {"title": "尾号7的三条工号", "stage": "active"},
    ]
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    ledger = service.get_continuity_ledger()

    titles = [item["title"] for item in ledger["plot_threads"]]
    assert titles == ["尾号7的三条工号"]
