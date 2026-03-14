from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = DASHBOARD_ROOT / "frontend" / "src" / "App.jsx"
APP_SECTIONS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "appSections.jsx"


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    (webnovel_dir / "state.json").write_text(json.dumps({"project_name": "Smoke Novel"}), encoding="utf-8")
    return project_root


def test_validation_error_envelope_matches_frontend_expectations(tmp_path: Path):
    project_root = make_project(tmp_path)
    app = create_app(project_root=project_root)

    with TestClient(app) as client:
        response = client.post("/api/review/approve", json={})

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["message"] == "Request validation failed"
    assert isinstance(payload.get("details", {}).get("errors"), list)
    assert any(error["field"] == "body.task_id" for error in payload["details"]["errors"])


def test_frontend_launcher_surfaces_api_errors():
    source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "setError(String(err.message || err))" in source
    assert '{error ? <div className="error-text">{error}</div> : null}' in source


def test_frontend_task_event_rendering_covers_review_gate_messages():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "fetchJSON(`/api/tasks/${selectedTask.id}/events`)" in section_source
    assert "translateEventMessage(event.message)" in section_source
    assert "translateEventLevel(event.level)" in section_source
    assert "translateStepName(event.step_name || 'task')" in section_source
    expected_review_gate = "\u5ba1\u67e5\u95f8\u95e8\u963b\u6b62\u7ee7\u7eed\u6267\u884c"
    assert f"'Review gate blocked execution': '{expected_review_gate}'" in app_source
