from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from dashboard.llm_runner import StepResult
from dashboard.orchestrator import (
    BODY_DIR_NAME,
    OUTLINE_DIR_NAME,
    OUTLINE_SUMMARY_FILE,
    OrchestrationService,
    REVIEW_REPORT_DIR_NAME,
    SETTINGS_DIR_NAME,
)
from scripts.init_project import _build_master_outline, build_initial_planning_profile


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
    )


class MappingRunner:
    def __init__(self, mapping: dict[str, dict]):
        self.mapping = mapping
        self.prompt_bundles: list[tuple[str, dict]] = []

    def probe(self):
        return {"provider": "test-runner", "installed": True, "configured": True}

    def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
        self.prompt_bundles.append((step_spec["name"], prompt_bundle))
        payload = self.mapping[step_spec["name"]]
        return step_result(step_spec["name"], payload)


class SequenceRunner:
    def __init__(self, mapping: dict[str, list[StepResult] | StepResult]):
        self.mapping = mapping
        self.calls: list[str] = []

    def probe(self):
        return {"provider": "sequence-runner", "installed": True, "configured": True}

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
    (project_root / ".webnovel" / "summaries").mkdir(parents=True)
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
    }
    (project_root / ".webnovel" / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    outline_dir = project_root / OUTLINE_DIR_NAME
    outline_dir.mkdir(parents=True, exist_ok=True)
    (outline_dir / OUTLINE_SUMMARY_FILE).write_text(
        "\n".join(
            [
                "# 总纲",
                "",
                "## 故事前提",
                "- 书名：Night Rain Archive",
                "- 题材：Urban Supernatural",
                "- 一句话梗概：Costly rewind and anomaly investigation",
                "- 主角：Shen Yan",
                "- 主角身份：Watch repairer",
                "- 主角初始状态：Keeps an old repair shop alone after the disappearance",
                "- 核心设定：Rewind 10 Minutes",
                "- 能力代价：Loses one memory permanently on every rewind",
                "",
                "## 主线推进",
                "- 主角当前欲望：Find the truth behind his mother's disappearance",
                "- 主角核心缺陷：Relies too heavily on the power",
                "- 第1卷标题：First Rewind in the Rain",
                "- 第1卷核心冲突：The protagonist must decode repeated anomaly warnings before he forgets more.",
                "- 第1卷高潮：The protagonist exposes traces of the rewind at an observation point.",
                "",
                "## 主要角色",
                "- Shen Yan | protagonist | self | discovers the cost in volume 1",
                "",
                "## 势力",
                "- Bureau | Official | Monitor and potential ally",
                "",
                "## 规则梗概",
                "- Urban anomalies and inspection rules",
                "",
                "## 伏笔与回收",
                "- Repeated warning source | 1 | 5 | A",
                "",
                "## 卷结构",
                "",
                "### 第1卷（第1-50章）",
                "- 卷目标：Learn the rewind rules and get pulled into the bureau line.",
                "- 核心冲突：Trade memory for survival.",
                "- 升级与代价：Each successful rewind costs more identity.",
                "- 关键爽点：Win through information asymmetry.",
                "- 阶段敌手/阻力：Outer-line investigators and black-market fixers.",
                "- 卷末高潮：Expose the rewind traces at the observation point.",
                "- 主要登场角色：Shen Yan, bureau contact, fixer.",
                "- 关键伏笔（埋/收）：Repeated warning source and missing mother.",
                "- 前5章拆解：Hook, first benefit, rule reveal, backlash, mini climax.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_root / BODY_DIR_NAME).mkdir(parents=True, exist_ok=True)
    settings_dir = project_root / SETTINGS_DIR_NAME
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "世界观.md").write_text("# 世界观\nNight Rain City is monitored by anomaly inspectors.\n", encoding="utf-8")
    (settings_dir / "力量体系.md").write_text("# 力量体系\nRewind exacts a permanent memory cost.\n", encoding="utf-8")
    (settings_dir / "风格契约.md").write_text("# 风格契约\nKeep the tone tense and serial-friendly.\n", encoding="utf-8")
    return project_root


def make_service(project_root: Path, runner: MappingRunner | SequenceRunner) -> OrchestrationService:
    with patch("dashboard.orchestrator.get_client") as mock_get_client:
        mock_get_client.return_value.probe.return_value = {"configured": True}
        return OrchestrationService(project_root, runner=runner)


def long_content(title: str = "Chapter") -> str:
    return f"# {title}\n" + ("Rain archive memory cost " * 50)


def review_payload(score: float = 91.0) -> dict:
    return {
        "overall_score": score,
        "pass": True,
        "issues": [],
        "metrics": {"consistency": score},
        "summary": "ok",
    }


def test_plan_task_persists_outline_and_state(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = MappingRunner(
        {
            "plan": {
                "volume_plan": {"title": "Volume One", "summary": "The first five chapters establish the cost and first enemy line."},
                "chapters": [{"chapter": 1, "goal": "Set the hook"}, {"chapter": 2, "goal": "First rewind benefit"}],
            }
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("plan", {"volume": "1"})

    assert task["status"] == "completed"
    assert task["artifacts"]["plan_blocked"] is False
    outline_file = project_root / OUTLINE_DIR_NAME / "volume-01-plan.md"
    assert outline_file.is_file()
    outline_text = outline_file.read_text(encoding="utf-8")
    assert "Volume 1 Plan" in outline_text
    assert "Chapter 1" in outline_text
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["planning"]["latest_volume"] == "1"
    assert state["planning"]["volume_plans"]["1"]["outline_file"].endswith("volume-01-plan.md")
    plan_bundle = next(bundle for step_name, bundle in runner.prompt_bundles if step_name == "plan")
    assert plan_bundle["input"]["plan_health_check"]["ok"] is True


def test_plan_preflight_becomes_completed_but_blocked(tmp_path: Path):
    project_root = make_project(tmp_path)
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    state["planning"]["profile"]["volume_1_title"] = ""
    state["planning"]["profile"]["volume_1_conflict"] = ""
    (project_root / ".webnovel" / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    runner = MappingRunner({"plan": {"volume_plan": {"title": "unused"}, "chapters": []}})
    service = make_service(project_root, runner)

    task = service.run_task_sync("plan", {"volume": "1"})

    assert task["status"] == "completed"
    assert task["artifacts"]["plan_blocked"] is True
    assert task["artifacts"]["blocking_items"]
    assert runner.prompt_bundles == []
    assert not (project_root / OUTLINE_DIR_NAME / "volume-01-plan.md").exists()


def test_plan_blocked_payload_does_not_write_empty_volume_plan(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = MappingRunner(
        {
            "plan": {
                "volume_plan": {
                    "status": "BLOCKED",
                    "reason": "missing character stakes",
                    "blocking_items": [{"field": "major_characters_text", "label": "Major characters"}],
                }
            }
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("plan", {"volume": "1"})

    assert task["status"] == "completed"
    assert task["artifacts"]["plan_blocked"] is True
    assert not (project_root / OUTLINE_DIR_NAME / "volume-01-plan.md").exists()
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["planning"]["last_blocked"]["reason"] == "model_blocked"


def test_init_master_outline_contains_plan_ready_sections():
    outline = _build_master_outline(
        50,
        title="Night Rain Archive",
        genre="Urban Supernatural",
        protagonist_name="Shen Yan",
        golden_finger_name="Rewind 10 Minutes",
        core_selling_points="Costly rewind and anomaly investigation",
        protagonist_desire="Find the truth behind his mother's disappearance",
        protagonist_flaw="Relies too heavily on the power",
        factions="Bureau, fixer network",
        power_system_type="Urban anomalies",
        gf_irreversible_cost="Lose one memory permanently",
    )

    assert "## 故事前提" in outline
    assert "## 主线推进" in outline
    assert "能力代价" in outline
    assert "前5章拆解" in outline


def test_write_project_context_includes_context_payload_and_settings_snapshots(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Chapter 1")
    actual_word_count = len("".join(content.split()))
    chapter_file = f"{BODY_DIR_NAME}/ch0001.md"
    runner = MappingRunner(
        {
            "context": {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"},
            "draft": {"chapter_file": chapter_file, "content": content, "word_count": actual_word_count},
            "consistency-review": review_payload(),
            "continuity-review": review_payload(),
            "ooc-review": review_payload(),
            "polish": {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []},
            "data-sync": {
                "files_written": [chapter_file],
                "summary_file": ".webnovel/summaries/ch0001.md",
                "state_updated": True,
                "index_updated": True,
            },
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 1, "require_manual_approval": False})

    assert task["status"] == "completed"
    context_bundle = next(bundle for step_name, bundle in runner.prompt_bundles if step_name == "context")
    context_paths = [item["path"] for item in context_bundle["project_context"]]
    assert ".webnovel/context/ch0001.context.json" in context_paths
    assert f"{SETTINGS_DIR_NAME}/世界观.md" in context_paths
    checklist_scores = service.index_manager.get_recent_writing_checklist_scores(limit=1)
    assert checklist_scores
    assert checklist_scores[0]["chapter"] == 1


def test_write_data_sync_persists_chapter_index_and_canonical_word_count(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Chapter 1")
    actual_word_count = len("".join(content.split()))
    chapter_file = f"{BODY_DIR_NAME}/ch0001.md"
    runner = MappingRunner(
        {
            "context": {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"},
            "draft": {"chapter_file": chapter_file, "content": content, "word_count": actual_word_count},
            "consistency-review": review_payload(),
            "continuity-review": review_payload(),
            "ooc-review": review_payload(),
            "polish": {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []},
            "data-sync": {
                "files_written": [chapter_file],
                "summary_file": ".webnovel/summaries/ch0001.md",
                "state_updated": True,
                "index_updated": True,
                "chapter_meta": {"title": "Chapter 1", "location": "Night Rain City", "characters": ["Shen Yan"]},
            },
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 1, "require_manual_approval": False})

    assert task["status"] == "completed"
    chapter_record = service.index_manager.get_chapter(1)
    assert chapter_record is not None
    assert chapter_record["title"] == "Chapter 1"
    assert chapter_record["word_count"] == actual_word_count
    assert chapter_record["file_path"].endswith("ch0001.md")
    assert (project_root / BODY_DIR_NAME / "ch0001.md").is_file()
    assert (project_root / ".webnovel" / "summaries" / "ch0001.md").is_file()
    metrics = service.index_manager.get_recent_review_metrics(limit=1)[0]
    assert metrics["start_chapter"] == 1
    assert metrics["end_chapter"] == 1
    assert metrics["report_file"] == f"{REVIEW_REPORT_DIR_NAME}/第1-1章审查报告.md"
    assert (project_root / REVIEW_REPORT_DIR_NAME / "第1-1章审查报告.md").is_file()
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["review_checkpoints"][-1]["report"] == f"{REVIEW_REPORT_DIR_NAME}/第1-1章审查报告.md"


def test_write_data_sync_persists_structured_settings_into_state_and_index(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Chapter 2")
    actual_word_count = len("".join(content.split()))
    chapter_file = f"{BODY_DIR_NAME}/ch0002.md"
    runner = MappingRunner(
        {
            "context": {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"},
            "draft": {"chapter_file": chapter_file, "content": content, "word_count": actual_word_count},
            "consistency-review": review_payload(),
            "continuity-review": review_payload(),
            "ooc-review": review_payload(),
            "polish": {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []},
            "data-sync": {
                "files_written": [chapter_file],
                "summary_file": ".webnovel/summaries/ch0002.md",
                "state_updated": True,
                "index_updated": True,
                "organizations": [
                    {"name": "Rain Broker", "type": "organization", "summary": "A broker for anomaly information"},
                    {"name": "Investigation Bureau", "type": "organization", "summary": "Official anomaly unit"},
                ],
                "locations": [{"name": "Observation Point", "summary": "Critical shift handoff location"}],
                "world_rules": [{"name": "Temporary patrol window", "summary": "The inspection time moves ten minutes earlier in heavy rain"}],
                "chapter_meta": {"title": "Chapter 2", "location": "Night Rain City", "characters": ["Shen Yan"]},
            },
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 2, "require_manual_approval": False})

    assert task["status"] == "completed"
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    faction_names = {item["name"] for item in state["world_settings"]["factions"]}
    location_names = {item["name"] for item in state["world_settings"]["locations"]}
    rule_names = {item["name"] for item in state["world_settings"]["power_system"]}
    assert {"Rain Broker", "Investigation Bureau"} <= faction_names
    assert "Observation Point" in location_names
    assert "Temporary patrol window" in rule_names
    assert service.index_manager.get_entity("faction-rain-broker") is not None
    assert service.index_manager.get_entity("faction-investigation-bureau") is not None
    assert service.index_manager.get_entity("rule-temporary-patrol-window") is not None
    chapter_meta = state["chapter_meta"]["0002"]["structured_settings"]
    assert "Rain Broker" in chapter_meta["factions"]
    assert "Temporary patrol window" in chapter_meta["rules"]


def test_write_data_sync_enriches_minimal_payload_from_planning_profile(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Chapter 3")
    actual_word_count = len("".join(content.split()))
    chapter_file = f"{BODY_DIR_NAME}/ch0003.md"
    runner = MappingRunner(
        {
            "context": {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"},
            "draft": {"chapter_file": chapter_file, "content": content, "word_count": actual_word_count},
            "consistency-review": review_payload(),
            "continuity-review": review_payload(),
            "ooc-review": review_payload(),
            "polish": {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []},
            "data-sync": {
                "files_written": [chapter_file],
                "summary_file": ".webnovel/summaries/ch0003.md",
                "state_updated": True,
                "index_updated": True,
            },
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 3, "require_manual_approval": False})

    assert task["status"] == "completed"
    writeback = task["artifacts"]["writeback"]
    assert writeback["structured_sync"]["normalized_entries"] > 0
    assert service.index_manager.get_entity("faction-bureau") is not None
    assert service.index_manager.get_entity("rule-rewind-10-minutes") is not None
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    chapter_meta = state["chapter_meta"]["0003"]
    assert "Shen Yan" in chapter_meta["characters"]
    assert state["world_settings"]["factions"]
    assert state["world_settings"]["power_system"]


def test_write_data_sync_rejects_truncated_or_bogus_word_count(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = "too short " * 10
    runner = MappingRunner(
        {
            "context": {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"},
            "draft": {"chapter_file": f"{BODY_DIR_NAME}/ch0001.md", "content": content, "word_count": 9999},
            "consistency-review": review_payload(),
            "continuity-review": review_payload(),
            "ooc-review": review_payload(),
            "polish": {"chapter_file": f"{BODY_DIR_NAME}/ch0001.md", "content": content, "anti_ai_force_check": "pass", "change_summary": []},
            "data-sync": {
                "files_written": [],
                "summary_file": ".webnovel/summaries/ch0001.md",
                "state_updated": True,
                "index_updated": True,
            },
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 1, "require_manual_approval": False})

    assert task["status"] == "failed"
    assert task["error"]["code"] == "VALIDATION_ERROR"
    assert service.index_manager.get_chapter(1) is None
    assert not (project_root / BODY_DIR_NAME / "ch0001.md").exists()


def test_review_range_loads_real_chapters_and_persists_aggregate_metrics(tmp_path: Path):
    project_root = make_project(tmp_path)
    (project_root / BODY_DIR_NAME / "ch0001.md").write_text(long_content("Chapter 1"), encoding="utf-8")
    (project_root / BODY_DIR_NAME / "ch0002.md").write_text(long_content("Chapter 2"), encoding="utf-8")
    (project_root / ".webnovel" / "summaries" / "ch0001.md").write_text("# s1\n", encoding="utf-8")
    (project_root / ".webnovel" / "summaries" / "ch0002.md").write_text("# s2\n", encoding="utf-8")
    runner = MappingRunner(
        {
            "consistency-review": review_payload(90),
            "continuity-review": review_payload(92),
            "ooc-review": review_payload(93),
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("review", {"chapter_range": "1-2"})

    assert task["status"] == "completed"
    prompt_bundle = next(bundle for step_name, bundle in runner.prompt_bundles if step_name == "consistency-review")
    context_paths = [item["path"] for item in prompt_bundle["project_context"]]
    assert f"{BODY_DIR_NAME}/ch0001.md" in context_paths
    assert f"{BODY_DIR_NAME}/ch0002.md" in context_paths
    metrics = service.index_manager.get_recent_review_metrics(limit=1)[0]
    assert metrics["start_chapter"] == 1
    assert metrics["end_chapter"] == 2
    assert metrics["report_file"] == f"{REVIEW_REPORT_DIR_NAME}/第1-2章审查报告.md"
    assert (project_root / REVIEW_REPORT_DIR_NAME / "第1-2章审查报告.md").is_file()
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["review_checkpoints"][-1]["chapters"] == "1-2"
    assert state["review_checkpoints"][-1]["report"] == f"{REVIEW_REPORT_DIR_NAME}/第1-2章审查报告.md"


def test_resume_task_recovers_interrupted_write_from_data_sync(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Chapter 4")
    chapter_file = f"{BODY_DIR_NAME}/ch0004.md"
    runner = MappingRunner(
        {
            "data-sync": {
                "files_written": [chapter_file],
                "summary_file": ".webnovel/summaries/ch0004.md",
                "state_updated": True,
                "index_updated": True,
                "chapter_meta": {"title": "Chapter 4", "characters": ["Shen Yan"]},
            }
        }
    )
    service = make_service(project_root, runner)
    workflow = service._load_workflow("write")
    target = service.store.create_task("write", {"chapter": 4, "require_manual_approval": False}, workflow)
    target = service.store.update_task(
        target["id"],
        workflow_spec=workflow,
        status="interrupted",
        current_step="data-sync",
        approval_status="approved",
        artifacts={
            "step_results": {
                "polish": {"success": True, "structured_output": {"chapter_file": chapter_file, "content": content}},
            },
            "review_summary": {"overall_score": 92, "issues": [], "reviewers": []},
            "approval": {},
        },
    )

    resume_task = service.run_task_sync("resume", {"chapter": 4})
    resumed_target = service.get_task(target["id"])

    assert resume_task["status"] == "completed"
    assert resume_task["resume_target_task_id"] == target["id"]
    assert resumed_target["status"] == "completed"
    assert (project_root / BODY_DIR_NAME / "ch0004.md").is_file()
    assert (project_root / ".webnovel" / "summaries" / "ch0004.md").is_file()
    assert service.index_manager.get_chapter(4) is not None


def test_plan_auto_retries_once_for_missing_required_keys(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "plan": [
                step_result("plan", {"volume_plan": {"title": "Volume One"}}),
                step_result("plan", {"volume_plan": {"title": "Volume One"}, "chapters": [{"chapter": 1, "goal": "Open with a hook"}]}),
            ]
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("plan", {"volume": "1"})
    messages = [event["message"] for event in service.get_events(task["id"])]

    assert task["status"] == "completed"
    assert runner.calls == ["plan", "plan"]
    assert "step_auto_retried" in messages


def test_failed_write_does_not_persist_review_metrics_before_data_sync(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Failed pipeline")
    chapter_file = f"{BODY_DIR_NAME}/ch0001.md"
    runner = SequenceRunner(
        {
            "context": step_result("context", {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"}),
            "draft": step_result("draft", {"chapter_file": chapter_file, "content": content, "word_count": len("".join(content.split()))}),
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": step_result("continuity-review", review_payload()),
            "ooc-review": step_result("ooc-review", review_payload()),
            "polish": step_result("polish", {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []}),
            "data-sync": step_result("data-sync", {"error": "timeout"}, success=False),
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 1, "require_manual_approval": False})

    assert task["status"] == "failed"
    assert service.index_manager.get_chapter(1) is None
    assert service.index_manager.get_recent_review_metrics(limit=5) == []


def test_service_startup_marks_stale_running_tasks_interrupted(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = MappingRunner({"plan": {"volume_plan": {"title": "x"}, "chapters": []}})
    service = make_service(project_root, runner)
    workflow = {"name": "write", "version": 1, "steps": [{"name": "draft", "type": "codex"}]}
    task = service.store.create_task("write", {"chapter": 9}, workflow)
    service.store.mark_running(task["id"], "draft")

    restarted = make_service(project_root, runner)
    stale = restarted.get_task(task["id"])

    assert stale["status"] == "interrupted"
    assert stale["error"]["code"] == "TASK_INTERRUPTED"
