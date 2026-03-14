#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", None)
        if base:
            return Path(base)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> None:
    root = _bundle_root()
    app_root = root / "webnovel-writer"
    scripts_root = app_root / "scripts"

    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))

    os.environ.setdefault("WEBNOVEL_APP_ROOT", str(app_root))

    if len(sys.argv) == 1:
        sys.argv.append("dashboard")

    from runtime_compat import enable_windows_utf8_stdio
    from data_modules.webnovel import main as cli_main

    enable_windows_utf8_stdio()
    cli_main()


if __name__ == "__main__":
    main()

