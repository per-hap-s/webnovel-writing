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
                "project_info": {"title": "Director Test", "genre": "Urban Fantasy"},
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
    (outline_dir / "总纲.md").write_text("# outline\n", encoding="utf-8")
    return project_root


def test_chapter_director_internal_step_persists_brief_and_file(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root, runner=SequenceRunner({}))
    workflow = {"name": "write", "version": 1, "steps": [{"name": "chapter-director", "type": "internal"}]}
    task = service.store.create_task("write", {"chapter": 3}, workflow)
    current = service.store.get_task(task["id"]) or task

    outcome = asyncio.run(service._run_internal_step(task["id"], current, workflow, workflow["steps"][0], 0))

    assert outcome == "ok"
    saved = service.store.get_task(task["id"]) or {}
    brief = (((saved.get("artifacts") or {}).get("step_results") or {}).get("chapter-director") or {}).get("structured_output") or {}
    assert brief["chapter"] == 3
    assert brief["chapter_goal"]
    assert isinstance(brief["must_advance_threads"], list)
    director_file = project_root / ".webnovel" / "director" / "ch0003.json"
    assert director_file.is_file()
    assert json.loads(director_file.read_text(encoding="utf-8"))["chapter"] == 3


def test_retry_from_context_reuses_director_brief_but_director_retry_refreshes(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "context": [
                step_result("context", {"director_brief": {}, "task_brief": {}, "contract_v2": {}, "draft_prompt": "write"}),
                step_result("context", {"director_brief": {}, "task_brief": {}, "contract_v2": {}, "draft_prompt": "write"}),
            ]
        }
    )
    service = OrchestrationService(project_root, runner=runner)
    workflow = {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "chapter-director", "type": "internal"},
            {
                "name": "context",
                "type": "codex",
                "template": "write-context.md",
                "required_output_keys": ["director_brief", "task_brief", "contract_v2", "draft_prompt"],
            },
        ],
    }
    task = service.store.create_task("write", {"chapter": 2}, workflow)
    service.store.update_task(task["id"], workflow_spec=workflow)
    current = service.store.get_task(task["id"]) or task
    asyncio.run(service._run_internal_step(task["id"], current, workflow, workflow["steps"][0], 0))

    original_brief = json.loads((project_root / ".webnovel" / "director" / "ch0002.json").read_text(encoding="utf-8"))

    service._build_chapter_director_brief = lambda _task: {  # type: ignore[method-assign]
        **original_brief,
        "chapter_goal": "This should only appear after retrying chapter-director itself.",
    }

    service.store.update_task(task["id"], status="failed", current_step="context", error={"code": "STEP_FAILED", "message": "context failed"})
    retried = service.retry_task(task["id"])
    assert retried["status"] == "retrying"
    asyncio.run(service._run_task(task["id"], resume_from_step="context"))
    reused_brief = json.loads((project_root / ".webnovel" / "director" / "ch0002.json").read_text(encoding="utf-8"))
    assert reused_brief["chapter_goal"] == original_brief["chapter_goal"]

    service.store.update_task(task["id"], status="failed", current_step="context", error={"code": "STEP_FAILED", "message": "context failed again"})
    service.retry_task(task["id"], resume_from_step="chapter-director")
    asyncio.run(service._run_task(task["id"], resume_from_step="chapter-director"))
    refreshed_brief = json.loads((project_root / ".webnovel" / "director" / "ch0002.json").read_text(encoding="utf-8"))
    assert refreshed_brief["chapter_goal"] == "This should only appear after retrying chapter-director itself."
