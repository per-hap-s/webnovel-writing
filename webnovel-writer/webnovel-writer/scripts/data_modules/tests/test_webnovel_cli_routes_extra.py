#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _ensure_scripts_on_path() -> None:
    scripts_dir = Path(__file__).resolve().parents[2]
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))


def _load_module():
    _ensure_scripts_on_path()
    import scripts.data_modules.webnovel as webnovel_module

    return webnovel_module


def test_strip_project_root_args_removes_both_forms():
    module = _load_module()

    argv = [
        'stats',
        '--project-root',
        'C:/book',
        '--project-root=D:/other',
        '--limit',
        '5',
    ]

    assert module._strip_project_root_args(argv) == ['stats', '--limit', '5']


def test_run_data_module_returns_main_return_value(monkeypatch):
    module = _load_module()

    def _fake_main():
        return 5

    fake_mod = SimpleNamespace(main=_fake_main)
    monkeypatch.setattr(module.importlib, 'import_module', lambda name: fake_mod)

    result = module._run_data_module('rag_adapter', ['search', '--query', 'x'])

    assert result == 5


@pytest.mark.parametrize('exit_code', [None, 7])
def test_run_data_module_invokes_main_and_restores_argv(monkeypatch, exit_code):
    module = _load_module()
    original_argv = list(sys.argv)
    captured = {}

    def _fake_main():
        captured['argv'] = list(sys.argv)
        if exit_code is not None:
            raise SystemExit(exit_code)

    fake_mod = SimpleNamespace(main=_fake_main)
    monkeypatch.setattr(module.importlib, 'import_module', lambda name: fake_mod)

    result = module._run_data_module('index_manager', ['--project-root', 'C:/book', 'stats'])

    assert result == (0 if exit_code is None else exit_code)
    assert captured['argv'] == ['data_modules.index_manager', '--project-root', 'C:/book', 'stats']
    assert sys.argv == original_argv


def test_run_script_uses_subprocess_and_return_code(monkeypatch, tmp_path):
    module = _load_module()
    script_path = tmp_path / 'workflow_manager.py'
    script_path.write_text("print('ok')", encoding='utf-8')
    called = {}

    monkeypatch.setattr(module, '_scripts_dir', lambda: tmp_path)

    def _fake_run(cmd):
        called['cmd'] = list(cmd)
        return SimpleNamespace(returncode=3)

    monkeypatch.setattr(module.subprocess, 'run', _fake_run)

    result = module._run_script('workflow_manager.py', ['--project-root', 'C:/book', 'detect'])

    assert result == 3
    assert called['cmd'] == [sys.executable, str(script_path), '--project-root', 'C:/book', 'detect']


def test_cmd_where_prints_resolved_root(monkeypatch, capsys, tmp_path):
    module = _load_module()
    expected_root = (tmp_path / 'book').resolve()
    monkeypatch.setattr(module, '_resolve_root', lambda explicit: expected_root)

    result = module.cmd_where(argparse.Namespace(project_root=str(tmp_path)))

    assert result == 0
    assert capsys.readouterr().out.strip() == str(expected_root)


def test_cmd_use_prints_pointer_and_registry(monkeypatch, capsys, tmp_path):
    module = _load_module()
    project_root = (tmp_path / 'book').resolve()
    workspace_root = (tmp_path / 'workspace').resolve()
    pointer_file = workspace_root / '.webnovel' / 'current-project'
    registry_file = tmp_path / 'workspaces.json'

    monkeypatch.setattr(module, 'write_current_project_pointer', lambda project_root, workspace_root=None: pointer_file)
    monkeypatch.setattr(module, 'update_global_registry_current_project', lambda workspace_root, project_root: registry_file)

    result = module.cmd_use(argparse.Namespace(project_root=str(project_root), workspace_root=str(workspace_root)))

    output = capsys.readouterr().out
    assert result == 0
    assert f'workspace pointer: {pointer_file}' in output
    assert f'global registry: {registry_file}' in output


def test_main_runs_dashboard_module(monkeypatch, tmp_path):
    module = _load_module()
    book_root = (tmp_path / 'book').resolve()
    called = {}

    monkeypatch.setattr(module, '_resolve_root', lambda explicit: book_root)
    def _fake_run_dashboard(argv):
        called['argv'] = list(argv)
        return 0

    monkeypatch.setattr(module, '_run_dashboard', _fake_run_dashboard)
    monkeypatch.setattr(sys, 'argv', ['webnovel', '--project-root', str(tmp_path), 'dashboard', '--no-browser'])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert int(exc.value.code or 0) == 0
    assert called['argv'] == ['--project-root', str(book_root), '--host', '127.0.0.1', '--port', '8765', '--no-browser']


@pytest.mark.parametrize(
    ('tool', 'payload_key', 'payload_value'),
    [
        ('plan', 'volume', '1'),
        ('review', 'chapter_range', '1-3'),
    ],
)
def test_main_runs_workflow_tasks(monkeypatch, tmp_path, tool, payload_key, payload_value):
    module = _load_module()
    book_root = (tmp_path / 'book').resolve()
    called = {}

    monkeypatch.setattr(module, '_resolve_root', lambda explicit: book_root)

    def _fake_run_task_sync(task_type, project_root, request):
        called['task_type'] = task_type
        called['project_root'] = project_root
        called['request'] = request
        return 0

    monkeypatch.setattr(module, '_run_task_sync', _fake_run_task_sync)
    monkeypatch.setattr(sys, 'argv', ['webnovel', '--project-root', str(tmp_path), tool, payload_value])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert int(exc.value.code or 0) == 0
    assert called['task_type'] == tool
    assert called['project_root'] == book_root
    assert called['request'][payload_key] == payload_value


def test_main_runs_write_with_auto_approval_default(monkeypatch, tmp_path):
    module = _load_module()
    book_root = (tmp_path / 'book').resolve()
    called = {}

    monkeypatch.setattr(module, '_resolve_root', lambda explicit: book_root)

    def _fake_run_task_sync(task_type, project_root, request):
        called['task_type'] = task_type
        called['request'] = request
        return 0

    monkeypatch.setattr(module, '_run_task_sync', _fake_run_task_sync)
    monkeypatch.setattr(sys, 'argv', ['webnovel', '--project-root', str(tmp_path), 'write', '12'])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert int(exc.value.code or 0) == 0
    assert called['task_type'] == 'write'
    assert called['request']['chapter'] == 12
    assert called['request']['require_manual_approval'] is False


def test_main_forwards_query_to_status_reporter(monkeypatch, tmp_path):
    module = _load_module()
    book_root = (tmp_path / 'book').resolve()
    called = {}

    monkeypatch.setattr(module, '_resolve_root', lambda explicit: book_root)

    def _fake_run_script(name, argv):
        called['name'] = name
        called['argv'] = list(argv)
        return 0

    monkeypatch.setattr(module, '_run_script', _fake_run_script)
    monkeypatch.setattr(sys, 'argv', ['webnovel', '--project-root', str(tmp_path), 'query', '--', '--focus', 'urgency'])

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert int(exc.value.code or 0) == 0
    assert called['name'] == 'status_reporter.py'
    assert called['argv'] == ['--project-root', str(book_root), '--focus', 'urgency']


