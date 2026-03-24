import asyncio
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
        stdout=json.dumps(payload, ensure_ascii=False) if payload is not None else "",
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


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    (webnovel_dir / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "Story Director Test", "genre": "Urban Fantasy"},
                "progress": {"current_chapter": 2, "total_words": 6000},
                "protagonist_state": {"name": "Shen Yan", "location": {"current": "Night Rain City"}},
                "chapter_meta": {},
                "disambiguation_warnings": [],
                "disambiguation_pending": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    outline_dir = project_root / "大纲"
    outline_dir.mkdir(parents=True)
    (outline_dir / "总纲.md").write_text("# outline\ncurrent arc", encoding="utf-8")
    return project_root


def _sample_story_plan(anchor_chapter: int, chapter_goal: str) -> dict:
    return {
        "anchor_chapter": anchor_chapter,
        "planning_horizon": 4,
        "priority_threads": ["rain warning", "trust fracture"],
        "payoff_schedule": [{"thread": "rain warning", "target_chapter": anchor_chapter, "mode": "major"}],
        "defer_schedule": [{"thread": "final mastermind", "not_before_chapter": anchor_chapter + 3, "reason": "too early"}],
        "risk_flags": ["Need visible action this chapter."],
        "transition_notes": ["Convert clue pressure into action pressure."],
        "chapters": [
            {
                "chapter": anchor_chapter,
                "role": "current-execution",
                "chapter_goal": chapter_goal,
                "must_advance_threads": ["rain warning", "trust fracture"],
                "optional_payoffs": ["rain warning"],
                "forbidden_resolutions": ["Do not reveal the mastermind this chapter."],
                "ending_hook_target": "Force Shen Yan into the tower by chapter end.",
            }
        ],
        "rationale": "Current window should turn setup into movement.",
    }


def test_story_director_internal_step_persists_plan_and_chapter_director_uses_current_slot(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=SequenceRunner({}))
    workflow = {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "story-director", "type": "internal"},
            {"name": "chapter-director", "type": "internal"},
        ],
    }
    task = service.store.create_task("write", {"chapter": 3}, workflow)
    current = service.store.get_task(task["id"]) or task
    plan = _sample_story_plan(3, "Turn the warning clue into visible action and cost.")
    service._build_story_plan = lambda _task: plan  # type: ignore[method-assign]

    outcome = asyncio.run(service._run_internal_step(task["id"], current, workflow, workflow["steps"][0], 0))

    assert outcome == "ok"
    saved_task = service.store.get_task(task["id"]) or {}
    saved_plan = (((saved_task.get("artifacts") or {}).get("step_results") or {}).get("story-director") or {}).get("structured_output") or {}
    assert saved_plan["anchor_chapter"] == 3
    story_plan_file = project_root / ".webnovel" / "story-director" / "plan-ch0003.json"
    assert story_plan_file.is_file()

    current = service.store.get_task(task["id"]) or task
    outcome = asyncio.run(service._run_internal_step(task["id"], current, workflow, workflow["steps"][1], 1))
    assert outcome == "ok"

    refreshed = service.store.get_task(task["id"]) or {}
    brief = (((refreshed.get("artifacts") or {}).get("step_results") or {}).get("chapter-director") or {}).get("structured_output") or {}
    assert brief["chapter_goal"] == "Turn the warning clue into visible action and cost."
    assert "rain warning" in brief["must_advance_threads"]
    assert brief["ending_hook_target"] == "Force Shen Yan into the tower by chapter end."


def test_retry_from_context_reuses_story_plan_but_story_retry_refreshes(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "context": [
                step_result("context", {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"}),
                step_result("context", {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"}),
            ]
        }
    )
    service = OrchestrationService(project_root, runner=runner)
    workflow = {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "story-director", "type": "internal"},
            {"name": "chapter-director", "type": "internal"},
            {
                "name": "context",
                "type": "codex",
                "template": "write-context.md",
                "required_output_keys": ["story_plan", "director_brief", "task_brief", "contract_v2", "draft_prompt"],
            },
        ],
    }
    task = service.store.create_task("write", {"chapter": 2}, workflow)
    service.store.update_task(task["id"], workflow_spec=workflow)
    original_plan = _sample_story_plan(2, "Original story plan goal.")
    service._build_story_plan = lambda _task: original_plan  # type: ignore[method-assign]
    current = service.store.get_task(task["id"]) or task
    asyncio.run(service._run_internal_step(task["id"], current, workflow, workflow["steps"][0], 0))
    current = service.store.get_task(task["id"]) or task
    asyncio.run(service._run_internal_step(task["id"], current, workflow, workflow["steps"][1], 1))

    saved_plan = json.loads((project_root / ".webnovel" / "story-director" / "plan-ch0002.json").read_text(encoding="utf-8"))

    refreshed_plan = _sample_story_plan(2, "Refreshed story plan goal.")
    refreshed_plan["rationale"] = "Refreshed rationale."
    service._build_story_plan = lambda _task: refreshed_plan  # type: ignore[method-assign]

    service.store.update_task(task["id"], status="failed", current_step="context", error={"code": "STEP_FAILED", "message": "context failed"})
    retried = service.retry_task(task["id"])
    assert retried["status"] == "retrying"
    asyncio.run(service._run_task(task["id"], resume_from_step="context"))
    reused_plan = json.loads((project_root / ".webnovel" / "story-director" / "plan-ch0002.json").read_text(encoding="utf-8"))
    assert reused_plan["rationale"] == saved_plan["rationale"]

    service.store.update_task(task["id"], status="failed", current_step="context", error={"code": "STEP_FAILED", "message": "context failed again"})
    service.retry_task(task["id"], resume_from_step="story-director")
    asyncio.run(service._run_task(task["id"], resume_from_step="story-director"))
    updated_plan = json.loads((project_root / ".webnovel" / "story-director" / "plan-ch0002.json").read_text(encoding="utf-8"))
    assert updated_plan["rationale"] == "Refreshed rationale."


def test_get_task_story_plan_reuses_covering_plan_when_exact_anchor_file_is_missing(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=SequenceRunner({}))
    plan = _sample_story_plan(3, "Current slot goal.")
    plan["chapters"].append(
        {
            "chapter": 4,
            "role": "transition",
            "chapter_goal": "Follow-up chapter goal.",
            "must_advance_threads": ["rain warning"],
            "optional_payoffs": ["tower clue"],
            "forbidden_resolutions": ["Do not reveal the mastermind this chapter."],
            "ending_hook_target": "Push Shen Yan toward the tower again.",
        }
    )
    service._write_story_plan(3, plan)

    task = service.store.create_task("write", {"chapter": 4}, {"name": "write", "version": 1, "steps": []})
    stored = service._get_task_story_plan(task, 4)

    assert stored["anchor_chapter"] == 3
    assert any(item["chapter"] == 4 for item in stored["chapters"])
    assert next(item for item in stored["chapters"] if item["chapter"] == 4)["chapter_goal"] == "Follow-up chapter goal."
