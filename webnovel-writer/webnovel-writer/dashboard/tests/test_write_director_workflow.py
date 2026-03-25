from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from dashboard.llm_runner import StepResult
from dashboard.orchestrator import BODY_DIR_NAME, OUTLINE_DIR_NAME, OUTLINE_SUMMARY_FILE, OrchestrationService
from scripts.init_project import build_initial_planning_profile


def step_result(step_name: str, payload: dict, *, success: bool = True) -> StepResult:
    return StepResult(
        step_name=step_name,
        success=success,
        return_code=0 if success else 1,
        timing_ms=10,
        stdout=json.dumps(payload, ensure_ascii=False),
        stderr="",
        structured_output=payload,
        prompt_file="prompt.md",
        output_file="output.json",
        error=None if success else {"code": "STEP_FAILED", "message": "failed"},
        metadata={"attempt": 1, "retry_count": 0},
    )


class SequenceRunner:
    def __init__(self, mapping: dict[str, list[StepResult] | StepResult]):
        self.mapping = mapping
        self.calls: list[str] = []

    def probe(self):
        return {"provider": "test-runner", "installed": True, "configured": True}

    def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
        step_name = step_spec["name"]
        self.calls.append(step_name)
        payload = self.mapping[step_name]
        if isinstance(payload, list):
            assert payload, f"no queued result for {step_name}"
            return payload.pop(0)
        return payload


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    planning_profile = build_initial_planning_profile(
        title="Night Rain Archive",
        genre="Urban Supernatural",
        protagonist_name="Shen Yan",
        golden_finger_name="Rewind 10 Minutes",
        core_selling_points="Costly rewind and anomaly investigation",
        protagonist_desire="Find the truth behind his mother's disappearance",
        protagonist_flaw="Relies too heavily on the power",
        protagonist_archetype="Watch repairer",
        protagonist_structure="Keeps an old repair shop alone after the disappearance",
        factions="Bureau | Official | Monitor and potential ally",
        power_system_type="Urban anomalies and inspection rules",
        gf_irreversible_cost="Loses one memory permanently on every rewind",
    )
    planning_profile.update(
        {
            "volume_1_title": "First Rewind in the Rain",
            "volume_1_conflict": "The protagonist must decode repeated anomaly warnings before he forgets more.",
            "volume_1_climax": "The protagonist exposes traces of the rewind at an observation point.",
            "major_characters_text": "Shen Yan | protagonist | self | discovers the cost in volume 1",
            "foreshadowing_text": "Repeated warning source | 1 | 5 | A",
        }
    )
    state = {
        "project_info": {"title": "Night Rain Archive", "genre": "Urban Supernatural"},
        "progress": {"current_chapter": 0, "total_words": 0},
        "planning": {"profile": planning_profile, "readiness": {}},
        "plot_threads": {"active_threads": [], "foreshadowing": []},
        "chapter_meta": {},
        "disambiguation_warnings": [],
        "disambiguation_pending": [],
    }
    (webnovel_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    (webnovel_dir / "planning-profile.json").write_text(
        json.dumps(planning_profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    outline_dir = project_root / OUTLINE_DIR_NAME
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / OUTLINE_SUMMARY_FILE).write_text("# Outline\n", encoding="utf-8")
    (project_root / BODY_DIR_NAME).mkdir(parents=True, exist_ok=True)
    return project_root


def make_service(project_root: Path, runner: SequenceRunner) -> OrchestrationService:
    with patch("dashboard.orchestrator.get_client") as mock_get_client:
        mock_get_client.return_value.probe.return_value = {"configured": True}
        return OrchestrationService(project_root, runner=runner)


def long_content(title: str) -> str:
    return f"# {title}\n" + ("Rain archive memory cost " * 50)


def context_payload(chapter: int = 1) -> dict:
    return {
        "story_plan": {"anchor_chapter": chapter, "chapters": [chapter]},
        "director_brief": {"chapter": chapter, "chapter_goal": "Push the anomaly thread forward"},
        "task_brief": {"chapter": chapter},
        "contract_v2": {"chapter": chapter},
        "draft_prompt": "write",
    }


def review_payload(step_name: str, chapter: int = 1, score: float = 91.0, *, issues: list[dict] | None = None, passed: bool = True) -> dict:
    return {
        "agent": step_name,
        "chapter": chapter,
        "overall_score": score,
        "pass": passed,
        "issues": issues or [],
        "metrics": {"consistency": score},
        "summary": "ok",
    }


def test_write_task_waits_for_chapter_brief_approval_before_context(tmp_path: Path):
    project_root = make_project(tmp_path)
    chapter_file = f"{BODY_DIR_NAME}/ch0001.md"
    content = long_content("Chapter 1")
    runner = SequenceRunner(
        {
            "context": step_result("context", context_payload()),
            "draft": step_result("draft", {"chapter_file": chapter_file, "content": content, "word_count": len(''.join(content.split()))}),
            "consistency-review": step_result("consistency-review", review_payload("consistency-review")),
            "continuity-review": step_result("continuity-review", review_payload("continuity-review")),
            "ooc-review": step_result("ooc-review", review_payload("ooc-review")),
            "polish": step_result("polish", {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []}),
            "data-sync": step_result("data-sync", {"files_written": [chapter_file], "summary_file": ".webnovel/summaries/ch0001.md", "state_updated": True, "index_updated": True}),
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 1, "require_manual_approval": False})

    assert task["status"] == "awaiting_chapter_brief_approval"
    assert task["current_step"] == "chapter-brief-approval"
    assert task["approval_status"] == "pending"
    assert runner.calls == []
    brief = (((task.get("artifacts") or {}).get("step_results") or {}).get("chapter-director") or {}).get("structured_output") or {}
    assert brief["chapter"] == 1


def test_approved_chapter_brief_resumes_write_and_auto_completes_writeback(tmp_path: Path):
    project_root = make_project(tmp_path)
    chapter_file = f"{BODY_DIR_NAME}/ch0001.md"
    content = long_content("Chapter 1")
    runner = SequenceRunner(
        {
            "context": step_result("context", context_payload()),
            "draft": step_result("draft", {"chapter_file": chapter_file, "content": content, "word_count": len(''.join(content.split()))}),
            "consistency-review": step_result("consistency-review", review_payload("consistency-review")),
            "continuity-review": step_result("continuity-review", review_payload("continuity-review")),
            "ooc-review": step_result("ooc-review", review_payload("ooc-review")),
            "polish": step_result("polish", {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []}),
            "data-sync": step_result(
                "data-sync",
                {
                    "files_written": [chapter_file],
                    "summary_file": ".webnovel/summaries/ch0001.md",
                    "state_updated": True,
                    "index_updated": True,
                    "world_rules": [{"name": "Every rewind burns one memory", "summary": "Hard rule"}],
                    "foreshadowing_items": [{"name": "Warning source", "content": "A hidden watcher", "planted_chapter": 1, "planned_payoff_chapter": 3, "status": "active"}],
                    "character_arcs": [{"entity_id": "Shen Yan", "chapter": 1, "arc_stage": "hesitant", "relationship_state": {"Bureau": "suspicious"}}],
                    "knowledge_states": [{"entity_id": "Shen Yan", "chapter": 1, "topic": "rewind cost", "belief": "memory loss is cumulative", "truth_status": "partial", "confidence": 0.8}],
                },
            ),
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 1, "require_manual_approval": False})
    approved = service.approve_writeback(task["id"], reason="approve brief")
    asyncio.run(service._run_task(task["id"], resume_from_step=approved.get("current_step") or "chapter-brief-approval"))
    completed = service.get_task(task["id"])
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))

    assert completed["status"] == "completed"
    assert "approval-gate" not in runner.calls
    assert (project_root / service._default_chapter_file(1)).is_file()
    assert state["voice_bible"]
    assert state["mystery_ledger"]
    assert state["rule_assertions"]
    assert state["trust_map"]
    assert state["director_decisions"]
    assert state["plot_threads"]["active_threads"]


def test_write_uses_word_count_from_same_source_as_selected_content(tmp_path: Path):
    project_root = make_project(tmp_path)
    chapter_file = f"{BODY_DIR_NAME}/ch0001.md"
    draft_content = long_content("Draft Chapter 1")
    polished_content = long_content("Polished Chapter 1") * 8
    draft_word_count = len("".join(draft_content.split()))
    polished_word_count = len("".join(polished_content.split()))
    runner = SequenceRunner(
        {
            "context": step_result("context", context_payload()),
            "draft": step_result("draft", {"chapter_file": chapter_file, "content": draft_content, "word_count": draft_word_count}),
            "consistency-review": step_result("consistency-review", review_payload("consistency-review")),
            "continuity-review": step_result("continuity-review", review_payload("continuity-review")),
            "ooc-review": step_result("ooc-review", review_payload("ooc-review")),
            "polish": step_result(
                "polish",
                {
                    "chapter_file": chapter_file,
                    "content": polished_content,
                    "anti_ai_force_check": "pass",
                    "change_summary": [],
                },
            ),
            "data-sync": step_result(
                "data-sync",
                {
                    "files_written": [chapter_file],
                    "summary_file": ".webnovel/summaries/ch0001.md",
                    "state_updated": True,
                    "index_updated": True,
                    "chapter_meta": {"title": "Chapter 1", "location": "Night Rain City", "characters": ["Shen Yan"]},
                },
            ),
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 1, "require_manual_approval": False})
    approved = service.approve_writeback(task["id"], reason="approve brief")
    asyncio.run(service._run_task(task["id"], resume_from_step=approved.get("current_step") or "chapter-brief-approval"))
    completed = service.get_task(task["id"])

    assert completed["status"] == "completed"
    chapter_record = service.index_manager.get_chapter(1)
    assert chapter_record is not None
    assert chapter_record["word_count"] == polished_word_count
