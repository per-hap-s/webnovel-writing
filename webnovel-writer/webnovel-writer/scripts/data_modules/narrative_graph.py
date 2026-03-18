#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Narrative graph thin wrapper for first-phase narrative state tracking.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Optional, Type, TypeVar

from .index_manager import IndexManager
from .narrative_models import (
    CharacterArcMeta,
    ForeshadowingItemMeta,
    KnowledgeStateMeta,
    TimelineEventMeta,
)


T = TypeVar("T")


class NarrativeGraph:
    """叙事状态图谱的薄封装。"""

    def __init__(self, config=None, manager: Optional[IndexManager] = None):
        self.manager = manager or IndexManager(config=config)

    def _coerce_items(self, items: Optional[Iterable[Any]], meta_cls: Type[T]) -> List[T]:
        records: List[T] = []
        for item in items or []:
            if isinstance(item, meta_cls):
                records.append(item)
                continue
            if is_dataclass(item):
                records.append(meta_cls(**asdict(item)))
                continue
            if isinstance(item, dict):
                records.append(meta_cls(**item))
                continue
            raise TypeError(f"Unsupported narrative item type: {type(item)!r}")
        return records

    def write_batch(
        self,
        foreshadowing_items: Optional[Iterable[Any]] = None,
        timeline_events: Optional[Iterable[Any]] = None,
        character_arcs: Optional[Iterable[Any]] = None,
        knowledge_states: Optional[Iterable[Any]] = None,
    ) -> Dict[str, int]:
        foreshadowing_batch = self._coerce_items(
            foreshadowing_items,
            ForeshadowingItemMeta,
        )
        timeline_batch = self._coerce_items(timeline_events, TimelineEventMeta)
        arc_batch = self._coerce_items(character_arcs, CharacterArcMeta)
        knowledge_batch = self._coerce_items(knowledge_states, KnowledgeStateMeta)

        for item in foreshadowing_batch:
            self.manager.upsert_foreshadowing_item(item)
        for item in timeline_batch:
            self.manager.record_timeline_event(item)
        for item in arc_batch:
            self.manager.save_character_arc(item)
        for item in knowledge_batch:
            self.manager.save_knowledge_state(item)

        return {
            "foreshadowing_items": len(foreshadowing_batch),
            "timeline_events": len(timeline_batch),
            "character_arcs": len(arc_batch),
            "knowledge_states": len(knowledge_batch),
        }

    def get_active_foreshadowing(
        self,
        before_chapter: Optional[int] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return self.manager.list_active_foreshadowing_items(
            before_chapter=before_chapter,
            limit=limit,
        )

    def get_recent_timeline(
        self,
        chapter: Optional[int] = None,
        window: int = 5,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return self.manager.get_recent_timeline_events(
            chapter=chapter,
            window=window,
            limit=limit,
        )

    def get_core_character_arcs(
        self,
        chapter: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return self.manager.get_core_character_arcs(chapter=chapter, limit=limit)

    def get_knowledge_conflicts(
        self,
        chapter: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        return self.manager.get_knowledge_conflicts(chapter=chapter, limit=limit)

    def summarize_for_context(
        self,
        chapter: int,
        max_items: int = 12,
    ) -> Dict[str, Any]:
        limits = [0, 0, 0, 0]
        for index in range(max(0, max_items)):
            limits[index % 4] += 1

        return {
            "chapter": chapter,
            "active_foreshadowing": self.get_active_foreshadowing(
                before_chapter=chapter,
                limit=limits[0],
            )
            if limits[0]
            else [],
            "recent_timeline_events": self.get_recent_timeline(
                chapter=chapter,
                window=5,
                limit=limits[1],
            )
            if limits[1]
            else [],
            "core_character_arcs": self.get_core_character_arcs(
                chapter=chapter,
                limit=limits[2],
            )
            if limits[2]
            else [],
            "knowledge_conflicts": self.get_knowledge_conflicts(
                chapter=chapter,
                limit=limits[3],
            )
            if limits[3]
            else [],
        }
