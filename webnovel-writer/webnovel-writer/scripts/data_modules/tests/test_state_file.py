from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.data_modules.state_file import (
    ProjectStateCorruptedError,
    read_project_state,
    update_project_state,
)


def make_project(tmp_path: Path, payload: dict | str) -> Path:
    project_root = tmp_path / "novel"
    state_dir = project_root / ".webnovel"
    state_dir.mkdir(parents=True)
    state_path = state_dir / "state.json"
    if isinstance(payload, str):
        state_path.write_text(payload, encoding="utf-8")
    else:
        state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return project_root


def test_read_project_state_raises_for_corrupted_json(tmp_path: Path):
    project_root = make_project(tmp_path, "{broken json")

    with pytest.raises(ProjectStateCorruptedError):
        read_project_state(project_root)


def test_update_project_state_preserves_unrelated_fields(tmp_path: Path):
    project_root = make_project(
        tmp_path,
        {
            "project_info": {"title": "Test"},
            "progress": {"current_chapter": 8},
            "chapter_meta": {"8": {"title": "Current"}},
        },
    )

    def mutate(state_data: dict) -> None:
        planning = state_data.setdefault("planning", {})
        planning["profile"] = {"volume_1_title": "Volume 1"}

    updated = update_project_state(project_root, mutate)

    assert updated["planning"]["profile"]["volume_1_title"] == "Volume 1"
    assert updated["progress"]["current_chapter"] == 8
    assert updated["chapter_meta"]["8"]["title"] == "Current"


def test_sequential_updates_do_not_clobber_previous_changes(tmp_path: Path):
    project_root = make_project(
        tmp_path,
        {
            "project_info": {"title": "Test"},
            "progress": {"current_chapter": 3},
        },
    )

    update_project_state(
        project_root,
        lambda state_data: state_data.setdefault("planning", {}).update({"profile": {"volume_1_title": "Volume 1"}}),
    )
    update_project_state(
        project_root,
        lambda state_data: state_data.setdefault("chapter_meta", {}).update({"3": {"title": "Chapter 3"}}),
    )

    payload = read_project_state(project_root)
    assert payload["planning"]["profile"]["volume_1_title"] == "Volume 1"
    assert payload["chapter_meta"]["3"]["title"] == "Chapter 3"
    assert payload["progress"]["current_chapter"] == 3
