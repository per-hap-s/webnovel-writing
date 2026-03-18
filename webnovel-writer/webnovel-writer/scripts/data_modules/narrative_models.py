#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Narrative state models for first-phase tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ForeshadowingItemMeta:
    """伏笔条目元数据。"""

    name: str
    content: str
    planted_chapter: int
    planned_payoff_chapter: int = 0
    status: str = "active"
    importance: str = "medium"
    owner_entity: str = ""
    payoff_note: str = ""
    payoff_chapter: int = 0


@dataclass
class TimelineEventMeta:
    """时间线事件元数据。"""

    chapter: int
    scene_index: int = 0
    event_time_label: str = ""
    location: str = ""
    summary: str = ""
    participants: List[str] = field(default_factory=list)
    objective_fact: bool = True
    source: str = "data-sync"


@dataclass
class CharacterArcMeta:
    """角色弧线元数据。"""

    entity_id: str
    chapter: int
    desire: str = ""
    fear: str = ""
    misbelief: str = ""
    arc_stage: str = ""
    relationship_state: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""


@dataclass
class KnowledgeStateMeta:
    """角色认知状态元数据。"""

    entity_id: str
    chapter: int
    topic: str
    belief: str
    truth_status: str = "unknown"
    confidence: float = 1.0
    evidence: str = ""
