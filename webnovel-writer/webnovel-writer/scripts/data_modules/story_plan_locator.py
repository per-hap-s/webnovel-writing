from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def load_story_plan_for_chapter(story_dir: Path, chapter: int) -> Dict[str, Any]:
    if chapter <= 0 or not story_dir.is_dir():
        return {}

    exact_path = story_dir / f"plan-ch{chapter:04d}.json"
    exact_payload = _load_story_plan_payload(exact_path)
    if exact_payload:
        return exact_payload

    candidates: List[Dict[str, Any]] = []
    for path in story_dir.glob("plan-ch*.json"):
        payload = _load_story_plan_payload(path)
        if not payload:
            continue
        slots = [item for item in (payload.get("chapters") or []) if isinstance(item, dict)]
        if not any(int(item.get("chapter") or 0) == chapter for item in slots):
            continue
        try:
            updated_at = path.stat().st_mtime
        except OSError:
            updated_at = 0.0
        candidates.append(
            {
                "payload": payload,
                "anchor_chapter": int(payload.get("anchor_chapter") or 0),
                "updated_at": updated_at,
            }
        )

    if not candidates:
        return {}

    candidates.sort(
        key=lambda item: (
            int(item.get("anchor_chapter") or 0),
            float(item.get("updated_at") or 0.0),
        ),
        reverse=True,
    )
    return candidates[0]["payload"]


def _load_story_plan_payload(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
