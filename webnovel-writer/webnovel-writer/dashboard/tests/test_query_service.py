from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dashboard.query_service import DashboardQueryService


@pytest.fixture
def query_project_root(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    conn = sqlite3.connect(str(webnovel_dir / "index.db"))
    conn.execute(
        "CREATE TABLE entities (id TEXT PRIMARY KEY, canonical_name TEXT, type TEXT, is_archived INTEGER DEFAULT 0, last_appearance INTEGER)"
    )
    conn.execute(
        "CREATE TABLE aliases (alias TEXT, entity_id TEXT, entity_type TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute(
        "CREATE TABLE relationships (id INTEGER PRIMARY KEY AUTOINCREMENT, from_entity TEXT, to_entity TEXT, type TEXT, chapter INTEGER)"
    )
    conn.execute(
        "CREATE TABLE relationship_events (id INTEGER PRIMARY KEY AUTOINCREMENT, from_entity TEXT, to_entity TEXT, type TEXT, chapter INTEGER)"
    )
    conn.execute(
        "CREATE TABLE review_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, end_chapter INTEGER, overall_score REAL, created_at TEXT)"
    )
    conn.execute(
        "CREATE TABLE timeline_events (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT, chapter INTEGER, summary TEXT)"
    )
    conn.execute(
        "CREATE TABLE character_arcs (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT, chapter INTEGER, arc_stage TEXT)"
    )
    conn.execute(
        "CREATE TABLE knowledge_states (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT, chapter INTEGER, fact TEXT, state TEXT)"
    )
    conn.commit()
    conn.close()
    return project_root


def _seed_query_data(project_root: Path) -> None:
    conn = sqlite3.connect(str(project_root / ".webnovel" / "index.db"))
    conn.executemany(
        "INSERT INTO entities (id, canonical_name, type, is_archived, last_appearance) VALUES (?, ?, ?, ?, ?)",
        [
            ("hero", "沈砚", "character", 0, 5),
            ("mentor", "沈母", "character", 0, 4),
            ("retired", "旧友", "character", 1, 1),
        ],
    )
    conn.executemany(
        "INSERT INTO aliases (alias, entity_id, entity_type) VALUES (?, ?, ?)",
        [
            ("阿砚", "hero", "character"),
            ("沈姨", "mentor", "character"),
        ],
    )
    conn.execute(
        "INSERT INTO relationships (from_entity, to_entity, type, chapter) VALUES (?, ?, ?, ?)",
        ("hero", "mentor", "family", 4),
    )
    conn.executemany(
        "INSERT INTO relationship_events (from_entity, to_entity, type, chapter) VALUES (?, ?, ?, ?)",
        [
            ("hero", "mentor", "family", 3),
            ("mentor", "hero", "warned_by", 2),
        ],
    )
    conn.execute(
        "INSERT INTO review_metrics (end_chapter, overall_score, created_at) VALUES (?, ?, ?)",
        (4, 92, "2026-03-18T09:59:08+00:00"),
    )
    conn.executemany(
        "INSERT INTO timeline_events (entity_id, chapter, summary) VALUES (?, ?, ?)",
        [
            ("hero", 2, "hero chapter 2"),
            ("ally", 2, "ally chapter 2"),
            ("hero", 4, "hero chapter 4"),
        ],
    )
    conn.executemany(
        "INSERT INTO character_arcs (entity_id, chapter, arc_stage) VALUES (?, ?, ?)",
        [
            ("hero", 1, "hesitant"),
            ("hero", 2, "committed"),
            ("ally", 2, "watching"),
        ],
    )
    conn.executemany(
        "INSERT INTO knowledge_states (entity_id, chapter, fact, state) VALUES (?, ?, ?, ?)",
        [
            ("hero", 1, "secret-a", "suspects"),
            ("hero", 2, "secret-b", "confirmed"),
            ("ally", 2, "secret-a", "unknown"),
        ],
    )
    conn.commit()
    conn.close()


def test_query_service_entities_and_aliases_use_stable_filters(query_project_root: Path):
    _seed_query_data(query_project_root)
    service = DashboardQueryService(query_project_root)

    active_entities = service.list_entities(entity_type="character", include_archived=False)
    all_entities = service.list_entities(entity_type="character", include_archived=True)
    hero_aliases = service.list_aliases(entity="hero")
    all_aliases = service.list_aliases()

    assert [item["id"] for item in active_entities] == ["hero", "mentor"]
    assert [item["id"] for item in all_entities] == ["hero", "mentor", "retired"]
    assert len(hero_aliases) == 1
    assert hero_aliases[0]["alias"] == "阿砚"
    assert hero_aliases[0]["entity_id"] == "hero"
    assert hero_aliases[0]["entity_type"] == "character"
    assert {item["entity_id"] for item in all_aliases} == {"hero", "mentor"}


def test_query_service_relationships_normalize_display_fields(query_project_root: Path):
    _seed_query_data(query_project_root)
    service = DashboardQueryService(query_project_root)

    relationships = service.list_relationships(limit=10)
    events = service.list_relationship_events(limit=10)

    assert relationships[0]["from_entity_display"] == "沈砚"
    assert relationships[0]["to_entity_display"] == "沈母"
    assert relationships[0]["type_label"] == "家庭"
    assert [item["chapter"] for item in events] == [3, 2]


def test_query_service_review_metrics_adds_display_timestamp(query_project_root: Path):
    _seed_query_data(query_project_root)
    service = DashboardQueryService(query_project_root)

    metrics = service.list_review_metrics(limit=5)

    assert metrics[0]["created_at_display"] == "2026-03-18 17:59:08"


def test_query_service_narrative_queries_keep_entity_and_chapter_filters(query_project_root: Path):
    _seed_query_data(query_project_root)
    service = DashboardQueryService(query_project_root)

    timeline = service.list_timeline_events(chapter=2, entity="hero", limit=5)
    arcs = service.list_character_arcs(chapter=2, entity="hero", limit=5)
    knowledge = service.list_knowledge_states(chapter=2, entity="hero", limit=5)

    assert timeline == [{"id": 1, "entity_id": "hero", "chapter": 2, "summary": "hero chapter 2"}]
    assert arcs == [{"id": 2, "entity_id": "hero", "chapter": 2, "arc_stage": "committed"}]
    assert knowledge == [{"id": 2, "entity_id": "hero", "chapter": 2, "fact": "secret-b", "state": "confirmed"}]
