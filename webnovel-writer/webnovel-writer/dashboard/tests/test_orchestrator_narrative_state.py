import json
from pathlib import Path
from unittest.mock import patch

import pytest

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
    (project_root / ".webnovel").mkdir(parents=True)
    (project_root / ".webnovel" / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "Narrative Test", "genre": "悬疑"},
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


def _create_write_task(service: OrchestrationService, chapter: int) -> dict:
    workflow = {"name": "write", "version": 1, "steps": []}
    task = service.store.create_task("write", {"chapter": chapter}, workflow)
    return service.store.get_task(task["id"]) or task


def _seed_entities(service: OrchestrationService) -> None:
    service.index_manager.upsert_entity(
        EntityMeta(
            id="hero",
            type="角色",
            canonical_name="沈言",
            tier="核心",
            current={},
            first_appearance=1,
            last_appearance=1,
            is_protagonist=True,
        )
    )
    service.index_manager.upsert_entity(
        EntityMeta(
            id="ally",
            type="角色",
            canonical_name="周岚",
            tier="重要",
            current={},
            first_appearance=1,
            last_appearance=1,
        )
    )


def test_apply_write_data_sync_persists_narrative_state(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    _seed_entities(service)
    task = _create_write_task(service, 1)

    payload = {
        "content": "测试正文" * 300,
        "summary_content": "# 第1章摘要\n\n测试摘要\n",
        "chapter_meta": {"title": "第一章", "location": "雨城观测点", "characters": ["沈言", "周岚"]},
        "foreshadowing_items": [
            {
                "name": "雨夜警报",
                "content": "警报总比异变提前十分钟",
                "planted_chapter": 1,
                "planned_payoff_chapter": 5,
                "owner_entity": "hero",
                "importance": "high",
            }
        ],
        "timeline_events": [
            {
                "chapter": 1,
                "scene_index": 1,
                "location": "雨城观测点",
                "summary": "沈言和周岚确认警报提前出现",
                "participants": ["hero", "ally"],
                "objective_fact": True,
            }
        ],
        "character_arcs": [
            {
                "entity_id": "hero",
                "chapter": 1,
                "desire": "找出警报源",
                "fear": "继续失去记忆",
                "misbelief": "只能独自承担风险",
                "arc_stage": "pressure",
                "relationship_state": {"ally": "试探信任"},
            }
        ],
        "knowledge_states": [
            {
                "entity_id": "hero",
                "chapter": 1,
                "topic": "警报来源",
                "belief": "警报来自观测塔",
                "truth_status": "partial",
                "confidence": 0.7,
            }
        ],
    }

    with patch.object(service, "_validate_writeback_consistency", return_value=None), patch.object(
        service, "_sync_core_setting_docs", return_value=None
    ):
        service._apply_write_data_sync(task["id"], task, payload)

    refreshed = service.store.get_task(task["id"]) or {}
    writeback = (refreshed.get("artifacts") or {}).get("writeback") or {}
    assert writeback["narrative_sync"]["normalized_entries"] == 4
    assert service.narrative_graph.get_active_foreshadowing(before_chapter=1, limit=5)[0]["name"] == "雨夜警报"
    assert service.index_manager.get_recent_timeline_events(chapter=1, window=1, limit=5)[0]["summary"] == "沈言和周岚确认警报提前出现"
    assert service.index_manager.get_entity_knowledge_states("hero", limit=5)[0]["topic"] == "警报来源"


def test_apply_write_data_sync_rolls_back_narrative_state_on_failure(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    _seed_entities(service)
    service.narrative_graph.write_batch(
        foreshadowing_items=[
            {
                "name": "雨夜警报",
                "content": "旧内容",
                "planted_chapter": 1,
                "planned_payoff_chapter": 5,
                "owner_entity": "hero",
            }
        ]
    )
    task = _create_write_task(service, 1)

    payload = {
        "content": "回滚测试正文" * 300,
        "summary_content": "# 第1章摘要\n\n回滚测试\n",
        "chapter_meta": {"title": "第一章", "location": "雨城", "characters": ["沈言"]},
        "foreshadowing_items": [
            {
                "name": "雨夜警报",
                "content": "新内容",
                "planted_chapter": 1,
                "planned_payoff_chapter": 6,
                "owner_entity": "hero",
            }
        ],
    }

    with patch.object(service, "_validate_writeback_consistency", side_effect=ValueError("forced failure")), patch.object(
        service, "_sync_core_setting_docs", return_value=None
    ):
        with pytest.raises(ValueError, match="forced failure"):
            service._apply_write_data_sync(task["id"], task, payload)

    active = service.narrative_graph.get_active_foreshadowing(before_chapter=1, limit=5)
    assert active[0]["content"] == "旧内容"
    assert not (project_root / service._default_chapter_file(1)).exists()
    assert not (project_root / service._default_summary_file(1)).exists()
