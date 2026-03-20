#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified CLI for Webnovel Writer.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from runtime_compat import enable_windows_utf8_stdio, normalize_windows_path
from project_locator import resolve_project_root, write_current_project_pointer, update_global_registry_current_project


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _resolve_root(explicit_project_root: Optional[str]) -> Path:
    if explicit_project_root:
        return resolve_project_root(explicit_project_root)
    return resolve_project_root()


def _strip_project_root_args(argv: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--project-root":
            i += 2
            continue
        if tok.startswith("--project-root="):
            i += 1
            continue
        out.append(tok)
        i += 1
    return out


def _run_module_entry(module_name: str, argv: list[str]) -> int:
    mod = importlib.import_module(module_name)
    main = getattr(mod, "main", None)
    if not callable(main):
        raise RuntimeError(f"{module_name} 缺少可调用的 main()")

    old_argv = sys.argv
    try:
        sys.argv = [module_name] + argv
        try:
            return int(main() or 0)
        except SystemExit as exc:
            return int(exc.code or 0)
    finally:
        sys.argv = old_argv


def _run_data_module(module: str, argv: list[str]) -> int:
    return _run_module_entry(f"data_modules.{module}", argv)


def _run_script(script_name: str, argv: list[str]) -> int:
    script_path = _scripts_dir() / script_name
    if not script_path.is_file():
        raise FileNotFoundError(f"未找到脚本: {script_path}")
    proc = subprocess.run([sys.executable, str(script_path), *argv])
    return int(proc.returncode or 0)


def _run_dashboard(argv: list[str]) -> int:
    return _run_module_entry("dashboard.server", argv)


def _run_task_sync(task_type: str, project_root: Path, request: dict) -> int:
    from dashboard.orchestrator import OrchestrationService

    service = OrchestrationService(project_root)
    result = service.run_task_sync(task_type, request)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"completed", "awaiting_writeback_approval"} else 1


def cmd_where(args: argparse.Namespace) -> int:
    root = _resolve_root(args.project_root)
    print(str(root))
    return 0


def cmd_use(args: argparse.Namespace) -> int:
    project_root = normalize_windows_path(args.project_root).expanduser()
    try:
        project_root = project_root.resolve()
    except Exception:
        project_root = project_root

    workspace_root: Optional[Path] = None
    if args.workspace_root:
        workspace_root = normalize_windows_path(args.workspace_root).expanduser()
        try:
            workspace_root = workspace_root.resolve()
        except Exception:
            workspace_root = workspace_root

    pointer_file = write_current_project_pointer(project_root, workspace_root=workspace_root)
    if pointer_file is not None:
        print(f"workspace pointer: {pointer_file}")
    else:
        print("workspace pointer: (skipped)")

    reg_path = update_global_registry_current_project(workspace_root=workspace_root, project_root=project_root)
    if reg_path is not None:
        print(f"global registry: {reg_path}")
    else:
        print("global registry: (skipped)")

    return 0


def main() -> None:
    enable_windows_utf8_stdio()
    parser = argparse.ArgumentParser(description="webnovel unified CLI")
    parser.add_argument("--project-root", help="书项目根目录或工作区根目录（可选，默认自动检测）")

    sub = parser.add_subparsers(dest="tool", required=True)

    p_where = sub.add_parser("where", help="打印解析出的 project_root")
    p_where.set_defaults(func=cmd_where)

    p_use = sub.add_parser("use", help="绑定当前工作区使用的书项目（写入指针/registry）")
    p_use.add_argument("project_root", help="书项目根目录（必须包含 .webnovel/state.json）")
    p_use.add_argument("--workspace-root", help="工作区根目录（可选；默认由运行环境推断）")
    p_use.set_defaults(func=cmd_use)

    p_dashboard = sub.add_parser("dashboard", help="启动 Dashboard")
    p_dashboard.add_argument("--host", default="127.0.0.1")
    p_dashboard.add_argument("--port", type=int, default=8765)
    p_dashboard.add_argument("--no-browser", action="store_true")

    p_plan = sub.add_parser("plan", help="执行规划工作流")
    p_plan.add_argument("volume", nargs="?", default=None)
    p_plan.add_argument("--mode", default="standard", choices=["standard", "fast", "minimal"])

    p_write = sub.add_parser("write", help="执行写作工作流")
    p_write.add_argument("chapter", type=int)
    p_write.add_argument("--mode", default="standard", choices=["standard", "fast", "minimal"])
    p_write.add_argument("--require-manual-approval", action="store_true")

    p_guarded_batch = sub.add_parser("guarded-batch", help="执行有上限的护栏批量推进")
    p_guarded_batch.add_argument("start_chapter", type=int)
    p_guarded_batch.add_argument("--max-chapters", type=int, default=2)
    p_guarded_batch.add_argument("--mode", default="standard", choices=["standard", "fast", "minimal"])
    p_guarded_batch.add_argument("--require-manual-approval", action="store_true")

    p_review = sub.add_parser("review", help="执行审查工作流")
    p_review.add_argument("chapter_range")
    p_review.add_argument("--mode", default="standard", choices=["standard", "fast", "minimal"])

    p_resume = sub.add_parser("resume", help="执行恢复工作流")
    p_resume.add_argument("--mode", default="standard", choices=["standard", "fast", "minimal"])

    p_query = sub.add_parser("query", help="转发到状态查询")
    p_query.add_argument("args", nargs=argparse.REMAINDER)

    p_index = sub.add_parser("index", help="转发到 index_manager")
    p_index.add_argument("args", nargs=argparse.REMAINDER)

    p_state = sub.add_parser("state", help="转发到 state_manager")
    p_state.add_argument("args", nargs=argparse.REMAINDER)

    p_rag = sub.add_parser("rag", help="转发到 rag_adapter")
    p_rag.add_argument("args", nargs=argparse.REMAINDER)

    p_style = sub.add_parser("style", help="转发到 style_sampler")
    p_style.add_argument("args", nargs=argparse.REMAINDER)

    p_entity = sub.add_parser("entity", help="转发到 entity_linker")
    p_entity.add_argument("args", nargs=argparse.REMAINDER)

    p_context = sub.add_parser("context", help="转发到 context_manager")
    p_context.add_argument("args", nargs=argparse.REMAINDER)

    p_migrate = sub.add_parser("migrate", help="转发到 migrate_state_to_sqlite")
    p_migrate.add_argument("args", nargs=argparse.REMAINDER)

    p_workflow = sub.add_parser("workflow", help="转发到 workflow_manager.py")
    p_workflow.add_argument("args", nargs=argparse.REMAINDER)

    p_status = sub.add_parser("status", help="转发到 status_reporter.py")
    p_status.add_argument("args", nargs=argparse.REMAINDER)

    p_audit = sub.add_parser("audit", help="转发到 supervisor_audit.py")
    p_audit.add_argument("args", nargs=argparse.REMAINDER)

    p_update_state = sub.add_parser("update-state", help="转发到 update_state.py")
    p_update_state.add_argument("args", nargs=argparse.REMAINDER)

    p_backup = sub.add_parser("backup", help="转发到 backup_manager.py")
    p_backup.add_argument("args", nargs=argparse.REMAINDER)

    p_archive = sub.add_parser("archive", help="转发到 archive_manager.py")
    p_archive.add_argument("args", nargs=argparse.REMAINDER)

    p_init = sub.add_parser("init", help="转发到 init_project.py（初始化项目）")
    p_init.add_argument("args", nargs=argparse.REMAINDER)

    p_extract_context = sub.add_parser("extract-context", help="转发到 extract_chapter_context.py")
    p_extract_context.add_argument("--chapter", type=int, required=True, help="目标章节号")
    p_extract_context.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")

    from .cli_args import normalize_global_project_root

    argv = normalize_global_project_root(sys.argv[1:])
    args = parser.parse_args(argv)

    if hasattr(args, "func"):
        raise SystemExit(int(args.func(args) or 0))

    tool = args.tool
    rest = list(getattr(args, "args", []) or [])
    if rest[:1] == ["--"]:
        rest = rest[1:]
    rest = _strip_project_root_args(rest)

    if tool == "init":
        raise SystemExit(_run_script("init_project.py", rest))

    project_root = _resolve_root(args.project_root)
    forward_args = ["--project-root", str(project_root)]

    if tool == "dashboard":
        dashboard_args = ["--project-root", str(project_root), "--host", args.host, "--port", str(args.port)]
        if args.no_browser:
            dashboard_args.append("--no-browser")
        raise SystemExit(_run_dashboard(dashboard_args))

    if tool == "plan":
        raise SystemExit(
            _run_task_sync(
                "plan",
                project_root,
                {"project_root": str(project_root), "volume": args.volume, "mode": args.mode},
            )
        )

    if tool == "write":
        raise SystemExit(
            _run_task_sync(
                "write",
                project_root,
                {
                    "project_root": str(project_root),
                    "chapter": args.chapter,
                    "mode": args.mode,
                    "require_manual_approval": bool(args.require_manual_approval),
                },
            )
        )

    if tool == "guarded-batch":
        raise SystemExit(
            _run_task_sync(
                "guarded-batch-write",
                project_root,
                {
                    "project_root": str(project_root),
                    "start_chapter": args.start_chapter,
                    "max_chapters": args.max_chapters,
                    "mode": args.mode,
                    "require_manual_approval": bool(args.require_manual_approval),
                },
            )
        )

    if tool == "review":
        raise SystemExit(
            _run_task_sync(
                "review",
                project_root,
                {"project_root": str(project_root), "chapter_range": args.chapter_range, "mode": args.mode},
            )
        )

    if tool == "resume":
        raise SystemExit(
            _run_task_sync(
                "resume",
                project_root,
                {"project_root": str(project_root), "mode": args.mode},
            )
        )

    if tool == "query":
        raise SystemExit(_run_script("status_reporter.py", [*forward_args, *rest]))

    if tool == "index":
        raise SystemExit(_run_data_module("index_manager", [*forward_args, *rest]))
    if tool == "state":
        raise SystemExit(_run_data_module("state_manager", [*forward_args, *rest]))
    if tool == "rag":
        raise SystemExit(_run_data_module("rag_adapter", [*forward_args, *rest]))
    if tool == "style":
        raise SystemExit(_run_data_module("style_sampler", [*forward_args, *rest]))
    if tool == "entity":
        raise SystemExit(_run_data_module("entity_linker", [*forward_args, *rest]))
    if tool == "context":
        raise SystemExit(_run_data_module("context_manager", [*forward_args, *rest]))
    if tool == "migrate":
        raise SystemExit(_run_data_module("migrate_state_to_sqlite", [*forward_args, *rest]))

    if tool == "workflow":
        raise SystemExit(_run_script("workflow_manager.py", [*forward_args, *rest]))
    if tool == "status":
        raise SystemExit(_run_script("status_reporter.py", [*forward_args, *rest]))
    if tool == "audit":
        raise SystemExit(_run_script("supervisor_audit.py", [*forward_args, *rest]))
    if tool == "update-state":
        raise SystemExit(_run_script("update_state.py", [*forward_args, *rest]))
    if tool == "backup":
        raise SystemExit(_run_script("backup_manager.py", [*forward_args, *rest]))
    if tool == "archive":
        raise SystemExit(_run_script("archive_manager.py", [*forward_args, *rest]))
    if tool == "extract-context":
        raise SystemExit(
            _run_script(
                "extract_chapter_context.py",
                [*forward_args, "--chapter", str(args.chapter), "--format", str(args.format)],
            )
        )

    raise SystemExit(2)


if __name__ == "__main__":
    main()

