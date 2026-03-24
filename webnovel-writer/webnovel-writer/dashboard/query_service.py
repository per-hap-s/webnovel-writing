from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from scripts.data_modules.config import get_config
from scripts.data_modules.index_manager import IndexManager


RELATIONSHIP_TYPE_LABELS = {
    "family": "家庭",
    "ally": "同盟",
    "enemy": "敌对",
    "mentor": "师友",
    "subordinate": "上下级",
    "colleague": "同事",
    "suspect": "嫌疑",
    "investigating": "调查",
    "conflict": "冲突",
    "owes": "欠债",
    "protects": "保护",
    "watches": "监视",
    "warned_by": "预警来源",
}


def _format_display_datetime(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _with_display_timestamps(item: dict[str, Any], *, fields: tuple[str, ...]) -> dict[str, Any]:
    enriched = dict(item)
    for field in fields:
        if enriched.get(field):
            enriched[f"{field}_display"] = _format_display_datetime(enriched.get(field))
    return enriched


def _resolve_relationship_entity_display(*, canonical_name: Any, alias: Any, raw_id: Any) -> str:
    raw = str(raw_id or "").strip()
    canonical = str(canonical_name or "").strip()
    alias_text = str(alias or "").strip()
    if canonical and canonical != raw:
        return canonical
    if alias_text:
        return alias_text
    if canonical:
        return canonical
    if raw:
        return raw
    return "-"


def _translate_relationship_type(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    if text in RELATIONSHIP_TYPE_LABELS:
        return RELATIONSHIP_TYPE_LABELS[text]
    fallback = text.replace("_", " / ").replace("-", " / ")
    return f"关系：{fallback}"


class DashboardQueryService:
    """Dashboard 读接口的统一查询与 DTO 归一化层。"""

    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()
        self.manager = IndexManager(get_config(self.project_root))

    def list_entities(
        self,
        *,
        entity_type: Optional[str] = None,
        include_archived: bool = False,
    ) -> list[dict[str, Any]]:
        rows = self.manager.list_entities(entity_type=entity_type, include_archived=include_archived)
        normalized: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            for field in ("is_archived", "is_protagonist"):
                if field in item:
                    item[field] = bool(item.get(field))
            normalized.append(item)
        return normalized

    def get_entity(self, entity_id: str) -> Optional[dict[str, Any]]:
        row = self.manager.get_entity(entity_id)
        if row is None:
            return None
        item = dict(row)
        for field in ("is_archived", "is_protagonist"):
            if field in item:
                item[field] = bool(item.get(field))
        return item

    def list_relationships(self, *, entity: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
        if entity:
            rows = self.manager.get_entity_relationships(entity)
            rows = sorted(rows, key=lambda item: (-int(item.get("chapter") or 0), -int(item.get("id") or 0)))[:limit]
        else:
            rows = self.manager.get_recent_relationships(limit=limit)

        entities = {
            item["id"]: item
            for item in self.manager.list_entities(include_archived=True)
            if item.get("id")
        }
        alias_map: dict[str, str] = {}
        for alias_row in self.manager.list_alias_records():
            entity_id = str(alias_row.get("entity_id") or "").strip()
            alias = str(alias_row.get("alias") or "").strip()
            if entity_id and alias and entity_id not in alias_map:
                alias_map[entity_id] = alias

        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            from_entity = entities.get(str(item.get("from_entity") or "").strip(), {})
            to_entity = entities.get(str(item.get("to_entity") or "").strip(), {})
            item["from_entity_name"] = from_entity.get("canonical_name") or item.get("from_entity")
            item["to_entity_name"] = to_entity.get("canonical_name") or item.get("to_entity")
            item["from_entity_alias"] = alias_map.get(str(item.get("from_entity") or "").strip())
            item["to_entity_alias"] = alias_map.get(str(item.get("to_entity") or "").strip())
            item["from_entity_display"] = _resolve_relationship_entity_display(
                canonical_name=item.get("from_entity_name"),
                alias=item.get("from_entity_alias"),
                raw_id=item.get("from_entity"),
            )
            item["to_entity_display"] = _resolve_relationship_entity_display(
                canonical_name=item.get("to_entity_name"),
                alias=item.get("to_entity_alias"),
                raw_id=item.get("to_entity"),
            )
            item["type_label"] = _translate_relationship_type(item.get("type"))
            item["from_entity_label"] = "起始实体"
            item["to_entity_label"] = "目标实体"
            item["type_label_label"] = "关系类型"
            items.append(item)
        return items

    def list_relationship_events(
        self,
        *,
        entity: Optional[str] = None,
        from_chapter: Optional[int] = None,
        to_chapter: Optional[int] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self.manager.list_relationship_events(
            entity_id=entity,
            from_chapter=from_chapter,
            to_chapter=to_chapter,
            limit=limit,
        )

    def list_chapters(self) -> list[dict[str, Any]]:
        return self.manager.list_chapters()

    def list_scenes(self, *, chapter: Optional[int] = None, limit: int = 500) -> list[dict[str, Any]]:
        return self.manager.list_scenes(chapter=chapter, limit=limit)

    def list_reading_power(self, *, limit: int = 50) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self.manager.get_recent_reading_power(limit=limit):
            item = dict(row)
            if "is_transition" in item:
                item["is_transition"] = bool(item.get("is_transition"))
            items.append(item)
        return items

    def list_review_metrics(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            _with_display_timestamps(dict(row), fields=("created_at",))
            for row in self.manager.get_recent_review_metrics(limit=limit)
        ]

    def list_state_changes(self, *, entity: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        if entity:
            return self.manager.get_entity_state_changes(entity, limit=limit)
        return self.manager.get_recent_state_changes(limit=limit)

    def list_aliases(self, *, entity: Optional[str] = None) -> list[dict[str, Any]]:
        return [dict(row) for row in self.manager.list_alias_records(entity_id=entity)]

    def list_invalid_facts(self, *, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        return [dict(row) for row in self.manager.list_invalid_facts(status=status)[:limit]]

    def list_checklist_scores(self, *, limit: int = 100) -> list[dict[str, Any]]:
        return [dict(row) for row in self.manager.get_recent_writing_checklist_scores(limit=limit)]

    def list_timeline_events(
        self,
        *,
        chapter: Optional[int] = None,
        entity: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.manager.list_timeline_events(chapter=chapter, entity_id=entity, limit=limit)

    def list_character_arcs(
        self,
        *,
        chapter: Optional[int] = None,
        entity: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.manager.list_character_arcs(chapter=chapter, entity_id=entity, limit=limit)

    def list_knowledge_states(
        self,
        *,
        chapter: Optional[int] = None,
        entity: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.manager.list_knowledge_states(chapter=chapter, entity_id=entity, limit=limit)
