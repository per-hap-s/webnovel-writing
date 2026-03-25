# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path

import pytest


TEST_ROOT = Path(__file__).resolve().parents[2]
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from scripts.data_modules.config import DataModulesConfig
from scripts.data_modules.context_manager import ContextManager
from scripts.data_modules.index_manager import EntityMeta, IndexManager
from scripts.data_modules.narrative_graph import NarrativeGraph


@pytest.fixture
def temp_project(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (cfg.webnovel_dir / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "Test Novel", "genre": "xuanhuan"},
                "progress": {"current_chapter": 3, "total_words": 9000},
                "protagonist_state": {"name": "沈言", "location": {"current": "雨城"}},
                "chapter_meta": {},
                "disambiguation_warnings": [],
                "disambiguation_pending": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return cfg


def _seed_narrative_state(cfg: DataModulesConfig) -> None:
    manager = IndexManager(cfg)
    manager.upsert_entity(
        EntityMeta(
            id="hero",
            type="角色",
            canonical_name="沈言",
            tier="核心",
            current={},
            first_appearance=1,
            last_appearance=3,
            is_protagonist=True,
        )
    )
    manager.upsert_entity(
        EntityMeta(
            id="ally",
            type="角色",
            canonical_name="周岚",
            tier="重要",
            current={},
            first_appearance=2,
            last_appearance=3,
        )
    )
    graph = NarrativeGraph(config=cfg, manager=manager)
    graph.write_batch(
        foreshadowing_items=[
            {
                "name": "雨夜警报",
                "content": "每次警报都提前十分钟响起",
                "planted_chapter": 1,
                "planned_payoff_chapter": 5,
                "importance": "high",
                "owner_entity": "hero",
            }
        ],
        timeline_events=[
            {
                "chapter": 3,
                "scene_index": 1,
                "location": "观测点",
                "summary": "沈言和周岚在观测点验证了提前警报",
                "participants": ["hero", "ally"],
                "objective_fact": True,
            }
        ],
        character_arcs=[
            {
                "entity_id": "hero",
                "chapter": 3,
                "desire": "追查警报源头",
                "fear": "失去更多记忆",
                "misbelief": "只能独自承担代价",
                "arc_stage": "pressure",
                "relationship_state": {"ally": "开始信任"},
                "notes": "首次决定让周岚参与调查",
            }
        ],
        knowledge_states=[
            {
                "entity_id": "hero",
                "chapter": 3,
                "topic": "警报来源",
                "belief": "警报来自旧观测塔",
                "truth_status": "partial",
                "confidence": 0.7,
                "evidence": "塔内设备仍在自发运行",
            },
            {
                "entity_id": "ally",
                "chapter": 3,
                "topic": "警报来源",
                "belief": "警报由人为触发",
                "truth_status": "unknown",
                "confidence": 0.6,
                "evidence": "值守记录有人为涂改",
            },
        ],
    )


def test_context_manager_includes_narrative_state_section(temp_project):
    _seed_narrative_state(temp_project)

    manager = ContextManager(temp_project)
    payload = manager.build_context(3, use_snapshot=False, save_snapshot=False)

    assert "narrative_state" in payload["sections"]
    narrative_state = payload["sections"]["narrative_state"]["content"]
    assert narrative_state["active_foreshadowing"][0]["name"] == "雨夜警报"
    assert narrative_state["recent_timeline_events"][0]["summary"] == "沈言和周岚在观测点验证了提前警报"
    assert narrative_state["core_character_arcs"][0]["entity_id"] == "hero"
    assert narrative_state["knowledge_conflicts"][0]["topic"] == "警报来源"


def test_extract_chapter_context_payload_exposes_narrative_state(temp_project):
    _seed_narrative_state(temp_project)

    from extract_chapter_context import _render_text, build_chapter_context_payload

    payload = build_chapter_context_payload(temp_project.project_root, 3)

    assert payload["narrative_state"]["active_foreshadowing"][0]["name"] == "雨夜警报"
    rendered = _render_text(payload)
    assert "叙事状态" in rendered
    assert "活跃伏笔" in rendered

