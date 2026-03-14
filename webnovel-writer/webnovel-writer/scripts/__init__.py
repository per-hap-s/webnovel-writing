"""
webnovel-writer scripts package

This package contains all Python scripts for the webnovel-writer plugin.
"""

from __future__ import annotations

from importlib import import_module

__version__ = "5.4.0"
__author__ = "lcy"

__all__ = [
    "security_utils",
    "project_locator",
    "chapter_paths",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(name)
    module = import_module(f".{name}", __name__)
    globals()[name] = module
    return module
