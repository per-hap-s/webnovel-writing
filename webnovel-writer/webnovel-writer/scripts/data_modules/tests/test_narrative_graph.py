#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import sys
from pathlib import Path

import pytest

TEST_ROOT = Path(__file__).resolve().parents[2]
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from scripts.data_modules.config import DataModulesConfig
from scripts.data_modules.index_manager import EntityMeta, IndexManager
from scripts.data_modules.narrative_graph import NarrativeGraph
from scripts.data_modules.narrative_models import (
    CharacterArcMeta,
    ForeshadowingItemMeta,
    KnowledgeStateMeta,
    TimelineEventMeta,
)


@pytest.fixture
def temp_project(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    return cfg


def test_index_manager_narrative_tables_and_crud(temp_project):
    manager = IndexManager(temp_project)

    with sqlite3.connect(temp_project.index_db) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "foreshadowing_items" in tables
    assert "timeline_events" in tables
    assert "character_arcs" in tables
    assert "knowledge_states" in tables

    manager.upsert_entity(
        EntityMeta(
            id="hero",
            type="角色",
            canonical_name="主角",
            tier="核心",
            current={},
            first_appearance=1,
            last_appearance=3,
            is_protagonist=True,
        )
    )
    manager.upsert_entity(
        EntityMeta(
            id="mentor",
            type="角色",
            canonical_name="师父",
            tier="重要",
            current={},
            first_appearance=1,
            last_appearance=3,
        )
    )

    manager.upsert_foreshadowing_item(
        ForeshadowingItemMeta(
            name="玉佩裂纹",
            content="玉佩出现新的裂纹，暗示封印松动。",
            planted_chapter=1,
            planned_payoff_chapter=8,
            importance="high",
            owner_entity="hero",
        )
    )
    event_id = manager.record_timeline_event(
        TimelineEventMeta(
            chapter=3,
            scene_index=2,
            event_time_label="夜晚",
            location="山门",
            summary="主角夜探山门禁地。",
            participants=["hero", "mentor"],
            objective_fact=True,
        )
    )
    manager.save_character_arc(
        CharacterArcMeta(
            entity_id="hero",
            chapter=3,
            desire="证明自己",
            fear="再次失败",
            misbelief="只要变强就能解决一切",
            arc_stage="refusal",
            relationship_state={"mentor": "疏离"},
            notes="仍在抗拒求助。",
        )
    )
    manager.save_knowledge_state(
        KnowledgeStateMeta(
            entity_id="hero",
            chapter=3,
            topic="禁地真相",
            belief="禁地里藏着提升境界的秘宝",
            truth_status="false",
            confidence=0.9,
            evidence="从流言推断",
        )
    )
    manager.save_knowledge_state(
        KnowledgeStateMeta(
            entity_id="mentor",
            chapter=3,
            topic="禁地真相",
            belief="禁地里封着会反噬的旧阵眼",
            truth_status="true",
            confidence=0.8,
            evidence="亲历封阵",
        )
    )

    active_items = manager.list_active_foreshadowing_items(before_chapter=3, limit=5)
    assert active_items[0]["name"] == "玉佩裂纹"

    timeline = manager.get_recent_timeline_events(chapter=3, window=2, limit=5)
    assert timeline[0]["id"] == event_id
    assert timeline[0]["participants"] == ["hero", "mentor"]
    assert timeline[0]["objective_fact"] is True

    arcs = manager.get_core_character_arcs(chapter=3, limit=5)
    assert arcs[0]["entity_id"] == "hero"
    assert arcs[0]["relationship_state_json"]["mentor"] == "疏离"

    conflicts = manager.get_knowledge_conflicts(chapter=3, limit=5)
    assert conflicts[0]["topic"] == "禁地真相"
    assert conflicts[0]["has_falsehood"] is True
    assert len(conflicts[0]["beliefs"]) == 2

    assert manager.mark_foreshadowing_paid_off("玉佩裂纹", chapter=9, payoff_note="裂纹彻底打开阵眼。")
    assert manager.list_active_foreshadowing_items(before_chapter=9, limit=5) == []


def test_narrative_graph_write_batch_and_context_summary(temp_project):
    graph = NarrativeGraph(config=temp_project)

    graph.manager.upsert_entity(
        EntityMeta(
            id="hero",
            type="角色",
            canonical_name="主角",
            tier="核心",
            current={},
            first_appearance=1,
            last_appearance=6,
            is_protagonist=True,
        )
    )
    graph.manager.upsert_entity(
        EntityMeta(
            id="ally",
            type="角色",
            canonical_name="同伴",
            tier="重要",
            current={},
            first_appearance=2,
            last_appearance=6,
        )
    )

    counts = graph.write_batch(
        foreshadowing_items=[
            {
                "name": "断刃共鸣",
                "content": "断刃在靠近遗迹时会微微震颤。",
                "planted_chapter": 2,
                "planned_payoff_chapter": 6,
                "importance": "high",
                "owner_entity": "hero",
            },
            {
                "name": "旧地图残页",
                "content": "残页上的路线与遗迹机关对应。",
                "planted_chapter": 3,
                "planned_payoff_chapter": 7,
                "importance": "medium",
                "owner_entity": "ally",
            },
        ],
        timeline_events=[
            TimelineEventMeta(
                chapter=5,
                scene_index=1,
                location="古道",
                summary="主角和同伴在古道遭遇追兵。",
                participants=["hero", "ally"],
            ),
            TimelineEventMeta(
                chapter=6,
                scene_index=3,
                location="遗迹外层",
                summary="两人突破遗迹外层机关。",
                participants=["hero", "ally"],
            ),
        ],
        character_arcs=[
            {
                "entity_id": "hero",
                "chapter": 6,
                "desire": "进入遗迹核心",
                "fear": "拖累同伴",
                "misbelief": "必须独自背负风险",
                "arc_stage": "pressure",
                "relationship_state": {"ally": "依赖但嘴硬"},
                "notes": "开始显露信任裂缝。",
            }
        ],
        knowledge_states=[
            {
                "entity_id": "hero",
                "chapter": 6,
                "topic": "遗迹入口",
                "belief": "入口只能靠断刃打开",
                "truth_status": "partial",
                "confidence": 0.7,
                "evidence": "断刃持续共鸣",
            },
            {
                "entity_id": "ally",
                "chapter": 6,
                "topic": "遗迹入口",
                "belief": "入口需要断刃和地图残页一起触发",
                "truth_status": "true",
                "confidence": 0.8,
                "evidence": "残页边缘有机关图示",
            },
        ],
    )

    assert counts == {
        "foreshadowing_items": 2,
        "timeline_events": 2,
        "character_arcs": 1,
        "knowledge_states": 2,
    }

    summary = graph.summarize_for_context(chapter=6, max_items=6)
    assert summary["chapter"] == 6
    assert set(summary) == {
        "chapter",
        "active_foreshadowing",
        "recent_timeline_events",
        "core_character_arcs",
        "knowledge_conflicts",
    }
    assert len(summary["active_foreshadowing"]) <= 2
    assert len(summary["recent_timeline_events"]) <= 2
    assert len(summary["core_character_arcs"]) <= 1
    assert len(summary["knowledge_conflicts"]) <= 1
    assert summary["knowledge_conflicts"][0]["topic"] == "遗迹入口"

