#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Create a repeatable supervisor smoke fixture project.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from runtime_compat import enable_windows_utf8_stdio

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = PACKAGE_ROOT.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from dashboard.orchestrator import OrchestrationService
from scripts.init_project import init_project


def _default_project_root() -> Path:
    stamp = datetime.now().strftime("%H%M%S")
    date_stamp = datetime.now().strftime("%Y%m%d")
    return PLUGIN_ROOT / f".tmp-playwright-{date_stamp}" / f"supervisor-smoke-{stamp}"


def _store_task(
    service: OrchestrationService,
    task_type: str,
    request: Dict[str, Any],
    *,
    status: str,
    updated_at: str,
    error: Dict[str, Any] | None = None,
    artifacts: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    task = service.store.create_task(task_type, request, {"name": task_type, "version": 1, "steps": []})
    updates: Dict[str, Any] = {"status": status, "updated_at": updated_at}
    if error is not None:
        updates["error"] = error
    if artifacts is not None:
        updates["artifacts"] = artifacts
    return service.store.update_task(task["id"], **updates)


def _append_raw_audit_event(project_root: Path, event: Dict[str, Any]) -> None:
    audit_path = project_root / ".webnovel" / "supervisor" / "audit-log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _seed_project(project_root: Path) -> OrchestrationService:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        init_project(str(project_root), "Supervisor Smoke Fixture", "Urban Fantasy", target_chapters=12, target_words=120000)
    service = OrchestrationService(project_root)

    def _mutate_state(payload: Dict[str, Any]) -> Dict[str, Any]:
        progress = payload.setdefault("progress", {})
        progress["current_chapter"] = 4
        progress["total_words"] = 24000
        return payload

    service._update_state_data(_mutate_state)
    return service


def create_supervisor_smoke_fixture(*, project_root: str | Path | None = None) -> Dict[str, Any]:
    target_root = Path(project_root).expanduser().resolve() if project_root else _default_project_root().resolve()
    target_root.mkdir(parents=True, exist_ok=True)

    service = _seed_project(target_root)

    approval_task = _store_task(
        service,
        "write",
        {"chapter": 3, "mode": "standard", "require_manual_approval": True},
        status="awaiting_writeback_approval",
        updated_at="2026-03-23T09:00:00+00:00",
    )
    review_task = _store_task(
        service,
        "write",
        {"chapter": 4, "mode": "standard", "require_manual_approval": False},
        status="failed",
        updated_at="2026-03-23T08:30:00+00:00",
        error={"code": "REVIEW_GATE_BLOCKED", "message": "fixture blocked by review gate"},
    )

    recommendations = service.list_supervisor_recommendations(limit=10, include_dismissed=True)
    approval_item = next(item for item in recommendations if item.get("sourceTaskId") == approval_task["id"])
    review_item = next(item for item in recommendations if item.get("sourceTaskId") == review_task["id"])

    checklist = service.save_supervisor_checklist(
        "\n".join(
            [
                "# 督办 Smoke 清单",
                "",
                "- [ ] 处理待审批回写任务",
                "- [ ] 处理审查阻断任务",
                "- [ ] 复核审计体检与修复预演",
            ]
        ),
        chapter=3,
        selected_keys=[approval_item["stableKey"], review_item["stableKey"]],
        category_filter="all",
        sort_mode="priority",
        title="督办 Smoke 清单",
        note="由 supervisor smoke fixture 自动生成。",
    )

    service.dismiss_supervisor_recommendation(
        approval_item["stableKey"],
        approval_item["fingerprint"],
        reason="fixture_dismiss",
        note="督办 smoke fixture 生成忽略事件。",
    )
    service.undismiss_supervisor_recommendation(approval_item["stableKey"])

    refreshed_approval = next(
        item
        for item in service.list_supervisor_recommendations(limit=10, include_dismissed=True)
        if item.get("sourceTaskId") == approval_task["id"]
    )
    service.set_supervisor_recommendation_tracking(
        refreshed_approval["stableKey"],
        refreshed_approval["fingerprint"],
        status="in_progress",
        note="督办 smoke fixture 已写入跟进状态。",
        linked_task_id=approval_task["id"],
        linked_checklist_path=checklist["relativePath"],
    )

    _append_raw_audit_event(
        target_root,
        {
            "timestamp": "2026-03-23T09:15:00+00:00",
            "action": "tracking_updated",
            "stable_key": refreshed_approval["stableKey"],
            "source_task_id": approval_task["id"],
            "linked_checklist_path": checklist["relativePath"],
            "category_label": "审批",
            "status_snapshot": "open",
        },
    )
    _append_raw_audit_event(
        target_root,
        {
            "schemaVersion": 3,
            "timestamp": "2026-03-23T09:20:00+00:00",
            "action": "tracking_updated",
            "stableKey": "future:supervisor-smoke",
            "sourceTaskId": review_task["id"],
            "linkedChecklistPath": checklist["relativePath"],
            "categoryLabel": "审查阻断",
            "status_snapshot": "open",
        },
    )

    service.apply_supervisor_audit_repair()

    recommendations_payload = service.list_supervisor_recommendations(limit=10, include_dismissed=True)
    checklists_payload = service.list_supervisor_checklists(limit=10)
    audit_log_payload = service.list_supervisor_audit_log(limit=200)
    audit_health_payload = service.get_supervisor_audit_health(issue_limit=20)
    repair_preview_payload = service.get_supervisor_audit_repair_preview(proposal_limit=20)
    repair_reports_payload = service.list_supervisor_audit_repair_reports(limit=10)

    result = {
        "project_root": str(target_root),
        "recommendation_count": len(recommendations_payload),
        "checklist_count": len(checklists_payload),
        "audit_log_count": len(audit_log_payload),
        "audit_health": {
            "exists": bool(audit_health_payload.get("exists")),
            "issue_count": int(audit_health_payload.get("issue_count") or 0),
        },
        "repair_preview": {
            "manual_review_count": int(repair_preview_payload.get("manual_review_count") or 0),
        },
        "repair_report_count": len(repair_reports_payload),
    }

    result_path = target_root / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    enable_windows_utf8_stdio(skip_in_pytest=True)
    parser = argparse.ArgumentParser(description="Create a repeatable supervisor smoke fixture project")
    parser.add_argument("--project-root", help="Target project root for the fixture")
    args = parser.parse_args()

    payload = create_supervisor_smoke_fixture(project_root=args.project_root)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
