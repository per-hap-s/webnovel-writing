#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
webnovel 统一入口脚本（无需先 `cd`）。

用法示例：
  python "<SCRIPTS_DIR>/webnovel.py" where
  python "<SCRIPTS_DIR>/webnovel.py" index stats

说明：
- 该脚本负责补齐 `scripts.*` 包导入所需的 package root（包根目录）。
- 之后再转发到 `scripts.data_modules.webnovel`。
"""

from __future__ import annotations

import sys
from pathlib import Path

from runtime_compat import enable_windows_utf8_stdio


def _ensure_package_root_on_path() -> None:
    package_root = Path(__file__).resolve().parent.parent
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))


_ensure_package_root_on_path()


def main() -> None:
    from scripts.data_modules.webnovel import main as _main

    _main()


if __name__ == "__main__":
    enable_windows_utf8_stdio(skip_in_pytest=True)
    main()
