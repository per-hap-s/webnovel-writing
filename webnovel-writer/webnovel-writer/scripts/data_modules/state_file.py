from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable

from filelock import FileLock

from scripts.security_utils import atomic_write_json


class ProjectStateError(RuntimeError):
    """Base exception for project state access errors."""


class ProjectStateNotFoundError(ProjectStateError, FileNotFoundError):
    """Raised when `.webnovel/state.json` is missing."""


class ProjectStateCorruptedError(ProjectStateError):
    """Raised when `.webnovel/state.json` cannot be decoded."""


StateMutator = Callable[[dict[str, Any]], dict[str, Any] | None]


def project_state_path(project_root: str | Path) -> Path:
    return Path(project_root).resolve() / ".webnovel" / "state.json"


def read_project_state(project_root: str | Path, *, strict: bool = True) -> dict[str, Any]:
    state_path = project_state_path(project_root)
    if not state_path.is_file():
        if strict:
            raise ProjectStateNotFoundError(f"state.json not found: {state_path}")
        return {}
    return _read_state_file(state_path)


def update_project_state(project_root: str | Path, mutator: StateMutator, *, strict: bool = True) -> dict[str, Any]:
    state_path = project_state_path(project_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(state_path.with_suffix(state_path.suffix + ".lock")), timeout=10)
    with lock:
        current_state = _read_state_file(state_path, strict=strict)
        next_state = copy.deepcopy(current_state)
        result = mutator(next_state)
        if result is not None:
            next_state = result
        if not isinstance(next_state, dict):
            raise ProjectStateError("project state mutator must return a dict or mutate in place")
        if next_state == current_state:
            return current_state
        atomic_write_json(state_path, next_state, use_lock=False, backup=True)
        return next_state


def _read_state_file(state_path: Path, *, strict: bool = True) -> dict[str, Any]:
    if not state_path.is_file():
        if strict:
            raise ProjectStateNotFoundError(f"state.json not found: {state_path}")
        return {}
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ProjectStateCorruptedError(f"state.json is corrupted: {state_path}") from exc
    if not isinstance(payload, dict):
        raise ProjectStateCorruptedError(f"state.json root must be an object: {state_path}")
    return payload


def _alias_module_name() -> None:
    module = sys.modules.get(__name__)
    if module is None:
        return
    if __name__.startswith("scripts.data_modules"):
        alias = __name__.replace("scripts.data_modules", "data_modules", 1)
    elif __name__.startswith("data_modules"):
        alias = __name__.replace("data_modules", "scripts.data_modules", 1)
    else:
        return
    sys.modules.setdefault(alias, module)


_alias_module_name()
