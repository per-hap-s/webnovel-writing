from __future__ import annotations

import sqlite3

import pytest

from scripts.data_modules.config import DataModulesConfig
from scripts.data_modules.index_manager import EntityMeta, IndexManager


@pytest.fixture
def temp_project(tmp_path):
    config = DataModulesConfig.from_project_root(tmp_path)
    config.ensure_dirs()
    return config


def test_index_manager_exposes_query_read_methods_for_dashboard(temp_project):
    manager = IndexManager(temp_project)
    manager.upsert_entity(
        EntityMeta(
            id="hero",
            type="角色",
            canonical_name="沈砚",
            tier="核心",
            current={},
            first_appearance=1,
            last_appearance=3,
            is_protagonist=True,
        )
    )
    manager.upsert_entity(
        EntityMeta(
            id="retired",
            type="角色",
            canonical_name="旧友",
            tier="次要",
            current={},
            first_appearance=1,
            last_appearance=1,
            is_archived=True,
        )
    )
    manager.register_alias("阿砚", "hero", "角色")

    with sqlite3.connect(temp_project.index_db) as conn:
        conn.execute(
            "INSERT INTO relationship_events (from_entity, to_entity, type, chapter) VALUES (?, ?, ?, ?)",
            ("hero", "retired", "ally", 2),
        )
        conn.execute(
            "INSERT INTO timeline_events (chapter, scene_index, summary, participants, objective_fact, source) VALUES (?, ?, ?, ?, ?, ?)",
            (2, 1, "hero timeline", "[\"hero\"]", 1, "test"),
        )
        conn.execute(
            "INSERT INTO character_arcs (entity_id, chapter, arc_stage, relationship_state_json) VALUES (?, ?, ?, ?)",
            ("hero", 2, "committed", "{}"),
        )
        conn.execute(
            "INSERT INTO knowledge_states (entity_id, chapter, topic, belief, truth_status, confidence, evidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("hero", 2, "secret", "confirmed", "true", 1.0, ""),
        )
        conn.commit()

    all_entities = manager.list_entities(include_archived=True)
    active_entities = manager.list_entities(entity_type="角色", include_archived=False)
    aliases = manager.list_alias_records()
    relationship_events = manager.list_relationship_events(limit=5)
    timeline = manager.list_timeline_events(chapter=2, entity_id="hero", limit=5)
    arcs = manager.list_character_arcs(chapter=2, entity_id="hero", limit=5)
    knowledge = manager.list_knowledge_states(chapter=2, entity_id="hero", limit=5)

    assert [item["id"] for item in all_entities] == ["hero", "retired"]
    assert [item["id"] for item in active_entities] == ["hero"]
    assert len(aliases) == 1
    assert aliases[0]["alias"] == "阿砚"
    assert aliases[0]["entity_id"] == "hero"
    assert aliases[0]["entity_type"] == "角色"
    assert relationship_events[0]["chapter"] == 2
    assert timeline[0]["summary"] == "hero timeline"
    assert arcs[0]["arc_stage"] == "committed"
    assert knowledge[0]["topic"] == "secret"
