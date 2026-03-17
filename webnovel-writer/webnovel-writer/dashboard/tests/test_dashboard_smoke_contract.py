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
    assert payload["message"] == "请求参数校验失败。"
    assert isinstance(payload.get("details", {}).get("errors"), list)
    assert any(error["field"] == "body.task_id" for error in payload["details"]["errors"])


def test_frontend_launcher_surfaces_api_errors():
    source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "setError(normalizeError(err))" in source
    assert "<ErrorNotice error={error} />" in source
    assert "ProjectBootstrapSection" in source or "ProjectBootstrapSection" in APP_PATH.read_text(encoding="utf-8-sig")


def test_frontend_task_event_rendering_covers_review_gate_messages_and_runtime_status():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "fetchJSON(`/api/tasks/${selectedTask.id}/events`)" in section_source
    assert "translateEventMessage(event.message)" in section_source
    assert "translateEventLevel(event.level)" in section_source
    assert "translateStepName(event.step_name || 'task')" in section_source
    assert "实时运行状态" in section_source
    assert "runtime_status?.phase_label" in section_source
    assert "runtime_status?.phase_detail" in section_source
    assert "runtime_status?.waiting_seconds" in section_source
    assert "formatTimestampShort(event.timestamp)" in section_source
    assert "buildRuntimeSummary(task)" in section_source
    assert "'Review gate blocked execution'" in app_source
    assert "'prompt_compiled'" in app_source
    assert "'awaiting_model_response'" in app_source
    assert "'step_heartbeat'" in app_source
    assert "'step_retry_started'" in app_source
    assert "'step_waiting_approval'" in app_source


def test_task_list_endpoint_returns_runtime_status(tmp_path: Path):
    project_root = make_project(tmp_path)
    app = create_app(project_root=project_root)
    task_file = project_root / ".webnovel" / "observability" / "task-runs" / "task-1.json"
    with TestClient(app) as client:
        task_file.parent.mkdir(parents=True, exist_ok=True)
        task_file.write_text(
            json.dumps(
                {
                    "id": "task-1",
                    "task_type": "plan",
                    "workflow_name": "plan",
                    "workflow_version": 1,
                    "status": "running",
                    "approval_status": "not_required",
                    "current_step": "plan",
                    "request": {"volume": "1"},
                    "project_root": str(project_root),
                    "created_at": "2026-03-16T10:00:00",
                    "updated_at": "2026-03-16T10:00:05",
                    "started_at": "2026-03-16T10:00:00",
                    "finished_at": None,
                    "interrupted_at": None,
                    "recovered_at": None,
                    "resume_target_task_id": None,
                    "resume_from_step": None,
                    "resume_reason": None,
                    "error": None,
                    "step_order": ["plan"],
                    "workflow_spec": {"steps": [{"name": "plan", "type": "llm"}]},
                    "artifacts": {"step_results": {}, "review_summary": None, "approval": {}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (task_file.parent / "task-1.events.jsonl").write_text(
            json.dumps(
                {
                    "id": "evt-1",
                    "task_id": "task-1",
                    "level": "info",
                    "message": "awaiting_model_response",
                    "step_name": "plan",
                    "payload": {"attempt": 1, "retry_count": 0, "timeout_seconds": 300, "retryable": True},
                    "timestamp": "2026-03-16T10:00:01",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        response = client.get("/api/tasks")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["runtime_status"]["phase_label"]
    assert payload[0]["runtime_status"]["step_state"] == "running"
    assert payload[0]["runtime_status"]["attempt"] == 1
    assert "phase_detail" in payload[0]["runtime_status"]
    assert "waiting_seconds" in payload[0]["runtime_status"]


def test_project_info_includes_dashboard_context(tmp_path: Path):
    project_root = make_project(tmp_path)
    app = create_app(project_root=project_root)

    with TestClient(app) as client:
        response = client.get("/api/project/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dashboard_context"]["project_root"] == str(project_root)
    assert payload["dashboard_context"]["project_initialized"] is True
