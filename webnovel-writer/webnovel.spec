# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

root = Path.cwd()
app_root = root / 'webnovel-writer'


a = Analysis(
    ['webnovel.py'],
    pathex=[str(root), str(app_root), str(app_root / 'scripts')],
    binaries=[],
    datas=[
        (str(app_root), 'webnovel-writer'),
    ],
    hiddenimports=[
        'dashboard.server',
        'dashboard.app',
        'dashboard.orchestrator',
        'dashboard.task_store',
        'dashboard.task_models',
        'dashboard.llm_runner',
        'data_modules.webnovel',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='webnovel',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='webnovel',
)
