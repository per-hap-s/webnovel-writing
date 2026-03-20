from __future__ import annotations

import json
from pathlib import Path

from dashboard.llm_runner import StepResult
from dashboard.orchestrator import OrchestrationService


def step_result(step_name: str, payload: dict | None = None, *, success: bool = True) -> StepResult:
    payload = payload if payload is not None else {}
    return StepResult(
        step_name=step_name,
        success=success,
        return_code=0 if success else 1,
        timing_ms=50,
        stdout=json.dumps(payload, ensure_ascii=False),
        stderr="",
        structured_output=payload,
        prompt_file="prompt.md",
        output_file="output.json",
        error=None if success else {"code": "STEP_FAILED", "message": "failed"},
        metadata={"attempt": 1, "retry_count": 0},
    )


class SequenceRunner:
    def __init__(self, responses: dict[str, list[StepResult] | StepResult]):
        self.responses = responses

    def probe(self):
        return {
            "provider": "codex-cli",
            "mode": "cli",
            "installed": True,
            "configured": True,
            "connection_status": "connected",
        }

    def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
        item = self.responses[step_spec["name"]]
        if isinstance(item, list):
            if len(item) == 1:
                return item[0]
            return item.pop(0)
        return item


def make_project(tmp_path: Path, *, current_chapter: int = 1) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    (webnovel_dir / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "Guarded Batch Runner Test", "genre": "Urban Fantasy"},
                "progress": {"current_chapter": current_chapter, "total_words": 6000},
                "chapter_meta": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project_root


def guarded_workflow() -> dict:
    return {"name": "guarded-write", "version": 1, "steps": [{"name": "guarded-chapter-runner", "type": "internal"}]}


def guarded_batch_workflow() -> dict:
    return {"name": "guarded-batch-write", "version": 1, "steps": [{"name": "guarded-batch-runner", "type": "internal"}]}


def write_workflow() -> dict:
    return {"name": "write", "version": 1, "steps": [{"name": "data-sync", "type": "codex"}]}


def test_guarded_batch_runner_completes_requested_chapters(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=1)
    runner = SequenceRunner({"data-sync": [step_result("data-sync", {"index_updated": True}), step_result("data-sync", {"index_updated": True})]})
    service = OrchestrationService(project_root, runner=runner)
    service._load_workflow = lambda task_type: guarded_batch_workflow() if task_type == "guarded-batch-write" else guarded_workflow() if task_type == "guarded-write" else write_workflow()  # type: ignore[method-assign]

    def fake_apply_write_data_sync(task_id: str, task: dict, payload: dict) -> None:
        chapter = int((task.get("request") or {}).get("chapter") or 0)
        latest = service.store.get_task(task_id) or task
        artifacts = dict(latest.get("artifacts") or {})
        artifacts["writeback"] = {
            "story_refresh": {"should_refresh": False, "suggested_action": ""},
            "story_alignment": {"satisfied": [f"story:{chapter}"], "missed": [], "deferred": []},
            "director_alignment": {"satisfied": [f"director:{chapter}"], "missed": [], "deferred": []},
        }
        service.store.update_task(task_id, artifacts=artifacts)

    service._apply_write_data_sync = fake_apply_write_data_sync  # type: ignore[method-assign]

    task = service.run_task_sync("guarded-batch-write", {"start_chapter": 2, "max_chapters": 2, "require_manual_approval": False})

    result = (((task.get("artifacts") or {}).get("step_results") or {}).get("guarded-batch-runner") or {}).get("structured_output") or {}
    guarded_children = [item for item in service.store.list_tasks(limit=20) if item.get("task_type") == "guarded-write"]
    write_children = [item for item in service.store.list_tasks(limit=20) if item.get("task_type") == "write"]
    assert task["status"] == "completed"
    assert result["outcome"] == "completed_requested_batch"
    assert result["completed_chapters"] == 2
    assert len(result["runs"]) == 2
    assert result["runs"][0]["chapter"] == 2
    assert result["runs"][1]["chapter"] == 3
    assert result["operator_actions"][0]["kind"] == "launch-task"
    assert result["operator_actions"][0]["task_type"] == "guarded-batch-write"
    assert result["operator_actions"][1]["kind"] == "open-task"
    assert len(guarded_children) == 2
    assert len(write_children) == 2


def test_guarded_batch_runner_stops_when_child_requests_story_refresh(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=1)
    runner = SequenceRunner({"data-sync": step_result("data-sync", {"index_updated": True})})
    service = OrchestrationService(project_root, runner=runner)
    service._load_workflow = lambda task_type: guarded_batch_workflow() if task_type == "guarded-batch-write" else guarded_workflow() if task_type == "guarded-write" else write_workflow()  # type: ignore[method-assign]

    def fake_apply_write_data_sync(task_id: str, task: dict, payload: dict) -> None:
        latest = service.store.get_task(task_id) or task
        artifacts = dict(latest.get("artifacts") or {})
        artifacts["writeback"] = {
            "story_refresh": {
                "should_refresh": True,
                "recommended_resume_from": "chapter-director",
                "suggested_action": "refresh before next chapter",
            },
            "story_alignment": {"satisfied": [], "missed": ["thread:drift"], "deferred": []},
            "director_alignment": {"satisfied": [], "missed": ["payoff:drift"], "deferred": []},
        }
        service.store.update_task(task_id, artifacts=artifacts)

    service._apply_write_data_sync = fake_apply_write_data_sync  # type: ignore[method-assign]

    task = service.run_task_sync("guarded-batch-write", {"start_chapter": 2, "max_chapters": 3, "require_manual_approval": False})

    result = (((task.get("artifacts") or {}).get("step_results") or {}).get("guarded-batch-runner") or {}).get("structured_output") or {}
    guarded_children = [item for item in service.store.list_tasks(limit=20) if item.get("task_type") == "guarded-write"]
    assert task["status"] == "completed"
    assert result["outcome"] == "blocked_story_refresh"
    assert result["completed_chapters"] == 1
    assert result["next_action"]["can_enqueue_next"] is False
    assert result["story_refresh"]["should_refresh"] is True
    assert result["operator_actions"][0]["kind"] == "retry-task"
    assert result["operator_actions"][0]["resume_from_step"] == "chapter-director"
    assert result["operator_actions"][1]["kind"] == "open-task"
    assert len(result["runs"]) == 1
    assert len(guarded_children) == 1


def test_guarded_batch_runner_fails_when_child_task_fails_unexpectedly(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=1)
    runner = SequenceRunner({"data-sync": step_result("data-sync", success=False)})
    service = OrchestrationService(project_root, runner=runner)
    service._load_workflow = lambda task_type: guarded_batch_workflow() if task_type == "guarded-batch-write" else guarded_workflow() if task_type == "guarded-write" else write_workflow()  # type: ignore[method-assign]

    task = service.run_task_sync("guarded-batch-write", {"start_chapter": 2, "max_chapters": 2, "require_manual_approval": False})

    result = (((task.get("artifacts") or {}).get("step_results") or {}).get("guarded-batch-runner") or {}).get("structured_output") or {}
    assert task["status"] == "failed"
    assert (task.get("error") or {}).get("message") == "护栏批量推进在第 2 章停止：护栏子任务未成功完成：failed"
    assert result["outcome"] == "child_task_failed"
    assert result["completed_chapters"] == 0
    assert result["last_child_task_status"] == "failed"
    assert result["next_action"]["reason"] == "护栏子任务未成功完成：failed"
    assert result["next_action"]["can_enqueue_next"] is False
    assert result["operator_actions"][0]["kind"] == "open-task"
    assert result["operator_actions"][0]["task_id"] == result["last_child_task_id"]
    assert len(result["runs"]) == 1
