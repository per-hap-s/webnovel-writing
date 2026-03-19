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
    assert payload["message"]
    assert isinstance(payload.get("details", {}).get("errors"), list)
    assert any(error["field"] == "body.task_id" for error in payload["details"]["errors"])


def test_frontend_launcher_surfaces_api_errors():
    source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")
    app_source = APP_PATH.read_text(encoding="utf-8-sig")

    assert "setError(normalizeError(err))" in source
    assert "<ErrorNotice error={error} />" in source
    assert "ProjectBootstrapSection" in source or "ProjectBootstrapSection" in app_source
    assert "key: 'guarded-write'" in app_source
    assert "'guarded-write':" in app_source
    assert "ErrorNotice" in app_source


def test_frontend_task_event_rendering_covers_runtime_contract():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "fetchJSON(`/api/tasks/${selectedTask.id}/events`)" in section_source
    assert "translateEventMessage(event.message)" in section_source
    assert "translateEventLevel(event.level)" in section_source
    assert "translateStepName(event.step_name || 'task')" in section_source
    assert "runtime_status?.phase_label" in section_source
    assert "runtime_status?.target_label" in section_source
    assert "runtime_status?.phase_detail" in section_source
    assert "runtime_status?.waiting_seconds" in section_source
    assert "runtime_status?.step_started_at" in section_source
    assert "runtime_status?.waiting_since" in section_source
    assert "runtime_status?.last_non_heartbeat_activity_at" in section_source
    assert "buildRuntimeSummary(task)" in section_source
    assert "buildEventPayloadTags" in section_source
    assert "tree-folder-toggle" in section_source
    assert "'Review gate blocked execution'" in app_source
    assert "'Write target normalized'" in app_source
    assert "writeback_rollback_started" in app_source
    assert "writeback_rollback_finished" in app_source
    assert "'prompt_compiled'" in app_source
    assert "'awaiting_model_response'" in app_source
    assert "'step_heartbeat'" in app_source
    assert "'step_retry_started'" in app_source
    assert "'step_waiting_approval'" in app_source
    assert "'Resume target scheduled'" in app_source
    assert "'Workflow config error'" in app_source
    assert "'Guarded runner blocked by story refresh'" in app_source
    assert "'Guarded runner completed one chapter'" in app_source


def test_frontend_task_detail_includes_guarded_runner_view():
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "resolveGuardedRunnerResult" in section_source
    assert "formatGuardedOutcome" in section_source
    assert "launchTask('guarded-write'" in section_source
    assert "launchTask('write'" in section_source


def test_frontend_control_page_includes_supervisor_panel():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")

    assert "{ id: 'supervisor'" in app_source
    assert "{ id: 'supervisor-audit'" in app_source
    assert "page === 'supervisor'" in app_source
    assert "page === 'supervisor-audit'" in app_source
    assert "<SupervisorPage" in app_source
    assert "<SupervisorAuditPage" in app_source
    assert "fetchJSON('/api/supervisor/recommendations?include_dismissed=true')" in app_source
    assert "postJSON('/api/supervisor/dismiss'" in app_source
    assert "postJSON('/api/supervisor/dismiss-batch'" in app_source
    assert "postJSON('/api/supervisor/undismiss'" in app_source
    assert "postJSON('/api/supervisor/undismiss-batch'" in app_source
    assert "postJSON('/api/supervisor/tracking'" in app_source
    assert "postJSON('/api/supervisor/tracking/clear'" in app_source
    assert "postJSON('/api/supervisor/checklists'" in app_source
    assert "fetchJSON('/api/supervisor/checklists'" in app_source
    assert "rawSupervisorItems" in app_source
    assert "setRawSupervisorItems" in app_source
    assert "selectedSupervisorKeys" in app_source
    assert "toggleSupervisorSelection" in app_source
    assert "setSelectionForItems" in app_source
    assert "handleBatchSupervisorDismiss" in app_source
    assert "handleBatchSupervisorUndismiss" in app_source
    assert "checklistMarkdown" in app_source
    assert "buildSupervisorChecklistMarkdown" in app_source
    assert "downloadTextFile" in app_source
    assert "handleCopyChecklist" in app_source
    assert "handleDownloadChecklist" in app_source
    assert "handleSaveChecklistToProject" in app_source
    assert "savedChecklistMeta" in app_source
    assert "checklistTitle" in app_source
    assert "checklistNote" in app_source
    assert "trackingDrafts" in app_source
    assert "resolveTrackingDraft" in app_source
    assert "updateTrackingDraft" in app_source
    assert "handleSupervisorTrackingSave" in app_source
    assert "handleSupervisorTrackingClear" in app_source
    assert "statusFilter" in app_source
    assert "setStatusFilter" in app_source
    assert "supervisorStatusSummary" in app_source
    assert "recentChecklists" in app_source
    assert "selectedChecklistPath" in app_source
    assert "reloadSupervisorChecklists" in app_source
    assert "handleDownloadSavedChecklist" in app_source
    assert "batchDismissReason" in app_source
    assert "batchDismissNote" in app_source
    assert "categoryFilter" in app_source
    assert "sortMode" in app_source
    assert "SUPERVISOR_SORT_OPTIONS" in app_source
    assert "SUPERVISOR_STATUS_FILTER_OPTIONS" in app_source
    assert "supervisorItems.map((item) => {" in app_source
    assert "dismissedSupervisorItems.map((item) => (" in app_source
    assert "sortSupervisorItems" in app_source
    assert "extractSupervisorChapter" in app_source
    assert "item.categoryLabel" in app_source
    assert "SUPERVISOR_DISMISS_REASON_OPTIONS" in app_source
    assert "formatSupervisorDismissReason" in app_source
    assert "formatSupervisorTrackingStatus" in app_source
    assert "dismissalReason" in app_source
    assert "dismissalNote" in app_source
    assert "trackingStatus" in app_source
    assert "trackingNote" in app_source
    assert "linkedTaskId" in app_source
    assert "linkedChecklistPath" in app_source
    assert "SUPERVISOR_TRACKING_STATUS_OPTIONS" in app_source
    assert "item.rationale" in app_source
    assert "item.actionLabel" in app_source
    assert "item.secondaryLabel" in app_source
    assert "handleSupervisorDismiss" in app_source
    assert "handleSupervisorUndismiss" in app_source
    assert "item.title ||" in app_source
    assert "item.note ?" in app_source
    assert "selectedChecklist?.content" in app_source
    assert "Supervisor Inbox" in app_source
    assert "dismissedAt" in app_source
    assert "handleSupervisorAction" in app_source


def test_frontend_includes_supervisor_audit_view():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")

    assert "function SupervisorAuditPage" in app_source
    assert "auditItems" in app_source
    assert "auditChecklists" in app_source
    assert "auditCategoryFilter" in app_source
    assert "auditStatusFilter" in app_source
    assert "auditChapterFilter" in app_source
    assert "linkedTask" in app_source
    assert "linkedChecklist" in app_source
    assert "Supervisor Audit" in app_source
    assert "清单归档" in app_source or "\\u6e05\\u5355\\u5f52\\u6863" in app_source


def test_frontend_data_page_includes_story_plan_view():
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "fetchJSON('/api/story-plans'" in section_source
    assert "Story Plans" in section_source
    assert "current_goal" in section_source
    assert "priority_threads" in section_source


def test_frontend_task_detail_includes_story_refresh_view():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "story_refresh" in section_source
    assert "normalizeStoryRefresh" in section_source
    assert "resume_from_step: 'story-director'" in section_source
    assert "'Story plan refresh suggested'" in app_source


def test_frontend_task_detail_includes_task_lineage_view():
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "parent_task_id" in section_source
    assert "root_task_id" in section_source
    assert "trigger_source" in section_source


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
    runtime = response.json()[0]["runtime_status"]
    assert runtime["phase_label"]
    assert runtime["target_label"] == "\u7b2c 1 \u5377"
    assert runtime["step_state"] == "running"
    assert runtime["attempt"] == 1
    assert "phase_detail" in runtime
    assert "waiting_seconds" in runtime
    assert "step_started_at" in runtime
    assert "waiting_since" in runtime
    assert "last_non_heartbeat_activity_at" in runtime


def test_project_info_includes_dashboard_context(tmp_path: Path):
    project_root = make_project(tmp_path)
    app = create_app(project_root=project_root)

    with TestClient(app) as client:
        response = client.get("/api/project/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dashboard_context"]["project_root"] == str(project_root)
    assert payload["dashboard_context"]["project_initialized"] is True
