from __future__ import annotations

import json
from pathlib import Path

from dashboard.orchestrator import OrchestrationService
from dashboard.tests.test_supervisor_recommendations import _write_raw_audit_events, make_project


def test_supervisor_audit_log_future_schema_marks_compatibility_warning(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    _write_raw_audit_events(
        project_root,
        [
            {
                "schemaVersion": 3,
                "timestamp": "2026-03-19T10:20:00+00:00",
                "action": "tracking_updated",
                "stableKey": "approval:task-v3",
                "sourceTaskId": "task-v3",
                "linkedChecklistPath": ".webnovel/supervisor/checklists/checklist-v3.md",
                "status_snapshot": "open",
                "categoryLabel": "审批",
            }
        ],
    )

    entries = service.list_supervisor_audit_log(limit=10)

    assert len(entries) == 1
    assert entries[0]["schema_version"] == 3
    assert entries[0]["schemaVersion"] == 3
    assert entries[0]["schema_state"] == "future"
    assert entries[0]["schemaState"] == "future"
    assert entries[0]["schema_supported"] is False
    assert entries[0]["schemaSupported"] is False
    assert "v3" in entries[0]["schema_warning"]
    assert "v2" in entries[0]["schema_warning"]
    assert "Detected audit schema" not in entries[0]["schema_warning"]
    assert "through v2" not in entries[0]["schema_warning"]
    assert "当前仅确认兼容到" in entries[0]["schema_warning"]
    assert entries[0]["schemaWarning"] == entries[0]["schema_warning"]


def test_supervisor_audit_health_reports_invalid_lines_and_missing_fields(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)
    audit_path = project_root / ".webnovel" / "supervisor" / "audit-log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        "\n".join(
            [
                "not-json",
                json.dumps({"timestamp": "bad-time", "action": "", "stableKey": "", "schemaVersion": 1}, ensure_ascii=False),
                json.dumps({"timestamp": "2026-03-19T10:20:00+00:00", "action": "tracking_updated", "stableKey": "approval:task-2", "schemaVersion": 3}, ensure_ascii=False),
            ]
        ),
        encoding="utf-8",
    )

    health = service.get_supervisor_audit_health(issue_limit=10)

    assert health["healthy"] is False
    assert health["exists"] is True
    assert health["total_lines"] == 3
    assert health["nonempty_lines"] == 3
    assert health["valid_entries"] == 2
    assert health["issue_count"] == 5
    assert health["issueCounts"]["invalid_json"] == 1
    assert health["issueCounts"]["invalid_timestamp"] == 1
    assert health["issueCounts"]["missing_action"] == 1
    assert health["issueCounts"]["missing_stable_key"] == 1
    assert health["issueCounts"]["future_schema"] == 1
    assert health["schemaStateCounts"]["supported"] == 1
    assert health["schemaStateCounts"]["future"] == 1
    assert health["schemaVersionCounts"]["1"] == 1
    assert health["schemaVersionCounts"]["3"] == 1
    assert health["latestTimestamp"] == "2026-03-19T10:20:00+00:00"
    assert any(item["code"] == "invalid_json" for item in health["issues"])
    assert any(item["code"] == "future_schema" for item in health["issues"])


def test_supervisor_audit_health_without_log_is_healthy(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    health = service.get_supervisor_audit_health()

    assert health["healthy"] is True
    assert health["exists"] is False
    assert health["issue_count"] == 0
    assert health["issues"] == []


def test_supervisor_audit_repair_preview_classifies_repairable_and_manual_review(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)
    audit_path = project_root / ".webnovel" / "supervisor" / "audit-log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        "\n".join(
            [
                "not-json",
                json.dumps(
                    {
                        "timestamp": "2026-03-19T10:15:00+00:00",
                        "action": "tracking_updated",
                        "stable_key": "approval:task-v1",
                        "source_task_id": "task-v1",
                        "category_label": "审批",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "schemaVersion": 3,
                        "timestamp": "2026-03-19T10:20:00+00:00",
                        "action": "tracking_updated",
                        "stableKey": "approval:task-v3",
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    preview = service.get_supervisor_audit_repair_preview(proposal_limit=10)

    assert preview["exists"] is True
    assert preview["total_lines"] == 3
    assert preview["nonempty_lines"] == 3
    assert preview["repairable_count"] == 2
    assert preview["manual_review_count"] == 1
    assert preview["actionCounts"]["drop_line"] == 1
    assert preview["actionCounts"]["rewrite_normalized_event"] == 1
    assert preview["actionCounts"]["manual_review"] == 1
    assert preview["proposals"][0]["action"] == "drop_line"
    assert preview["proposals"][1]["action"] == "rewrite_normalized_event"
    assert preview["proposals"][1]["proposedEvent"]["stableKey"] == "approval:task-v1"
    assert preview["proposals"][2]["action"] == "manual_review"
    assert "future_schema" in preview["proposals"][2]["issueCodes"]


def test_supervisor_audit_repair_applies_only_safe_changes_and_creates_backup(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)
    audit_path = project_root / ".webnovel" / "supervisor" / "audit-log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        "\n".join(
            [
                "not-json",
                json.dumps(
                    {
                        "timestamp": "2026-03-19T10:15:00+00:00",
                        "action": "tracking_updated",
                        "stable_key": "approval:task-v1",
                        "source_task_id": "task-v1",
                        "category_label": "审批",
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "schemaVersion": 3,
                        "timestamp": "2026-03-19T10:20:00+00:00",
                        "action": "tracking_updated",
                        "stableKey": "approval:task-v3",
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = service.apply_supervisor_audit_repair()

    assert result["exists"] is True
    assert result["changed"] is True
    assert result["backupCreated"] is True
    assert result["reportCreated"] is True
    assert result["dropped_count"] == 1
    assert result["rewritten_count"] == 1
    assert result["manual_review_count"] == 1
    assert Path(result["backupPath"]).is_file()
    assert Path(result["reportPath"]).is_file()

    repaired_lines = audit_path.read_text(encoding="utf-8").splitlines()
    assert len(repaired_lines) == 2
    rewritten = json.loads(repaired_lines[0])
    assert rewritten["schema_version"] == 1
    assert rewritten["stableKey"] == "approval:task-v1"
    assert "stable_key" not in rewritten
    manual_review_line = json.loads(repaired_lines[1])
    assert manual_review_line["schemaVersion"] == 3
    assert manual_review_line["stableKey"] == "approval:task-v3"
    report = json.loads(Path(result["reportPath"]).read_text(encoding="utf-8"))
    assert report["summary"]["dropped_count"] == 1
    assert report["summary"]["rewritten_count"] == 1
    assert report["summary"]["manual_review_count"] == 1
    assert len(report["appliedProposals"]) == 2
    assert len(report["skippedManualReview"]) == 1


def test_supervisor_audit_repair_skips_write_when_only_manual_review_items_exist(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)
    audit_path = project_root / ".webnovel" / "supervisor" / "audit-log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    original_content = json.dumps(
        {
            "schemaVersion": 3,
            "timestamp": "2026-03-19T10:20:00+00:00",
            "action": "tracking_updated",
            "stableKey": "approval:task-v3",
        },
        ensure_ascii=False,
    )
    audit_path.write_text(original_content, encoding="utf-8")

    result = service.apply_supervisor_audit_repair()

    assert result["changed"] is False
    assert result["backupCreated"] is False
    assert result["reportCreated"] is True
    assert result["manual_review_count"] == 1
    assert audit_path.read_text(encoding="utf-8") == original_content
    assert Path(result["reportPath"]).is_file()


def test_supervisor_audit_repair_reports_list_returns_latest_first(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)
    audit_path = project_root / ".webnovel" / "supervisor" / "audit-log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "timestamp": "2026-03-19T10:15:00+00:00",
                "action": "tracking_updated",
                "stable_key": "approval:task-v1",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    first = service.apply_supervisor_audit_repair()
    second = service.apply_supervisor_audit_repair()

    items = service.list_supervisor_audit_repair_reports(limit=5)

    assert len(items) == 2
    assert items[0]["relativePath"] == second["reportRelativePath"]
    assert items[1]["relativePath"] == first["reportRelativePath"]
    assert items[0]["changed"] is False
    assert items[1]["changed"] is True
    assert items[1]["rewrittenCount"] == 1
    assert items[0]["content"]["summary"]["manual_review_count"] == 0
