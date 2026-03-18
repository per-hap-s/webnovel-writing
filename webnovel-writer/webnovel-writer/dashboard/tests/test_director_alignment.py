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


def test_writeback_records_director_alignment(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
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
    workflow = {"name": "write", "version": 1, "steps": []}
    task = service.store.create_task("write", {"chapter": 1}, workflow)
    director_brief = {
        "chapter": 1,
        "chapter_goal": "推进雨夜警报主线。",
        "primary_conflict": "沈言必须在记忆继续受损前查出线索。",
        "must_advance_threads": ["雨夜警报"],
        "payoff_targets": ["雨夜警报"],
        "setup_targets": ["观测塔线索"],
        "must_use_entities": ["沈言"],
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
        "content": ("沈言沿着雨夜警报留下的痕迹进入观测塔，确认警报来源并发现下一步入口。") * 20,
        "summary_content": "# 第1章摘要\n\n测试摘要\n",
        "chapter_meta": {"title": "第一章", "location": "观测塔", "characters": ["沈言"]},
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
        service._apply_write_data_sync(task["id"], service.store.get_task(task["id"]) or task, payload)

    refreshed = service.store.get_task(task["id"]) or {}
    alignment = (((refreshed.get("artifacts") or {}).get("writeback") or {}).get("director_alignment") or {})
    assert "payoff:雨夜警报" in alignment["satisfied"]
    assert "setup:观测塔线索" in alignment["satisfied"]
    assert "entity:沈言" in alignment["satisfied"]
    assert "knowledge:警报来源" in alignment["satisfied"]
