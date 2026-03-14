from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_packaged_imports_work_from_package_root():
    package_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(package_root))
    try:
        for name in [
            "scripts",
            "scripts.data_modules.webnovel",
            "runtime_compat",
            "project_locator",
            "security_utils",
            "chapter_paths",
        ]:
            sys.modules.pop(name, None)

        scripts_pkg = importlib.import_module("scripts")
        cli_module = importlib.import_module("scripts.data_modules.webnovel")

        assert scripts_pkg is not None
        assert callable(cli_module.main)
    finally:
        try:
            sys.path.remove(str(package_root))
        except ValueError:
            pass
