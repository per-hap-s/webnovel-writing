#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
APP_ROOT = ROOT / 'webnovel-writer'
DOC_FILES = [ROOT / 'README.md']
DOC_ROOTS = [APP_ROOT / 'skills', APP_ROOT / 'agents', APP_ROOT / 'references', ROOT / 'docs']
SCRIPT_FILES = [
    APP_ROOT / 'scripts' / 'backup_manager.py',
    APP_ROOT / 'scripts' / 'init_project.py',
    APP_ROOT / 'scripts' / 'data_modules' / 'config.py',
]
FORBIDDEN_LITERALS = [
    'CLAUDE_PLUGIN_ROOT',
    'CLAUDE_PROJECT_DIR',
    'allowed-tools:',
    'AskUserQuestion',
    '~/.claude/webnovel-writer/.env',
]
LEGACY_SLASH_COMMAND = re.compile(r'(^|[\s`(])(/webnovel-[a-z-]+)', re.IGNORECASE)


def iter_docs():
    for path in DOC_FILES:
        if path.is_file():
            yield path
    for folder in DOC_ROOTS:
        for path in folder.rglob('*.md'):
            yield path


def iter_user_facing_files():
    yield from iter_docs()
    for path in SCRIPT_FILES:
        if path.is_file():
            yield path


def test_user_facing_files_do_not_reference_retired_claude_runtime_terms():
    violations = []
    for path in iter_user_facing_files():
        text = path.read_text(encoding='utf-8')
        for token in FORBIDDEN_LITERALS:
            if token in text:
                violations.append(f'{path.relative_to(ROOT)} -> {token}')
        match = LEGACY_SLASH_COMMAND.search(text)
        if match:
            violations.append(f'{path.relative_to(ROOT)} -> {match.group(2)}')
    assert not violations, 'Found retired Claude runtime terms:\n' + '\n'.join(violations)


def test_user_facing_files_use_neutral_pointer_path_when_pointer_is_mentioned():
    violations = []
    for path in iter_user_facing_files():
        text = path.read_text(encoding='utf-8')
        if '.webnovel-current-project' in text:
            violations.append(str(path.relative_to(ROOT)))
    assert not violations, 'Legacy pointer path still present:\n' + '\n'.join(violations)
