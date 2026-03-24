import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from dashboard.orchestrator import OrchestrationService
from scripts.data_modules.index_manager import EntityMeta


class MappingRunner:
    def probe(self):
        return {
            "provider": "codex-cli",
            "mode": "cli",
            "installed": True,
            "configured": True,
            "connection_status": "connected",
        }


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    (webnovel_dir / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "Alignment Test", "genre": "Suspense"},
                "progress": {"current_chapter": 0, "total_words": 0},
                "chapter_meta": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True)
    (outline_dir / "总纲.md").write_text("# outline\n", encoding="utf-8")
    return project_root


def test_writeback_records_director_and_story_alignment(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    service.index_manager.upsert_entity(
        EntityMeta(
            id="hero",
            type="角色",
            canonical_name="沈砚",
            tier="核心",
            current={},
            first_appearance=1,
            last_appearance=1,
            is_protagonist=True,
        )
    )

    workflow = {"name": "write", "version": 1, "steps": []}
    task = service.store.create_task("write", {"chapter": 1}, workflow)

    story_plan = {
        "anchor_chapter": 1,
        "planning_horizon": 4,
        "priority_threads": ["雨夜警报", "信任裂缝"],
        "payoff_schedule": [{"thread": "雨夜警报", "target_chapter": 1, "mode": "major"}],
        "defer_schedule": [],
        "risk_flags": [],
        "transition_notes": ["本章要把警报转成可执行动作。"],
        "chapters": [
            {
                "chapter": 1,
                "role": "current-execution",
                "chapter_goal": "把雨夜警报转成可见行动和代价。",
                "must_advance_threads": ["雨夜警报", "信任裂缝"],
                "optional_payoffs": ["雨夜警报"],
                "forbidden_resolutions": ["不要公开幕后主使"],
                "ending_hook_target": "章末逼主角进入观测塔。",
            }
        ],
        "rationale": "当前窗口先完成动作化推进。",
    }
    service.store.save_step_result(task["id"], "story-director", {"success": True, "structured_output": story_plan})
    service._write_story_plan(1, story_plan)

    director_brief = {
        "chapter": 1,
        "chapter_goal": "推进雨夜警报主线。",
        "primary_conflict": "沈砚必须在记忆继续受损前查出线索。",
        "must_advance_threads": ["雨夜警报"],
        "payoff_targets": ["雨夜警报"],
        "setup_targets": ["观测塔线索"],
        "must_use_entities": ["沈砚"],
        "relationship_moves": [],
        "knowledge_reveals": ["警报来源"],
        "forbidden_resolutions": ["不要一次性解释完所有疑点"],
        "ending_hook_target": "章末给出进入观测塔的下一步。",
        "tempo": "steady escalation",
        "review_focus": ["检查主线推进是否成立"],
        "rationale": "当前章节必须把警报推进成明确行动。",
    }
    service.store.save_step_result(task["id"], "chapter-director", {"success": True, "structured_output": director_brief})
    service._write_director_brief(1, director_brief)

    payload = {
        "content": ("沈砚沿着雨夜警报留下的痕迹进入观测塔，确认警报来源并发现下一步入口。") * 20,
        "summary_content": "# 第1章摘要\n\n测试摘要\n",
        "chapter_meta": {"title": "第一章", "location": "观测塔", "characters": ["沈砚"]},
        "foreshadowing_items": [
            {
                "name": "雨夜警报",
                "content": "警报总比异变提前十分钟",
                "planted_chapter": 1,
                "planned_payoff_chapter": 1,
                "status": "paid_off",
                "owner_entity": "hero",
            },
            {
                "name": "观测塔线索",
                "content": "塔内留有新的入口标记",
                "planted_chapter": 1,
                "planned_payoff_chapter": 3,
                "status": "active",
                "owner_entity": "hero",
            },
        ],
        "knowledge_states": [
            {
                "entity_id": "hero",
                "chapter": 1,
                "topic": "警报来源",
                "belief": "警报来自观测塔底层装置",
                "truth_status": "partial",
                "confidence": 0.8,
            }
        ],
    }

    with patch.object(service, "_validate_writeback_consistency", return_value=None), patch.object(
        service, "_sync_core_setting_docs", return_value=None
    ):
        asyncio.run(service._apply_write_data_sync(task["id"], service.store.get_task(task["id"]) or task, payload))

    refreshed = service.store.get_task(task["id"]) or {}
    story_alignment = (((refreshed.get("artifacts") or {}).get("writeback") or {}).get("story_alignment") or {})
    director_alignment = (((refreshed.get("artifacts") or {}).get("writeback") or {}).get("director_alignment") or {})

    assert "thread:雨夜警报" in story_alignment["satisfied"]
    assert "payoff:雨夜警报" in story_alignment["satisfied"]
    assert "thread:信任裂缝" in story_alignment["missed"]

    assert "payoff:雨夜警报" in director_alignment["satisfied"]
    assert "setup:观测塔线索" in director_alignment["satisfied"]
    assert "entity:沈砚" in director_alignment["satisfied"]
    assert "knowledge:警报来源" in director_alignment["satisfied"]


def test_writeback_marks_story_refresh_when_missed_targets_accumulate(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())

    previous_task = service.store.create_task("write", {"chapter": 1}, {"name": "write", "version": 1, "steps": []})
    previous_artifacts = dict(previous_task.get("artifacts") or {})
    previous_artifacts["writeback"] = {
        "story_alignment": {
            "satisfied": [],
            "missed": ["thread:旧案真相"],
            "deferred": [],
        }
    }
    service.store.update_task(previous_task["id"], artifacts=previous_artifacts, status="completed")

    task = service.store.create_task("write", {"chapter": 2}, {"name": "write", "version": 1, "steps": []})
    story_plan = {
        "anchor_chapter": 2,
        "planning_horizon": 4,
        "priority_threads": ["雨夜警报", "信任裂缝"],
        "payoff_schedule": [],
        "defer_schedule": [],
        "risk_flags": [],
        "transition_notes": [],
        "chapters": [
            {
                "chapter": 2,
                "role": "current-execution",
                "chapter_goal": "推进调查，但不要停留在解释。",
                "must_advance_threads": ["雨夜警报", "信任裂缝"],
                "optional_payoffs": [],
                "forbidden_resolutions": ["不要公开幕后主使"],
                "ending_hook_target": "章末迫使主角继续追查。",
            }
        ],
        "rationale": "当前窗口需要把调查线持续推进。",
    }
    service.store.save_step_result(task["id"], "story-director", {"success": True, "structured_output": story_plan})
    service._write_story_plan(2, story_plan)
    director_brief = {
        "chapter": 2,
        "chapter_goal": "推进调查。",
        "primary_conflict": "主角必须继续追查。",
        "must_advance_threads": ["雨夜警报"],
        "payoff_targets": [],
        "setup_targets": [],
        "must_use_entities": [],
        "relationship_moves": [],
        "knowledge_reveals": [],
        "forbidden_resolutions": ["不要公开幕后主使"],
        "ending_hook_target": "章末继续追查。",
        "tempo": "steady escalation",
        "review_focus": ["检查调查线是否推进"],
        "rationale": "维持推进。",
    }
    service.store.save_step_result(task["id"], "chapter-director", {"success": True, "structured_output": director_brief})
    service._write_director_brief(2, director_brief)

    payload = {
        "content": ("沈砚进入观测塔外围，但仍未触及警报核心，只确认敌方已经提前布置陷阱。") * 20,
        "summary_content": "# 第2章摘要\n\n测试摘要\n",
        "chapter_meta": {"title": "第二章", "location": "观测塔外围", "characters": ["沈砚"]},
        "foreshadowing_items": [],
        "knowledge_states": [],
    }

    with patch.object(service, "_validate_writeback_consistency", return_value=None), patch.object(
        service, "_sync_core_setting_docs", return_value=None
    ):
        asyncio.run(service._apply_write_data_sync(task["id"], service.store.get_task(task["id"]) or task, payload))

    refreshed = service.store.get_task(task["id"]) or {}
    writeback = ((refreshed.get("artifacts") or {}).get("writeback") or {})
    story_refresh = writeback.get("story_refresh") or {}
    assert story_refresh["should_refresh"] is True
    assert story_refresh["recommended_resume_from"] == "story-director"
    assert story_refresh["consecutive_missed_chapters"] >= 2

    events = service.store.get_events(task["id"])
    assert any(event.get("message") == "Story plan refresh suggested" for event in events)


def test_story_refresh_does_not_trigger_for_single_light_miss_without_history(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())

    assessment = service._build_story_refresh_assessment(
        {"anchor_chapter": 5, "planning_horizon": 4},
        {
            "satisfied": [],
            "missed": ["thread:异常名单"],
            "deferred": [],
        },
        chapter=5,
    )

    assert assessment["should_refresh"] is False
    assert assessment["recommended_resume_from"] is None
    assert assessment["suggested_action"] == "当前滚动规划仍可继续使用。"


def test_story_refresh_does_not_trigger_for_single_chapter_partial_miss(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())

    assessment = service._build_story_refresh_assessment(
        {"anchor_chapter": 6, "planning_horizon": 4},
        {
            "satisfied": ["thread:封控升级"],
            "missed": ["thread:白蜡印", "scheduled:白蜡印@6"],
            "deferred": [],
        },
        chapter=6,
    )

    assert assessment["should_refresh"] is False
    assert assessment["recommended_resume_from"] is None


def test_story_alignment_ignores_non_actionable_placeholder_threads(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())

    story_plan = {
        "anchor_chapter": 1,
        "planning_horizon": 4,
        "chapters": [
            {
                "chapter": 1,
                "must_advance_threads": ["推进当前卷主线", "保持章末钩子连续驱动"],
                "optional_payoffs": [],
            }
        ],
        "payoff_schedule": [],
    }
    payload = {
        "foreshadowing_items": [],
        "timeline_events": [],
        "knowledge_states": [],
        "chapter_meta": {"characters": ["顾临"]},
    }

    alignment = service._build_story_alignment(story_plan, payload, "顾临发现人数对不上，并被迫接下异常处理任务。", 1)
    assessment = service._build_story_refresh_assessment(story_plan, alignment, chapter=1)

    assert alignment == {"satisfied": [], "missed": [], "deferred": []}
    assert assessment["should_refresh"] is False


def test_director_alignment_ignores_non_actionable_placeholder_targets(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())

    director_brief = {
        "payoff_targets": [],
        "setup_targets": ["补一条可回收的新线索"],
        "must_advance_threads": ["推进本章主线目标"],
        "must_use_entities": [],
        "relationship_moves": [],
        "knowledge_reveals": [],
    }
    payload = {
        "foreshadowing_items": [],
        "timeline_events": [],
        "character_arcs": [],
        "knowledge_states": [],
        "relationships_new": [],
        "chapter_meta": {"characters": ["顾临"]},
    }

    alignment = service._build_director_alignment(director_brief, payload, "顾临先处理眼前风险。")

    assert alignment == {"satisfied": [], "missed": [], "deferred": []}
