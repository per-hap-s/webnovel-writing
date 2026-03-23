from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app
from scripts.supervisor_smoke_fixture import create_supervisor_smoke_fixture


def test_supervisor_smoke_fixture_populates_real_supervisor_apis(tmp_path: Path):
    project_root = tmp_path / "supervisor-smoke-project"

    fixture_result = create_supervisor_smoke_fixture(project_root=project_root)

    app = create_app(project_root=project_root)
    with TestClient(app) as client:
        recommendations = client.get(
            "/api/supervisor/recommendations",
            params={"include_dismissed": "true", "project_root": str(project_root)},
        )
        checklists = client.get(
            "/api/supervisor/checklists",
            params={"project_root": str(project_root)},
        )
        audit_log = client.get(
            "/api/supervisor/audit-log",
            params={"project_root": str(project_root)},
        )
        audit_health = client.get(
            "/api/supervisor/audit-health",
            params={"project_root": str(project_root)},
        )
        repair_preview = client.get(
            "/api/supervisor/audit-repair-preview",
            params={"project_root": str(project_root)},
        )
        repair_reports = client.get(
            "/api/supervisor/audit-repair-reports",
            params={"project_root": str(project_root)},
        )

    assert recommendations.status_code == 200
    assert len(recommendations.json()) >= 2

    assert checklists.status_code == 200
    assert len(checklists.json()) >= 1

    assert audit_log.status_code == 200
    assert audit_log.json()

    assert audit_health.status_code == 200
    health_payload = audit_health.json()
    assert health_payload["exists"] is True
    assert health_payload["issue_count"] >= 1

    assert repair_preview.status_code == 200
    preview_payload = repair_preview.json()
    assert preview_payload["exists"] is True
    assert preview_payload["manual_review_count"] >= 1

    assert repair_reports.status_code == 200
    assert len(repair_reports.json()) >= 1

    result_path = project_root / "result.json"
    assert result_path.is_file()
    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert persisted["project_root"] == str(project_root.resolve())
    assert persisted["recommendation_count"] >= 2
    assert persisted["checklist_count"] >= 1
    assert persisted["audit_log_count"] >= 1
    assert persisted["audit_health"]["exists"] is True
    assert persisted["audit_health"]["issue_count"] >= 1
    assert persisted["repair_preview"]["manual_review_count"] >= 1
    assert persisted["repair_report_count"] >= 1
    assert fixture_result == persisted
