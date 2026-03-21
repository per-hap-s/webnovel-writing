from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from dashboard.llm_runner import StepResult
from dashboard.orchestrator import OrchestrationService
from scripts.data_modules.state_file import ProjectStateCorruptedError


def step_result(step_name: str, *, success: bool = True, payload: dict | None = None, error: dict | None = None) -> StepResult:
    payload = payload if payload is not None else {"result": "ok"}
    return StepResult(
        step_name=step_name,
        success=success,
        return_code=0 if success else 1,
        timing_ms=100,
        stdout=json.dumps(payload, ensure_ascii=False) if payload is not None else "",
        stderr="",
        structured_output=payload,
        prompt_file="prompt.md",
        output_file="output.txt",
        error=error,
    )


class MappingRunner:
    def probe(self):
        return {
            "provider": "codex-cli",
            "mode": "cli",
            "installed": True,
            "configured": True,
            "connection_status": "connected",
        }

    def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
        return step_result(step_spec["name"])


class HangingRunner(MappingRunner):
    runs_dirname = "llm-runs"
    timeout_ms = 1000
    max_request_retries = 0
    retry_backoff_seconds = 0

    def _timeout_seconds_for_step(self, step_name):
        return 1

    def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
        time.sleep(0.2)
        return step_result(step_spec["name"])


class HeartbeatRunner(MappingRunner):
    runs_dirname = "llm-runs"
    timeout_ms = 1000
    max_request_retries = 0
    retry_backoff_seconds = 0

    def _timeout_seconds_for_step(self, step_name):
        return 1

    def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
        if progress_callback:
            progress_callback("request_dispatched", {"attempt": 1, "retry_count": 0})
            progress_callback("awaiting_model_response", {"attempt": 1, "retry_count": 0})
        time.sleep(0.05)
        if progress_callback:
            progress_callback("response_received", {"attempt": 1, "retry_count": 0})
            progress_callback("parsing_output", {"attempt": 1, "retry_count": 0})
        return step_result(step_spec["name"])


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    (project_root / ".webnovel").mkdir(parents=True)
    (project_root / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True)
    (outline_dir / "总纲.md").write_text("# outline\n", encoding="utf-8")
    return project_root


def test_read_state_data_raises_for_corrupted_json(tmp_path: Path):
    project_root = make_project(tmp_path)
    (project_root / ".webnovel" / "state.json").write_text("{broken json", encoding="utf-8")
    service = OrchestrationService(project_root, runner=MappingRunner())

    with pytest.raises(ProjectStateCorruptedError):
        service._read_state_data()


def test_apply_plan_writeback_preserves_unrelated_state_fields(tmp_path: Path):
    project_root = make_project(tmp_path)
    state_path = project_root / ".webnovel" / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "project_info": {"title": "Test Novel", "genre": "Urban Fantasy"},
                "progress": {"current_chapter": 7, "total_words": 3200},
                "chapter_meta": {"7": {"title": "Existing Chapter"}},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    service = OrchestrationService(project_root, runner=MappingRunner())
    async def _noop_sync(**kwargs):
        return None

    service._sync_core_setting_docs = _noop_sync
    task = service.store.create_task("plan", {"volume": 1}, {"name": "plan", "version": 1, "steps": []})

    asyncio.run(
        service._apply_plan_writeback(
            task["id"],
            task,
            {
                "chapters": [{"chapter": 1}, {"chapter": 12}],
                "summary": "Volume summary",
            },
        )
    )

    updated = json.loads(state_path.read_text(encoding="utf-8"))
    assert updated["chapter_meta"]["7"]["title"] == "Existing Chapter"
    assert updated["planning"]["volume_plans"]["1"]["chapter_count"] == 2


def test_plan_setting_doc_sync_runs_without_blocking_event_loop(tmp_path: Path):
    project_root = make_project(tmp_path)
    workflow = {
        "name": "plan",
        "version": 1,
        "steps": [{"name": "plan", "type": "llm", "instructions": "do", "output_schema": {}}],
    }
    llm_started = threading.Event()
    llm_release = threading.Event()

    class SlowSettingDocRunner(MappingRunner):
        mode = "api"
        provider = "openai-compatible"

        def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
            if step_spec["name"] == "plan":
                return step_result(
                    "plan",
                    payload={
                        "volume_plan": {"title": "Volume 1"},
                        "chapters": [{"chapter": 1, "title": "Start"}],
                    },
                )
            if step_spec["name"] == "setting-docs-sync":
                llm_started.set()
                assert llm_release.wait(timeout=1), "setting-docs-sync did not receive release signal"
                return step_result(
                    "setting-docs-sync",
                    payload={
                        "worldview": "# 世界观\n\n- 待补充\n",
                        "power_system": "# 力量体系\n\n- 待补充\n",
                        "protagonist": "# 主角卡\n\n- 待补充\n",
                        "golden_finger": "# 金手指设计\n\n- 待补充\n",
                    },
                )
            return super().run(step_spec, workspace, prompt_bundle, progress_callback)

    service = OrchestrationService(project_root, runner=SlowSettingDocRunner())
    task = service.store.create_task("plan", {"volume": 1}, workflow)
    service._run_plan_preflight = lambda *args, **kwargs: None

    async def _exercise() -> None:
        runner_task = asyncio.create_task(service._run_task(task["id"]))
        try:
            await asyncio.wait_for(asyncio.to_thread(llm_started.wait, 1), timeout=1)
            await asyncio.wait_for(asyncio.sleep(0.05), timeout=0.2)
        finally:
            llm_release.set()
        await asyncio.wait_for(runner_task, timeout=1)

    asyncio.run(_exercise())
    completed = service.get_task(task["id"])
    assert completed["status"] == "completed"


def test_probe_rag_returns_client_probe(tmp_path: Path):
    project_root = make_project(tmp_path)

    with patch("dashboard.orchestrator.get_client") as mock_get_client:
        mock_get_client.return_value.probe.return_value = {"provider": "siliconflow", "configured": True}
        service = OrchestrationService(project_root, runner=MappingRunner())
        result = service.probe_rag()

    assert result["provider"] == "siliconflow"
    mock_get_client.return_value.probe.assert_called_once()


def test_retry_keeps_failed_step_and_queues_again(tmp_path: Path):
    project_root = make_project(tmp_path)

    class FailingRunner(MappingRunner):
        def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
            return step_result(step_spec["name"], success=False, payload=None, error={"code": "STEP_FAILED", "message": "failed"})

    workflow = {"name": "write", "version": 1, "steps": [{"name": "context", "type": "llm"}, {"name": "draft", "type": "llm"}]}
    service = OrchestrationService(project_root, runner=FailingRunner())
    task = service.store.create_task("write", {"chapter": 1}, workflow)

    asyncio.run(service._run_task(task["id"]))
    failed_task = service.get_task(task["id"])
    assert failed_task["status"] == "failed"
    assert failed_task["current_step"] == "context"

    retried = service.retry_task(task["id"])
    assert retried["status"] == "retrying"


def test_retry_defaults_to_polish_or_data_sync(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    workflow = {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "context", "type": "llm"},
            {"name": "draft", "type": "llm"},
            {"name": "polish", "type": "llm"},
            {"name": "approval-gate", "type": "internal"},
            {"name": "data-sync", "type": "llm"},
        ],
    }
    polish_task = service.store.create_task("write", {"chapter": 1}, workflow)
    service.store.update_task(polish_task["id"], workflow_spec=workflow, status="failed", current_step="polish", error={"code": "LLM_TIMEOUT"})

    retried_polish = service.retry_task(polish_task["id"])
    polish_event = service.get_events(polish_task["id"])[-1]
    assert retried_polish["status"] == "retrying"
    assert polish_event["payload"]["resume_from_step"] == "polish"

    data_sync_task = service.store.create_task("write", {"chapter": 2}, workflow)
    service.store.update_task(
        data_sync_task["id"],
        workflow_spec=workflow,
        status="failed",
        current_step="data-sync",
        approval_status="approved",
        artifacts={"step_results": {"polish": {"success": True}}, "approval": {"status": "approved"}},
        error={"code": "LLM_HTTP_ERROR"},
    )

    retried_data_sync = service.retry_task(data_sync_task["id"])
    data_sync_event = service.get_events(data_sync_task["id"])[-1]
    refreshed = service.get_task(data_sync_task["id"])
    assert retried_data_sync["status"] == "retrying"
    assert data_sync_event["payload"]["resume_from_step"] == "data-sync"
    assert refreshed["approval_status"] == "approved"


def test_external_step_watchdog_fails_instead_of_hanging(tmp_path: Path):
    project_root = make_project(tmp_path)
    workflow = {"name": "plan", "version": 1, "steps": [{"name": "plan", "type": "llm", "instructions": "do", "output_schema": {}}]}
    service = OrchestrationService(project_root, runner=HangingRunner())
    service.store.create_task("plan", {"volume": 1}, workflow)
    task = service.store.list_tasks(limit=1)[0]

    service._run_plan_preflight = lambda *args, **kwargs: None
    service._watchdog_timeout_seconds = lambda step_name: 0.01
    asyncio.run(service._run_task(task["id"]))

    failed_task = service.get_task(task["id"])
    assert failed_task["status"] == "failed"
    assert failed_task["error"]["code"] == "LLM_TIMEOUT"
    assert failed_task["current_step"] == "plan"
    events = service.get_events(task["id"])
    assert any(event["message"] == "llm_request_started" for event in events)
    assert any(event["message"] == "llm_request_timed_out" for event in events)
    error_path = project_root / ".webnovel" / "observability" / "llm-runs" / f"{task['id']}-plan" / "error.json"
    assert error_path.is_file()


def test_runtime_status_aggregates_retry_and_waiting_approval(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    workflow = {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "context", "type": "llm"},
            {"name": "approval-gate", "type": "internal"},
        ],
    }
    task = service.store.create_task("write", {"chapter": 1}, workflow)
    service.store.update_task(task["id"], workflow_spec=workflow, status="running", current_step="context", started_at="2026-03-16T10:00:00")
    service.store.append_event(
        task["id"],
        "warning",
        "step_retry_started",
        step_name="context",
        payload={"attempt": 2, "retry_count": 1, "timeout_seconds": 120, "retryable": True},
    )

    retried = service.get_task(task["id"])
    runtime = retried["runtime_status"]
    assert runtime["step_state"] == "retrying"
    assert runtime["attempt"] == 2
    assert runtime["retry_count"] == 1
    assert runtime["target_label"] in {"第 1 章", "第 1 卷 · 第 1 章"}
    assert runtime["step_started_at"] is not None
    assert runtime["last_non_heartbeat_activity_at"] is not None

    service.store.mark_waiting_for_approval(
        task["id"],
        "approval-gate",
        {"status": "pending", "requested_at": "2026-03-16T10:05:00", "next_step": "data-sync"},
    )
    service.store.append_event(task["id"], "warning", "step_waiting_approval", step_name="approval-gate", payload={"retryable": True})
    waiting = service.get_task(task["id"])
    waiting_runtime = waiting["runtime_status"]
    assert waiting_runtime["step_state"] == "waiting_approval"
    assert waiting_runtime["phase_label"] == "回写审批"
    assert waiting_runtime["waiting_since"] is None


def test_list_task_summaries_returns_runtime_snapshot_without_full_events(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    workflow = {"name": "write", "version": 1, "steps": [{"name": "context", "type": "llm"}]}
    task = service.store.create_task("write", {"chapter": 3}, workflow)
    service.store.update_task(task["id"], workflow_spec=workflow, status="running", current_step="context")
    service.store.append_event(
        task["id"],
        "info",
        "request_dispatched",
        step_name="context",
        payload={"attempt": 1, "retry_count": 0, "timeout_seconds": 90},
    )

    summaries = service.list_task_summaries(limit=10)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["id"] == task["id"]
    assert summary["runtime_status"]["step_state"] == "running"
    assert summary["runtime_status"]["last_event_message"] == "request_dispatched"
    assert summary["runtime_status"]["timeout_seconds"] == 90


def test_approve_writeback_marks_task_resuming_before_scheduler_runs(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    workflow = {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "context", "type": "llm"},
            {"name": "approval-gate", "type": "internal"},
            {"name": "data-sync", "type": "llm"},
        ],
    }
    task = service.store.create_task("write", {"chapter": 1, "require_manual_approval": True}, workflow)
    service.store.update_task(task["id"], workflow_spec=workflow)
    service.store.mark_waiting_for_approval(
        task["id"],
        "approval-gate",
        {"status": "pending", "requested_at": "2026-03-16T10:05:00", "next_step": "data-sync"},
    )

    approved = service.approve_writeback(task["id"], "继续回写")
    events = service.get_events(task["id"])
    approval_event = next(event for event in reversed(events) if event["message"] == "Writeback approved")

    assert approved["status"] == "resuming_writeback"
    assert approved["approval_status"] == "approved"
    assert approval_event["payload"]["resume_from_step"] == "approval-gate"
    assert approval_event["payload"]["reason"] == "继续回写"


def test_long_running_step_emits_progress_and_heartbeat(tmp_path: Path):
    project_root = make_project(tmp_path)
    workflow = {"name": "plan", "version": 1, "steps": [{"name": "plan", "type": "llm", "instructions": "do", "output_schema": {}}]}
    service = OrchestrationService(project_root, runner=HeartbeatRunner())
    service.store.create_task("plan", {"volume": 1}, workflow)
    task = service.store.list_tasks(limit=1)[0]

    service._run_plan_preflight = lambda *args, **kwargs: None
    service._runner_heartbeat_seconds = lambda step_name: 0.01
    service._watchdog_timeout_seconds = lambda step_name: 0.2
    asyncio.run(service._run_task(task["id"]))

    refreshed = service.get_task(task["id"])
    events = service.get_events(task["id"])
    messages = [event["message"] for event in events]
    runtime = refreshed["runtime_status"]

    assert refreshed["status"] == "completed"
    assert runtime["phase_detail"] in {"当前步骤已完成。", "卷规划已完成。"}
    assert runtime["step_started_at"] is not None
    assert runtime["last_non_heartbeat_activity_at"] is not None
    assert runtime["waiting_since"] is None
    assert "prompt_compiled" in messages
    assert "request_dispatched" in messages
    assert "awaiting_model_response" in messages
    assert "step_heartbeat" in messages
    assert "response_received" in messages
    assert "parsing_output" in messages

    heartbeat_event = next(event for event in reversed(events) if event["message"] == "step_heartbeat")
    assert runtime["last_non_heartbeat_activity_at"] != heartbeat_event["timestamp"]


def test_runtime_status_waiting_since_ignores_heartbeat_resets(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    task = {
        "id": "task-1",
        "status": "running",
        "current_step": "plan",
        "updated_at": "2026-03-16T10:00:45",
    }
    events = [
        {"message": "request_dispatched", "step_name": "plan", "timestamp": "2026-03-16T10:00:01"},
        {"message": "step_heartbeat", "step_name": "plan", "timestamp": "2026-03-16T10:00:30"},
        {"message": "step_heartbeat", "step_name": "plan", "timestamp": "2026-03-16T10:00:45"},
    ]

    waiting_since = service._resolve_waiting_since(task, events, "plan", "running")
    last_non_heartbeat = service._resolve_last_non_heartbeat_activity_at(task, events, "plan")
    last_activity = service._resolve_last_activity_at(task, events[-1], last_non_heartbeat)

    assert waiting_since.isoformat() == service._parse_iso_datetime("2026-03-16T10:00:01").isoformat()
    assert last_activity == "2026-03-16T10:00:45"
    assert last_non_heartbeat == "2026-03-16T10:00:01"


def test_runtime_status_long_waiting_message_becomes_actionable(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    task = {
        "id": "task-1",
        "task_type": "write",
        "status": "running",
        "current_step": "context",
    }
    last_event = {
        "message": "awaiting_model_response",
        "payload": {},
        "step_name": "context",
        "timestamp": "2026-03-16T10:00:00",
    }

    detail = service._resolve_phase_detail(task, "context", "running", last_event, 1200, 1200)

    assert "可能已卡住" in detail


def test_cancel_task_marks_running_task_interrupted_with_cancel_code(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    workflow = {"name": "write", "version": 1, "steps": [{"name": "context", "type": "llm"}]}
    task = service.store.create_task("write", {"chapter": 2}, workflow)
    service.store.update_task(task["id"], workflow_spec=workflow)
    service.store.mark_running(task["id"], "context")

    cancelled = service.cancel_task(task["id"], "user requested stop")
    events = service.get_events(task["id"])

    assert cancelled["status"] == "interrupted"
    assert cancelled["error"]["code"] == "TASK_CANCELLED"
    assert any(event["payload"].get("reason") == "user requested stop" for event in events)


def test_runtime_status_hides_stale_error_after_retry_restart(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    workflow = {"name": "write", "version": 1, "steps": [{"name": "context", "type": "llm"}]}
    task = service.store.create_task("write", {"chapter": 3}, workflow)
    service.store.update_task(task["id"], workflow_spec=workflow)
    service.store.mark_running(task["id"], "context")
    service.store.append_event(
        task["id"],
        "error",
        "llm_request_failed",
        step_name="context",
        payload={"attempt": 1, "retry_count": 0, "error_code": "INVALID_STEP_OUTPUT", "retryable": True},
    )
    service.store.mark_failed(task["id"], "context", {"code": "INVALID_STEP_OUTPUT", "message": "bad json", "retryable": True})

    service.retry_task(task["id"])
    service.store.mark_running(task["id"], "context")
    service.store.append_event(task["id"], "info", "Step started: context", step_name="context", payload={"attempt": 1, "retry_count": 0})
    service.store.append_event(task["id"], "info", "llm_request_started", step_name="context", payload={"attempt": 1, "retry_count": 0})

    runtime = service.get_task(task["id"])["runtime_status"]

    assert runtime["step_state"] == "running"
    assert runtime["error_code"] is None
    assert runtime["retry_count"] == 0


def test_runtime_status_keeps_interrupted_and_cancelled_distinct(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=MappingRunner())
    workflow = {"name": "write", "version": 1, "steps": [{"name": "context", "type": "llm"}]}

    interrupted = service.store.create_task("write", {"chapter": 4}, workflow)
    service.store.update_task(interrupted["id"], workflow_spec=workflow)
    service.store.mark_running(interrupted["id"], "context")
    service.store.mark_interrupted(interrupted["id"], "context", "service interrupted")

    cancelled = service.store.create_task("write", {"chapter": 5}, workflow)
    service.store.update_task(cancelled["id"], workflow_spec=workflow)
    service.store.mark_running(cancelled["id"], "context")
    service.cancel_task(cancelled["id"], "user requested stop")

    interrupted_runtime = service.get_task(interrupted["id"])["runtime_status"]
    cancelled_runtime = service.get_task(cancelled["id"])["runtime_status"]

    assert interrupted_runtime["step_state"] == "interrupted"
    assert cancelled_runtime["step_state"] == "cancelled"
