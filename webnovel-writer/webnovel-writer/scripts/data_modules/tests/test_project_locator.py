#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def test_resolve_project_root_prefers_cwd_project(tmp_path):
    _ensure_scripts_on_path()

    from project_locator import resolve_project_root

    project_root = tmp_path / 'workspace'
    (project_root / '.webnovel').mkdir(parents=True, exist_ok=True)
    (project_root / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')

    resolved = resolve_project_root(cwd=project_root)
    assert resolved == project_root.resolve()


def test_resolve_project_root_stops_at_git_root(tmp_path):
    _ensure_scripts_on_path()

    from project_locator import resolve_project_root

    repo_root = tmp_path / 'repo'
    (repo_root / '.git').mkdir(parents=True, exist_ok=True)

    nested = repo_root / 'sub' / 'dir'
    nested.mkdir(parents=True, exist_ok=True)

    outside_project = tmp_path / 'outside_project'
    (outside_project / '.webnovel').mkdir(parents=True, exist_ok=True)
    (outside_project / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')

    try:
        resolve_project_root(cwd=nested)
        assert False, 'Expected FileNotFoundError when only parent outside git root has project'
    except FileNotFoundError:
        pass


def test_resolve_project_root_finds_default_subdir_within_git_root(tmp_path):
    _ensure_scripts_on_path()

    from project_locator import resolve_project_root

    repo_root = tmp_path / 'repo'
    (repo_root / '.git').mkdir(parents=True, exist_ok=True)

    default_project = repo_root / 'webnovel-project'
    (default_project / '.webnovel').mkdir(parents=True, exist_ok=True)
    (default_project / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')

    nested = repo_root / 'sub' / 'dir'
    nested.mkdir(parents=True, exist_ok=True)

    resolved = resolve_project_root(cwd=nested)
    assert resolved == default_project.resolve()


def test_resolve_project_root_uses_new_workspace_pointer(tmp_path):
    _ensure_scripts_on_path()

    from project_locator import resolve_project_root, write_current_project_pointer

    workspace = tmp_path / 'workspace'
    workspace.mkdir(parents=True, exist_ok=True)

    project_root = workspace / 'novel'
    (project_root / '.webnovel').mkdir(parents=True, exist_ok=True)
    (project_root / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')

    pointer_file = write_current_project_pointer(project_root, workspace_root=workspace)
    assert pointer_file is not None
    assert pointer_file == workspace / '.webnovel' / 'current-project'
    assert pointer_file.is_file()

    resolved = resolve_project_root(cwd=workspace)
    assert resolved == project_root.resolve()


def test_resolve_project_root_uses_legacy_pointer_for_compatibility(tmp_path):
    _ensure_scripts_on_path()

    from project_locator import resolve_project_root

    workspace = tmp_path / 'workspace'
    (workspace / '.claude').mkdir(parents=True, exist_ok=True)

    project_root = workspace / 'legacy-novel'
    (project_root / '.webnovel').mkdir(parents=True, exist_ok=True)
    (project_root / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')
    (workspace / '.claude' / '.webnovel-current-project').write_text(str(project_root), encoding='utf-8')

    resolved = resolve_project_root(cwd=workspace)
    assert resolved == project_root.resolve()


def test_registry_uses_webnovel_home(tmp_path, monkeypatch):
    _ensure_scripts_on_path()

    from project_locator import update_global_registry_current_project, write_current_project_pointer

    workspace = tmp_path / 'workspace'
    workspace.mkdir()
    project_root = workspace / 'novel'
    (project_root / '.webnovel').mkdir(parents=True, exist_ok=True)
    (project_root / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')

    app_home = tmp_path / 'app-home'
    monkeypatch.setenv('WEBNOVEL_HOME', str(app_home))

    pointer = write_current_project_pointer(project_root, workspace_root=workspace)
    registry = update_global_registry_current_project(workspace_root=workspace, project_root=project_root)

    assert pointer == workspace / '.webnovel' / 'current-project'
    assert registry == app_home / 'workspaces.json'
    assert registry.is_file()
    assert 'current_project_root' in registry.read_text(encoding='utf-8')


def test_resolve_project_root_uses_webnovel_project_root_env(tmp_path, monkeypatch):
    _ensure_scripts_on_path()

    from project_locator import resolve_project_root

    project_root = tmp_path / 'novel'
    (project_root / '.webnovel').mkdir(parents=True, exist_ok=True)
    (project_root / '.webnovel' / 'state.json').write_text('{}', encoding='utf-8')

    monkeypatch.setenv('WEBNOVEL_PROJECT_ROOT', str(project_root))
    resolved = resolve_project_root(cwd=tmp_path)
    assert resolved == project_root.resolve()
    monkeypatch.delenv('WEBNOVEL_PROJECT_ROOT', raising=False)
