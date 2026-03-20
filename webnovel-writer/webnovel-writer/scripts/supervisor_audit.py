#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Supervisor audit maintenance CLI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

from runtime_compat import enable_windows_utf8_stdio

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from project_locator import resolve_project_root
except ImportError:  # pragma: no cover
    from scripts.project_locator import resolve_project_root

try:
    from dashboard.orchestrator import OrchestrationService
except ImportError:  # pragma: no cover
    raise


def _resolve_service(project_root_arg: str | None) -> OrchestrationService:
    project_root = resolve_project_root(project_root_arg) if project_root_arg else resolve_project_root()
    return OrchestrationService(Path(project_root))


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_health_text(payload: Dict[str, Any]) -> None:
    print(f"audit log: {payload.get('relativePath') or payload.get('path')}")
    print(f"healthy: {'yes' if payload.get('healthy') else 'no'}")
    print(f"issues: {payload.get('issue_count', 0)}")
    print(f"valid entries: {payload.get('valid_entries', 0)}")
    for issue in payload.get("issues") or []:
        line = issue.get("line")
        where = f"line {line}" if line else "global"
        print(f"- [{where}] {issue.get('code')}: {issue.get('message')}")


def _print_preview_text(payload: Dict[str, Any]) -> None:
    print(f"audit log: {payload.get('relativePath') or payload.get('path')}")
    print(f"repairable: {payload.get('repairable_count', 0)}")
    print(f"manual review: {payload.get('manual_review_count', 0)}")
    for item in payload.get("proposals") or []:
        line = item.get("line")
        where = f"line {line}" if line else "global"
        print(f"- [{where}] {item.get('action')}: {item.get('reason')}")


def _print_repair_text(payload: Dict[str, Any]) -> None:
    print(f"audit log: {payload.get('relativePath') or payload.get('path')}")
    print(f"changed: {'yes' if payload.get('changed') else 'no'}")
    print(f"dropped: {payload.get('dropped_count', 0)}")
    print(f"rewritten: {payload.get('rewritten_count', 0)}")
    print(f"manual review kept: {payload.get('manual_review_count', 0)}")
    if payload.get("backupCreated"):
        print(f"backup: {payload.get('backupPath')}")
    if payload.get("reportCreated"):
        print(f"report: {payload.get('reportPath')}")


def main() -> int:
    enable_windows_utf8_stdio(skip_in_pytest=True)
    parser = argparse.ArgumentParser(description="Supervisor audit maintenance CLI")
    parser.add_argument("--project-root", help="书项目根目录或工作区根目录（可选，默认自动检测）")
    parser.add_argument("--format", choices=["json", "text"], default="json", help="输出格式")
    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", help="输出 audit health")
    p_health.add_argument("--issue-limit", type=int, default=20)

    p_preview = sub.add_parser("repair-preview", help="输出 repair preview")
    p_preview.add_argument("--proposal-limit", type=int, default=20)

    p_repair = sub.add_parser("repair", help="执行安全离线 repair")
    p_repair.add_argument("--no-backup", action="store_true", help="不生成备份文件")

    args = parser.parse_args()
    service = _resolve_service(args.project_root)

    if args.command == "health":
        payload = service.get_supervisor_audit_health(issue_limit=int(args.issue_limit or 20))
        if args.format == "text":
            _print_health_text(payload)
        else:
            _print_json(payload)
        return 0 if payload.get("healthy", True) else 1

    if args.command == "repair-preview":
        payload = service.get_supervisor_audit_repair_preview(proposal_limit=int(args.proposal_limit or 20))
        if args.format == "text":
            _print_preview_text(payload)
        else:
            _print_json(payload)
        return 0

    payload = service.apply_supervisor_audit_repair(create_backup=not bool(args.no_backup))
    if args.format == "text":
        _print_repair_text(payload)
    else:
        _print_json(payload)
    return 0 if payload.get("exists", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
