"""
Dashboard launcher and portable project-root resolution.
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from project_locator import resolve_project_root


def _resolve_project_root(cli_root: str | None) -> Path:
    if cli_root:
        return resolve_project_root(cli_root)

    env_root = os.environ.get("WEBNOVEL_PROJECT_ROOT")
    if env_root:
        return resolve_project_root(env_root)

    return resolve_project_root(cwd=Path.cwd())


def _build_browser_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host == "0.0.0.0" else host
    return f"http://{browser_host}:{port}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Webnovel Dashboard Server")
    parser.add_argument("--project-root", type=str, default=None, help="小说项目根目录")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", type=int, default=8765, help="监听端口")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    project_root = _resolve_project_root(args.project_root)
    os.environ.setdefault("WEBNOVEL_PROJECT_ROOT", str(project_root))
    print(f"项目路径: {project_root}")

    import uvicorn
    from .app import create_app

    app = create_app(project_root)

    url = f"http://{args.host}:{args.port}"
    browser_url = _build_browser_url(args.host, args.port)
    print(f"Dashboard 启动: {url}")
    print(f"API 文档: {url}/docs")

    if not args.no_browser:
        webbrowser.open(browser_url)

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
