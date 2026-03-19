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
                "project_info": {"title": "Guarded Runner Test", "genre": "Urban Fantasy"},
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


def test_guarded_runner_stops_before_child_when_previous_story_refresh_requests_replan(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=1)
    service = OrchestrationService(project_root, runner=SequenceRunner({}))
    previous = service.store.create_task("write", {"chapter": 1}, {"name": "write", "version": 1, "steps": []})
    artifacts = dict(previous.get("artifacts") or {})
    artifacts["writeback"] = {
        "story_refresh": {
            "should_refresh": True,
            "recommended_resume_from": "story-director",
            "suggested_action": "refresh before chapter 2",
        }
    }
    service.store.update_task(previous["id"], status="completed", artifacts=artifacts)
    service._load_workflow = lambda task_type: guarded_workflow() if task_type == "guarded-write" else {"name": "write", "version": 1, "steps": []}  # type: ignore[method-assign]

    task = service.run_task_sync("guarded-write", {"chapter": 2, "require_manual_approval": False})

    result = (((task.get("artifacts") or {}).get("step_results") or {}).get("guarded-chapter-runner") or {}).get("structured_output") or {}
    assert task["status"] == "completed"
    assert result["outcome"] == "blocked_story_refresh"
    assert result["parent_task_id"] == task["id"]
    assert result["trigger_source"] == "guarded-chapter-runner"
    assert result["child_task_id"] is None
    assert len([item for item in service.store.list_tasks(limit=20) if item.get("task_type") == "write"]) == 1


def test_guarded_runner_stops_when_child_review_gate_blocks(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=1)
    runner = SequenceRunner(
        {
            "context": step_result("context", {"task_brief": {}}),
            "consistency-review": step_result(
                "consistency-review",
                {
                    "overall_score": 42,
                    "pass": False,
                    "issues": [{"severity": "critical", "title": "Continuity break"}],
                    "metrics": {},
                    "summary": "blocked",
                },
            ),
        }
    )
    service = OrchestrationService(project_root, runner=runner)
    write_workflow = {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "context", "type": "codex"},
            {
                "name": "consistency-review",
                "type": "codex",
                "required_output_keys": ["overall_score", "pass", "issues", "metrics", "summary"],
                "output_schema": {"overall_score": 0, "pass": True, "issues": [], "metrics": {}, "summary": "string"},
            },
            {"name": "review-summary", "type": "internal"},
        ],
    }
    service._load_workflow = lambda task_type: guarded_workflow() if task_type == "guarded-write" else write_workflow  # type: ignore[method-assign]

    task = service.run_task_sync("guarded-write", {"chapter": 2, "require_manual_approval": False})

    result = (((task.get("artifacts") or {}).get("step_results") or {}).get("guarded-chapter-runner") or {}).get("structured_output") or {}
    child = service.store.get_task(result["child_task_id"]) or {}
    assert task["status"] == "completed"
    assert result["outcome"] == "blocked_by_review"
    assert child["parent_task_id"] == task["id"]
    assert child["parent_step_name"] == "guarded-chapter-runner"
    assert child["root_task_id"] == task["id"]
    assert child["trigger_source"] == "guarded-write"
    assert child["status"] == "failed"
    assert child["error"]["code"] == "REVIEW_GATE_BLOCKED"


def test_guarded_runner_stops_when_child_requires_manual_approval(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=1)
    runner = SequenceRunner({"context": step_result("context", {"task_brief": {}})})
    service = OrchestrationService(project_root, runner=runner)
    write_workflow = {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "context", "type": "codex"},
            {"name": "approval-gate", "type": "internal"},
        ],
    }
    service._load_workflow = lambda task_type: guarded_workflow() if task_type == "guarded-write" else write_workflow  # type: ignore[method-assign]

    task = service.run_task_sync("guarded-write", {"chapter": 2, "require_manual_approval": True})

    result = (((task.get("artifacts") or {}).get("step_results") or {}).get("guarded-chapter-runner") or {}).get("structured_output") or {}
    child = service.store.get_task(result["child_task_id"]) or {}
    assert task["status"] == "completed"
    assert result["outcome"] == "stopped_for_approval"
    assert child["parent_task_id"] == task["id"]
    assert child["trigger_source"] == "guarded-write"
    assert child["status"] == "awaiting_writeback_approval"
    assert child["approval_status"] == "pending"


def test_guarded_runner_completes_exactly_one_child_chapter_and_proposes_next_step(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=1)
    runner = SequenceRunner({"data-sync": step_result("data-sync", {"index_updated": True})})
    service = OrchestrationService(project_root, runner=runner)
    write_workflow = {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "data-sync", "type": "codex"},
        ],
    }
    service._load_workflow = lambda task_type: guarded_workflow() if task_type == "guarded-write" else write_workflow  # type: ignore[method-assign]

    def fake_apply_write_data_sync(task_id: str, task: dict, payload: dict) -> None:
        latest = service.store.get_task(task_id) or task
        artifacts = dict(latest.get("artifacts") or {})
        artifacts["writeback"] = {
            "story_refresh": {"should_refresh": False, "suggested_action": ""},
            "story_alignment": {"satisfied": ["hit current slot"], "missed": [], "deferred": []},
            "director_alignment": {"satisfied": ["met brief"], "missed": [], "deferred": []},
        }
        service.store.update_task(task_id, artifacts=artifacts)

    service._apply_write_data_sync = fake_apply_write_data_sync  # type: ignore[method-assign]

    task = service.run_task_sync("guarded-write", {"chapter": 2, "require_manual_approval": False})

    result = (((task.get("artifacts") or {}).get("step_results") or {}).get("guarded-chapter-runner") or {}).get("structured_output") or {}
    write_tasks = [item for item in service.store.list_tasks(limit=20) if item.get("task_type") == "write"]
    child = service.store.get_task(result["child_task_id"]) or {}
    assert task["status"] == "completed"
    assert result["outcome"] == "completed_one_chapter"
    assert result["parent_task_id"] == task["id"]
    assert result["next_action"]["next_recommended_chapter"] == 3
    assert child["parent_task_id"] == task["id"]
    assert child["trigger_source"] == "guarded-write"
    assert result["safe_to_continue"] is True
    assert result["next_action"]["can_enqueue_next"] is True
    assert result["next_action"]["next_chapter"] == 3
    assert len(write_tasks) == 1
