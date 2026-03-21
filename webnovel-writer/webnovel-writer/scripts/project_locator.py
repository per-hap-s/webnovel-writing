#!/usr/bin/env python3
"""
Project location helpers for Webnovel Writer.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from runtime_compat import normalize_windows_path


DEFAULT_PROJECT_DIR_NAMES: tuple[str, ...] = ("webnovel-project",)
CURRENT_PROJECT_POINTER_REL: Path = Path(".webnovel") / "current-project"
LEGACY_CURRENT_PROJECT_POINTER_REL: Path = Path(".claude") / ".webnovel-current-project"
GLOBAL_REGISTRY_FILE_NAME = "workspaces.json"
LEGACY_GLOBAL_REGISTRY_REL: Path = Path("webnovel-writer") / GLOBAL_REGISTRY_FILE_NAME

ENV_WEBNOVEL_HOME = "WEBNOVEL_HOME"
ENV_WEBNOVEL_PROJECT_ROOT = "WEBNOVEL_PROJECT_ROOT"
ENV_WEBNOVEL_WORKSPACE_ROOT = "WEBNOVEL_WORKSPACE_ROOT"
ENV_CLAUDE_PROJECT_DIR = "CLAUDE_PROJECT_DIR"
ENV_CLAUDE_HOME = "CLAUDE_HOME"
ENV_WEBNOVEL_CLAUDE_HOME = "WEBNOVEL_CLAUDE_HOME"


def _find_git_root(cwd: Path) -> Optional[Path]:
    for candidate in (cwd, *cwd.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _normcase_path_key(p: Path) -> str:
    try:
        resolved = p.expanduser().resolve()
    except Exception:
        resolved = p.expanduser()
    return os.path.normcase(str(resolved))


def _get_app_home() -> Path:
    raw = os.environ.get(ENV_WEBNOVEL_HOME) or os.environ.get(ENV_WEBNOVEL_CLAUDE_HOME) or os.environ.get(ENV_CLAUDE_HOME)
    if raw:
        try:
            return normalize_windows_path(raw).expanduser().resolve()
        except Exception:
            return normalize_windows_path(raw).expanduser()
    return (Path.home() / ".webnovel").resolve()


def _registry_candidates() -> list[Path]:
    app_home = _get_app_home()
    primary = app_home / GLOBAL_REGISTRY_FILE_NAME
    legacy = app_home / LEGACY_GLOBAL_REGISTRY_REL
    if primary == legacy:
        return [primary]
    return [primary, legacy]


def _primary_registry_path() -> Path:
    return _registry_candidates()[0]


def _default_registry() -> dict:
    return {
        "schema_version": 1,
        "workspaces": {},
        "last_used_project_root": "",
        "updated_at": _now_iso(),
    }


def _normalize_recent_projects(value: object) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    raw_items = value if isinstance(value, list) else []
    seen: set[str] = set()
    for raw in raw_items:
        if isinstance(raw, str):
            project_root = raw.strip()
            last_opened_at = ""
        elif isinstance(raw, dict):
            project_root = str(raw.get("project_root") or "").strip()
            last_opened_at = str(raw.get("last_opened_at") or "").strip()
        else:
            continue
        if not project_root:
            continue
        dedupe_key = os.path.normcase(project_root)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(
            {
                "project_root": project_root,
                "last_opened_at": last_opened_at,
            }
        )
    return items


def _normalize_pinned_project_roots(value: object) -> list[str]:
    raw_items = value if isinstance(value, list) else []
    items: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = str(raw or "").strip()
        if not text:
            continue
        dedupe_key = os.path.normcase(text)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(text)
    return items


def _normalize_workspace_entry(workspace_root: Path, entry: object) -> dict:
    if not isinstance(entry, dict):
        entry = {}
    current_project_root = str(entry.get("current_project_root") or "").strip()
    normalized = dict(entry)
    normalized["workspace_root"] = str(workspace_root)
    normalized["current_project_root"] = current_project_root
    normalized["recent_projects"] = _normalize_recent_projects(entry.get("recent_projects"))
    normalized["pinned_project_roots"] = _normalize_pinned_project_roots(entry.get("pinned_project_roots"))
    normalized["updated_at"] = str(entry.get("updated_at") or "").strip()
    return normalized


def _workspace_key(workspace_root: Path) -> str:
    return _normcase_path_key(workspace_root)


def _resolve_workspace_root(explicit_workspace_root: Optional[str] = None, *, cwd: Optional[Path] = None) -> Path:
    if explicit_workspace_root:
        return normalize_windows_path(explicit_workspace_root).expanduser().resolve()

    env_ws = os.environ.get(ENV_WEBNOVEL_WORKSPACE_ROOT) or os.environ.get(ENV_CLAUDE_PROJECT_DIR)
    if env_ws:
        return normalize_windows_path(env_ws).expanduser().resolve()

    base = (cwd or Path.cwd()).resolve()
    found = _find_workspace_root(base)
    if found is not None:
        return found.resolve()

    git_root = _find_git_root(base)
    if git_root is not None:
        return git_root.resolve()
    return base


def _load_global_registry() -> dict:
    for path in _registry_candidates():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8") or "{}")
        except Exception:
            continue
        if isinstance(data, dict):
            data.setdefault("schema_version", 1)
            data.setdefault("workspaces", {})
            data.setdefault("last_used_project_root", "")
            data.setdefault("updated_at", _now_iso())
            if not isinstance(data["workspaces"], dict):
                data["workspaces"] = {}
            return data
    return _default_registry()


def _save_global_registry(data: dict) -> None:
    path = _primary_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now_iso()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _is_project_root(path: Path) -> bool:
    return (path / ".webnovel" / "state.json").is_file()


def _is_project_root_bootstrap(path: Path) -> bool:
    return (path / ".webnovel").is_dir()


def _candidate_roots(cwd: Path, *, stop_at: Optional[Path] = None) -> Iterable[Path]:
    yield cwd
    for name in DEFAULT_PROJECT_DIR_NAMES:
        yield cwd / name

    for parent in cwd.parents:
        yield parent
        for name in DEFAULT_PROJECT_DIR_NAMES:
            yield parent / name
        if stop_at is not None and parent == stop_at:
            break


def _pointer_candidates(cwd: Path, *, stop_at: Optional[Path] = None) -> Iterable[Path]:
    for candidate in (cwd, *cwd.parents):
        yield candidate / CURRENT_PROJECT_POINTER_REL
        yield candidate / LEGACY_CURRENT_PROJECT_POINTER_REL
        if stop_at is not None and candidate == stop_at:
            break


def _resolve_project_root_from_pointer(cwd: Path, *, stop_at: Optional[Path] = None) -> Optional[Path]:
    for pointer_file in _pointer_candidates(cwd, stop_at=stop_at):
        if not pointer_file.is_file():
            continue
        raw = pointer_file.read_text(encoding="utf-8").strip()
        if not raw:
            continue
        target = normalize_windows_path(raw).expanduser()
        if not target.is_absolute():
            target = (pointer_file.parent / target).resolve()
        if _is_project_root(target):
            return target.resolve()
    return None


def _resolve_project_root_from_global_registry(
    base: Path,
    *,
    workspace_hint: Optional[Path] = None,
    allow_last_used_fallback: bool = False,
) -> Optional[Path]:
    reg = _load_global_registry()
    workspaces = reg.get("workspaces") or {}
    if not isinstance(workspaces, dict) or not workspaces:
        return None

    hints: list[Path] = []
    env_ws = os.environ.get(ENV_WEBNOVEL_WORKSPACE_ROOT) or os.environ.get(ENV_CLAUDE_PROJECT_DIR)
    if env_ws:
        hints.append(normalize_windows_path(env_ws).expanduser())
    if workspace_hint is not None:
        hints.append(workspace_hint)
    hints.append(base)

    for hint in hints:
        key = _normcase_path_key(hint)
        entry = workspaces.get(key)
        if isinstance(entry, dict):
            raw = entry.get("current_project_root")
            if isinstance(raw, str) and raw.strip():
                target = normalize_windows_path(raw).expanduser()
                if target.is_absolute() and _is_project_root(target):
                    return target.resolve()

    for hint in hints:
        hint_key = _normcase_path_key(hint)
        for ws_key, entry in workspaces.items():
            if not isinstance(ws_key, str) or not isinstance(entry, dict):
                continue
            ws_key_norm = os.path.normcase(ws_key)
            if hint_key == ws_key_norm or hint_key.startswith(ws_key_norm.rstrip("\\") + "\\"):
                raw = entry.get("current_project_root")
                if isinstance(raw, str) and raw.strip():
                    target = normalize_windows_path(raw).expanduser()
                    if target.is_absolute() and _is_project_root(target):
                        return target.resolve()

    if allow_last_used_fallback:
        raw = reg.get("last_used_project_root")
        if isinstance(raw, str) and raw.strip():
            target = normalize_windows_path(raw).expanduser()
            if target.is_absolute() and _is_project_root(target):
                return target.resolve()

    return None


def _find_workspace_root(start: Path) -> Optional[Path]:
    for candidate in (start, *start.parents):
        if (candidate / ".webnovel").is_dir() or (candidate / ".claude").is_dir():
            return candidate
    return None


def update_global_registry_current_project(*, workspace_root: Optional[Path], project_root: Path) -> Optional[Path]:
    root = normalize_windows_path(project_root).expanduser()
    try:
        root = root.resolve()
    except Exception:
        root = root
    if not _is_project_root(root):
        raise FileNotFoundError(f"Not a webnovel project root (missing .webnovel/state.json): {root}")

    ws = workspace_root
    if ws is None:
        env_ws = os.environ.get(ENV_WEBNOVEL_WORKSPACE_ROOT) or os.environ.get(ENV_CLAUDE_PROJECT_DIR)
        if env_ws:
            ws = normalize_windows_path(env_ws).expanduser()
    if ws is None:
        return None

    try:
        ws = ws.expanduser().resolve()
    except Exception:
        ws = ws.expanduser()
    register_workspace_project(workspace_root=ws, project_root=root, make_current=True)
    return _primary_registry_path()


def write_current_project_pointer(project_root: Path, *, workspace_root: Optional[Path] = None) -> Optional[Path]:
    root = normalize_windows_path(project_root).expanduser().resolve()
    if not _is_project_root(root):
        raise FileNotFoundError(f"Not a webnovel project root (missing .webnovel/state.json): {root}")

    ws_root = Path(workspace_root).expanduser().resolve() if workspace_root else None
    if ws_root is None:
        env_ws = os.environ.get(ENV_WEBNOVEL_WORKSPACE_ROOT) or os.environ.get(ENV_CLAUDE_PROJECT_DIR)
        if env_ws:
            ws_root = normalize_windows_path(env_ws).expanduser().resolve()
    if ws_root is None:
        ws_root = _find_workspace_root(root)
    if ws_root is None:
        ws_root = root.parent if root.parent != root else None
    if ws_root is None:
        return None

    pointer_file = ws_root / CURRENT_PROJECT_POINTER_REL
    pointer_file.parent.mkdir(parents=True, exist_ok=True)
    pointer_file.write_text(str(root), encoding="utf-8")

    try:
        update_global_registry_current_project(workspace_root=ws_root, project_root=root)
    except Exception:
        pass

    return pointer_file


def clear_current_project_pointer(*, workspace_root: Optional[Path] = None) -> Optional[Path]:
    ws_root = _resolve_workspace_root(str(workspace_root) if workspace_root is not None else None)
    pointer_file = ws_root / CURRENT_PROJECT_POINTER_REL
    if pointer_file.is_file():
        pointer_file.unlink()
        return pointer_file
    return None


def get_workspace_root(explicit_workspace_root: Optional[str] = None, *, cwd: Optional[Path] = None) -> Path:
    return _resolve_workspace_root(explicit_workspace_root, cwd=cwd)


def get_workspace_registry_state(*, workspace_root: Optional[Path] = None) -> dict:
    ws_root = _resolve_workspace_root(str(workspace_root) if workspace_root is not None else None)
    reg = _load_global_registry()
    workspaces = reg.get("workspaces")
    if not isinstance(workspaces, dict):
        workspaces = {}
        reg["workspaces"] = workspaces
    entry = _normalize_workspace_entry(ws_root, workspaces.get(_workspace_key(ws_root)))
    current_root = resolve_workspace_current_project(workspace_root=ws_root)
    if current_root is not None:
        entry["current_project_root"] = str(current_root)
    reg["workspaces"][_workspace_key(ws_root)] = entry
    return {
        "registry_path": str(_primary_registry_path()),
        "workspace_root": str(ws_root),
        "entry": entry,
        "last_used_project_root": str(reg.get("last_used_project_root") or "").strip(),
    }


def resolve_workspace_current_project(*, workspace_root: Optional[Path] = None) -> Optional[Path]:
    ws_root = _resolve_workspace_root(str(workspace_root) if workspace_root is not None else None)
    pointer_file = ws_root / CURRENT_PROJECT_POINTER_REL
    if pointer_file.is_file():
        raw = pointer_file.read_text(encoding="utf-8").strip()
        if raw:
            target = normalize_windows_path(raw).expanduser()
            if not target.is_absolute():
                target = (pointer_file.parent / target).resolve()
            if _is_project_root(target):
                return target.resolve()

    reg = _load_global_registry()
    workspaces = reg.get("workspaces") if isinstance(reg.get("workspaces"), dict) else {}
    entry = _normalize_workspace_entry(ws_root, workspaces.get(_workspace_key(ws_root)))
    current_project_root = str(entry.get("current_project_root") or "").strip()
    if current_project_root:
        target = normalize_windows_path(current_project_root).expanduser()
        if target.is_absolute() and _is_project_root(target):
            return target.resolve()
    return None


def register_workspace_project(
    *,
    workspace_root: Optional[Path],
    project_root: Path,
    make_current: bool = True,
) -> dict:
    ws_root = _resolve_workspace_root(str(workspace_root) if workspace_root is not None else None)
    root = normalize_windows_path(project_root).expanduser().resolve()
    if not _is_project_root(root):
        raise FileNotFoundError(f"Not a webnovel project root (missing .webnovel/state.json): {root}")

    reg = _load_global_registry()
    workspaces = reg.get("workspaces")
    if not isinstance(workspaces, dict):
        workspaces = {}
        reg["workspaces"] = workspaces

    key = _workspace_key(ws_root)
    entry = _normalize_workspace_entry(ws_root, workspaces.get(key))
    now = _now_iso()
    root_text = str(root)
    root_key = os.path.normcase(root_text)

    recent_projects = [
        item
        for item in entry["recent_projects"]
        if os.path.normcase(str(item.get("project_root") or "")) != root_key
    ]
    recent_projects.insert(
        0,
        {
            "project_root": root_text,
            "last_opened_at": now,
        },
    )
    entry["recent_projects"] = recent_projects[:20]
    entry["updated_at"] = now
    if make_current:
        entry["current_project_root"] = root_text
        pointer_file = ws_root / CURRENT_PROJECT_POINTER_REL
        pointer_file.parent.mkdir(parents=True, exist_ok=True)
        pointer_file.write_text(root_text, encoding="utf-8")
    workspaces[key] = entry
    reg["last_used_project_root"] = root_text
    _save_global_registry(reg)
    return entry


def pin_workspace_project(*, workspace_root: Optional[Path], project_root: str) -> dict:
    ws_root = _resolve_workspace_root(str(workspace_root) if workspace_root is not None else None)
    project_text = str(project_root or "").strip()
    if not project_text:
        raise ValueError("project_root is required")

    reg = _load_global_registry()
    workspaces = reg.get("workspaces")
    if not isinstance(workspaces, dict):
        workspaces = {}
        reg["workspaces"] = workspaces
    key = _workspace_key(ws_root)
    entry = _normalize_workspace_entry(ws_root, workspaces.get(key))
    pinned = [
        item
        for item in entry["pinned_project_roots"]
        if os.path.normcase(item) != os.path.normcase(project_text)
    ]
    pinned.insert(0, project_text)
    entry["pinned_project_roots"] = pinned
    entry["updated_at"] = _now_iso()
    workspaces[key] = entry
    _save_global_registry(reg)
    return entry


def unpin_workspace_project(*, workspace_root: Optional[Path], project_root: str) -> dict:
    ws_root = _resolve_workspace_root(str(workspace_root) if workspace_root is not None else None)
    project_text = str(project_root or "").strip()
    if not project_text:
        raise ValueError("project_root is required")

    reg = _load_global_registry()
    workspaces = reg.get("workspaces")
    if not isinstance(workspaces, dict):
        workspaces = {}
        reg["workspaces"] = workspaces
    key = _workspace_key(ws_root)
    entry = _normalize_workspace_entry(ws_root, workspaces.get(key))
    entry["pinned_project_roots"] = [
        item
        for item in entry["pinned_project_roots"]
        if os.path.normcase(item) != os.path.normcase(project_text)
    ]
    entry["updated_at"] = _now_iso()
    workspaces[key] = entry
    _save_global_registry(reg)
    return entry


def remove_workspace_project(*, workspace_root: Optional[Path], project_root: str) -> dict:
    ws_root = _resolve_workspace_root(str(workspace_root) if workspace_root is not None else None)
    project_text = str(project_root or "").strip()
    if not project_text:
        raise ValueError("project_root is required")

    reg = _load_global_registry()
    workspaces = reg.get("workspaces")
    if not isinstance(workspaces, dict):
        workspaces = {}
        reg["workspaces"] = workspaces
    key = _workspace_key(ws_root)
    entry = _normalize_workspace_entry(ws_root, workspaces.get(key))
    project_key = os.path.normcase(project_text)
    entry["recent_projects"] = [
        item
        for item in entry["recent_projects"]
        if os.path.normcase(str(item.get("project_root") or "")) != project_key
    ]
    entry["pinned_project_roots"] = [
        item for item in entry["pinned_project_roots"] if os.path.normcase(item) != project_key
    ]
    if os.path.normcase(str(entry.get("current_project_root") or "")) == project_key:
        entry["current_project_root"] = ""
        clear_current_project_pointer(workspace_root=ws_root)
    entry["updated_at"] = _now_iso()
    workspaces[key] = entry
    if os.path.normcase(str(reg.get("last_used_project_root") or "")) == project_key:
        reg["last_used_project_root"] = ""
    _save_global_registry(reg)
    return entry


def resolve_project_root(explicit_project_root: Optional[str] = None, *, cwd: Optional[Path] = None) -> Path:
    if explicit_project_root:
        root = normalize_windows_path(explicit_project_root).expanduser().resolve()
        if _is_project_root(root) or _is_project_root_bootstrap(root):
            return root

        pointer_root = _resolve_project_root_from_pointer(root, stop_at=_find_git_root(root))
        if pointer_root is not None:
            return pointer_root

        reg_root = _resolve_project_root_from_global_registry(root, workspace_hint=root, allow_last_used_fallback=False)
        if reg_root is not None:
            return reg_root

        for candidate in _candidate_roots(root, stop_at=_find_git_root(root)):
            if _is_project_root(candidate):
                return candidate.resolve()

        if root.is_dir():
            return root
        raise FileNotFoundError(f"Not a webnovel project root (missing .webnovel/state.json): {root}")

    env_root = os.environ.get(ENV_WEBNOVEL_PROJECT_ROOT)
    if env_root:
        root = normalize_windows_path(env_root).expanduser().resolve()
        if _is_project_root(root) or _is_project_root_bootstrap(root) or root.is_dir():
            return root
        raise FileNotFoundError(f"WEBNOVEL_PROJECT_ROOT is set but invalid (missing .webnovel/state.json): {root}")

    base = (cwd or Path.cwd()).resolve()
    git_root = _find_git_root(base)

    pointer_root = _resolve_project_root_from_pointer(base, stop_at=git_root)
    if pointer_root is not None:
        return pointer_root

    allow_last_used = bool(os.environ.get(ENV_WEBNOVEL_WORKSPACE_ROOT) or os.environ.get(ENV_CLAUDE_PROJECT_DIR))
    reg_root = _resolve_project_root_from_global_registry(base, workspace_hint=None, allow_last_used_fallback=allow_last_used)
    if reg_root is not None:
        return reg_root

    for candidate in _candidate_roots(base, stop_at=git_root):
        if _is_project_root(candidate):
            return candidate.resolve()

    raise FileNotFoundError(
        "Unable to locate webnovel project root. Expected `.webnovel/state.json` under the current directory, "
        "a parent directory, or `webnovel-project/`. Run `webnovel init` first or pass --project-root / set "
        "WEBNOVEL_PROJECT_ROOT."
    )


def resolve_state_file(
    explicit_state_file: Optional[str] = None,
    *,
    explicit_project_root: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> Path:
    base = (cwd or Path.cwd()).resolve()
    if explicit_state_file:
        p = Path(explicit_state_file).expanduser()
        return (base / p).resolve() if not p.is_absolute() else p.resolve()

    root = resolve_project_root(explicit_project_root, cwd=base)
    return root / ".webnovel" / "state.json"
