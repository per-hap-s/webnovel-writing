from __future__ import annotations

import json
import threading
import time
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


def test_update_project_state_noop_does_not_rewrite_state_file(tmp_path: Path):
    project_root = make_project(
        tmp_path,
        {
            "project_info": {"title": "Test"},
            "progress": {"current_chapter": 4, "total_words": 1200},
        },
    )
    state_path = project_root / ".webnovel" / "state.json"
    original_content = state_path.read_text(encoding="utf-8")
    original_mtime_ns = state_path.stat().st_mtime_ns

    time.sleep(0.05)
    updated = update_project_state(project_root, lambda state_data: None)

    assert updated["progress"]["current_chapter"] == 4
    assert state_path.read_text(encoding="utf-8") == original_content
    assert state_path.stat().st_mtime_ns == original_mtime_ns


def test_update_project_state_serializes_concurrent_writes_without_losing_changes(tmp_path: Path):
    project_root = make_project(
        tmp_path,
        {
            "project_info": {"title": "Test"},
            "progress": {"current_chapter": 1, "total_words": 100},
        },
    )

    first_entered = threading.Event()
    allow_first = threading.Event()

    def slow_increment(state_data: dict) -> None:
        first_entered.set()
        allow_first.wait(timeout=2)
        state_data["progress"]["current_chapter"] = int(state_data["progress"]["current_chapter"]) + 1

    def fast_increment(state_data: dict) -> None:
        state_data["progress"]["total_words"] = int(state_data["progress"]["total_words"]) + 50

    first_result: dict | None = None
    second_result: dict | None = None

    def run_first() -> None:
        nonlocal first_result
        first_result = update_project_state(project_root, slow_increment)

    def run_second() -> None:
        nonlocal second_result
        second_result = update_project_state(project_root, fast_increment)

    thread_one = threading.Thread(target=run_first)
    thread_two = threading.Thread(target=run_second)
    thread_one.start()
    first_entered.wait(timeout=2)
    thread_two.start()
    time.sleep(0.05)
    allow_first.set()
    thread_one.join(timeout=2)
    thread_two.join(timeout=2)

    assert thread_one.is_alive() is False
    assert thread_two.is_alive() is False
    assert first_result is not None
    assert second_result is not None

    payload = read_project_state(project_root)
    assert payload["progress"]["current_chapter"] == 2
    assert payload["progress"]["total_words"] == 150


def test_update_project_state_leaves_state_file_untouched_when_mutator_raises(tmp_path: Path):
    project_root = make_project(
        tmp_path,
        {
            "project_info": {"title": "Test"},
            "progress": {"current_chapter": 6, "total_words": 2400},
        },
    )
    state_path = project_root / ".webnovel" / "state.json"
    original_content = state_path.read_text(encoding="utf-8")

    def boom(state_data: dict) -> None:
        state_data["progress"]["current_chapter"] = 7
        raise RuntimeError("mutation failed")

    with pytest.raises(RuntimeError):
        update_project_state(project_root, boom)

    assert state_path.read_text(encoding="utf-8") == original_content
    payload = read_project_state(project_root)
    assert payload["progress"]["current_chapter"] == 6
    assert payload["progress"]["total_words"] == 2400
