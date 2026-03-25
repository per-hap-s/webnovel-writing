from __future__ import annotations

from pathlib import Path


SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
TESTS_ROOT = Path(__file__).resolve().parent


def _read_script(name: str) -> str:
    return (SCRIPTS_ROOT / name).read_text(encoding="utf-8-sig")


def test_runtime_entrypoints_use_canonical_scripts_imports():
    cases = {
        "webnovel.py": [
            "from scripts.data_modules.webnovel import main as _main",
        ],
        "update_state.py": [
            "from scripts.data_modules.state_validator import (",
        ],
        "quality_trend_report.py": [
            "from scripts.project_locator import resolve_project_root",
            "from scripts.data_modules.config import DataModulesConfig",
            "from scripts.data_modules.index_manager import IndexManager",
        ],
        "extract_chapter_context.py": [
            "from scripts.chapter_paths import find_chapter_file, volume_num_for_chapter",
            "from scripts.data_modules.config import DataModulesConfig",
            "from scripts.data_modules.context_manager import ContextManager",
            "from scripts.data_modules.rag_adapter import RAGAdapter",
        ],
    }

    for script_name, expected_imports in cases.items():
        source = _read_script(script_name)
        assert "from data_modules." not in source
        for expected in expected_imports:
            assert expected in source


def test_runtime_entrypoints_do_not_keep_try_fallback_import_shims():
    quality_source = _read_script("quality_trend_report.py")
    context_source = _read_script("extract_chapter_context.py")

    assert "except ImportError" not in quality_source
    assert "except ImportError" not in context_source


def test_data_module_tests_do_not_use_legacy_import_path():
    offenders: list[str] = []
    for path in sorted(TESTS_ROOT.glob("test_*.py")):
        if path.name == "test_import_path_contracts.py":
            continue
        source = path.read_text(encoding="utf-8-sig")
        if "from data_modules." in source or "import data_modules." in source:
            offenders.append(path.name)

    assert offenders == []
