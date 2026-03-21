from __future__ import annotations

import asyncio
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
from scripts.data_modules.index_manager import ChapterMeta
from scripts.init_project import _build_master_outline, build_initial_planning_profile


def step_result(
    step_name: str,
    payload: dict,
    *,
    success: bool = True,
    stdout: str | None = None,
    error: dict | None = None,
    metadata: dict | None = None,
) -> StepResult:
    return StepResult(
        step_name=step_name,
        success=success,
        return_code=0 if success else 1,
        timing_ms=10,
        stdout=stdout if stdout is not None else json.dumps(payload, ensure_ascii=False),
        stderr="",
        structured_output=payload,
        prompt_file="prompt.md",
        output_file="output.json",
        error=None if success else (error or {"code": "STEP_FAILED", "message": "failed"}),
        metadata=metadata,
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
        self.prompt_bundles: list[tuple[str, dict]] = []

    def probe(self):
        return {"provider": "sequence-runner", "installed": True, "configured": True}

    def run(self, step_spec, workspace, prompt_bundle, progress_callback=None):
        step_name = step_spec["name"]
        self.calls.append(step_name)
        self.prompt_bundles.append((step_name, prompt_bundle))
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
    (project_root / ".webnovel" / "planning-profile.json").write_text(
        json.dumps(planning_profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
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


def review_payload(score: float = 91.0, *, issues: list[dict] | None = None, passed: bool = True) -> dict:
    return {
        "overall_score": score,
        "pass": passed,
        "issues": issues or [],
        "metrics": {"consistency": score},
        "summary": "ok",
    }


def test_bootstrap_profile_defaults_are_cold_start_ready():
    profile = build_initial_planning_profile(title="夜雨城回档人", genre="都市异能")

    assert profile["protagonist_name"]
    assert "请先" not in profile["protagonist_identity"]
    assert "请给" not in profile["protagonist_desire"]
    assert "请明确" not in profile["ability_cost"]
    assert "回档" in profile["core_setting"]
    assert "回档" in profile["story_logline"]


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
    assert plan_bundle["input"]["planning_profile_summary"]["volume_1"]["title"] == "First Rewind in the Rain"
    assert plan_bundle["input"]["planning_profile_summary"]["protagonist"]["name"] == "Shen Yan"


def test_plan_prompt_prefers_planning_profile_file(tmp_path: Path):
    project_root = make_project(tmp_path)
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    state["planning"]["profile"]["protagonist_name"] = "State Name"
    (project_root / ".webnovel" / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    file_profile = json.loads((project_root / ".webnovel" / "planning-profile.json").read_text(encoding="utf-8"))
    file_profile["protagonist_name"] = "File Name"
    (project_root / ".webnovel" / "planning-profile.json").write_text(
        json.dumps(file_profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    runner = MappingRunner(
        {
            "plan": {
                "volume_plan": {"title": "Volume One", "summary": "The first five chapters establish the cost and first enemy line."},
                "chapters": [{"chapter": 1, "goal": "Set the hook"}],
            }
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("plan", {"volume": "1"})

    assert task["status"] == "completed"
    plan_bundle = next(bundle for step_name, bundle in runner.prompt_bundles if step_name == "plan")
    assert plan_bundle["input"]["planning_profile_summary"]["protagonist"]["name"] == "File Name"
    planning_profile_doc = next(
        item for item in plan_bundle["project_context"] if item["path"] == ".webnovel/planning-profile.json"
    )
    assert "File Name" in planning_profile_doc["content"]


def test_plan_preflight_fails_with_plan_input_blocked(tmp_path: Path):
    project_root = make_project(tmp_path)
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    state["planning"]["profile"]["volume_1_title"] = ""
    state["planning"]["profile"]["volume_1_conflict"] = ""
    (project_root / ".webnovel" / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    file_profile = json.loads((project_root / ".webnovel" / "planning-profile.json").read_text(encoding="utf-8"))
    file_profile["volume_1_title"] = ""
    file_profile["volume_1_conflict"] = ""
    (project_root / ".webnovel" / "planning-profile.json").write_text(
        json.dumps(file_profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    runner = MappingRunner({"plan": {"volume_plan": {"title": "unused"}, "chapters": []}})
    service = make_service(project_root, runner)

    task = service.run_task_sync("plan", {"volume": "1"})

    assert task["status"] == "failed"
    assert task["error"]["code"] == "PLAN_INPUT_BLOCKED"
    assert task["error"]["details"]["blocking_items"]
    assert task["artifacts"]["plan_blocked"] is True
    assert task["artifacts"]["blocking_items"]
    assert runner.prompt_bundles == []
    assert not (project_root / OUTLINE_DIR_NAME / "volume-01-plan.md").exists()
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert "1" not in (state.get("planning", {}).get("volume_plans") or {})


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

    assert task["status"] == "failed"
    assert task["error"]["code"] == "PLAN_INPUT_BLOCKED"
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
    assert chapter_record["file_path"] == service._default_chapter_file(1)
    assert (project_root / service._default_chapter_file(1)).is_file()
    assert (project_root / ".webnovel" / "summaries" / "ch0001.md").is_file()
    metrics = service.index_manager.get_recent_review_metrics(limit=1)[0]
    assert metrics["start_chapter"] == 1
    assert metrics["end_chapter"] == 1
    assert metrics["report_file"] == f"{REVIEW_REPORT_DIR_NAME}/第1-1章审查报告.md"
    assert (project_root / REVIEW_REPORT_DIR_NAME / "第1-1章审查报告.md").is_file()
    state = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    assert state["review_checkpoints"][-1]["report"] == f"{REVIEW_REPORT_DIR_NAME}/第1-1章审查报告.md"


def test_write_data_sync_uses_requested_chapter_as_only_write_target(tmp_path: Path):
    project_root = make_project(tmp_path)
    bootstrap_service = make_service(project_root, MappingRunner({}))
    chapter_one_path = project_root / bootstrap_service._default_chapter_file(1)
    chapter_one_path.parent.mkdir(parents=True, exist_ok=True)
    chapter_one_path.write_text("chapter-one-original", encoding="utf-8")

    content = long_content("Chapter 2 canonical target")
    actual_word_count = len("".join(content.split()))
    wrong_chapter_file = bootstrap_service._default_chapter_file(1)
    wrong_summary_file = bootstrap_service._default_summary_file(1)
    runner = MappingRunner(
        {
            "context": {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"},
            "draft": {"chapter_file": wrong_chapter_file, "content": content, "word_count": actual_word_count},
            "consistency-review": review_payload(),
            "continuity-review": review_payload(),
            "ooc-review": review_payload(),
            "polish": {"chapter_file": wrong_chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []},
            "data-sync": {
                "files_written": [wrong_chapter_file],
                "summary_file": wrong_summary_file,
                "state_updated": True,
                "index_updated": True,
                "chapter_meta": {"title": "Chapter 2", "location": "Night Rain City", "characters": ["Shen Yan"]},
            },
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 2, "require_manual_approval": False})

    expected_chapter_path = project_root / service._default_chapter_file(2)
    expected_summary_path = project_root / service._default_summary_file(2)
    assert task["status"] == "completed"
    assert chapter_one_path.read_text(encoding="utf-8") == "chapter-one-original"
    assert expected_chapter_path.is_file()
    assert expected_summary_path.is_file()
    assert service.index_manager.get_chapter(2)["file_path"] == service._relative_project_path(expected_chapter_path)
    metrics = service.index_manager.get_recent_review_metrics(limit=5)
    assert any(item["start_chapter"] == 2 and item["end_chapter"] == 2 for item in metrics)
    messages = [event["message"] for event in service.get_events(task["id"])]
    assert "Write target normalized" in messages


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
    worldview_text = (project_root / SETTINGS_DIR_NAME / "世界观.md").read_text(encoding="utf-8")
    power_text = (project_root / SETTINGS_DIR_NAME / "力量体系.md").read_text(encoding="utf-8")
    assert "Rain Broker" in worldview_text
    assert "Temporary patrol window" in power_text


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


def test_write_data_sync_fails_when_chapter_index_is_missing_after_writeback(tmp_path: Path):
    project_root = make_project(tmp_path)
    bootstrap_service = make_service(project_root, MappingRunner({}))
    chapter_file = bootstrap_service._default_chapter_file(2)
    summary_file = bootstrap_service._default_summary_file(2)
    content = long_content("Chapter 2")
    runner = MappingRunner(
        {
            "context": {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"},
            "draft": {"chapter_file": chapter_file, "content": content, "word_count": len("".join(content.split()))},
            "consistency-review": review_payload(),
            "continuity-review": review_payload(),
            "ooc-review": review_payload(),
            "polish": {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []},
            "data-sync": {
                "files_written": [chapter_file],
                "summary_file": summary_file,
                "state_updated": True,
                "index_updated": True,
                "chapter_meta": {"title": "Chapter 2", "location": "Night Rain City", "characters": ["Shen Yan"]},
            },
        }
    )
    service = make_service(project_root, runner)
    service.index_manager.add_chapter = lambda chapter_meta: None

    task = service.run_task_sync("write", {"chapter": 2, "require_manual_approval": False})

    assert task["status"] == "failed"
    assert task["error"]["code"] == "WRITEBACK_CONSISTENCY_ERROR"


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
    assert (project_root / service._default_chapter_file(4)).is_file()
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


def test_write_context_auto_retries_once_and_compacts_context_payload_for_later_steps(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Chapter 1")
    chapter_file = f"{BODY_DIR_NAME}/ch0001.md"
    long_draft_prompt = "line\\n" * 900
    runner = SequenceRunner(
        {
            "context": [
                step_result(
                    "context",
                    {},
                    success=False,
                    stdout='{"task_brief": {"chapter": 1}',
                    error={
                        "code": "INVALID_STEP_OUTPUT",
                        "message": "步骤输出中不包含有效 JSON 对象。",
                        "attempt": 1,
                        "retryable": False,
                        "timeout_seconds": 150,
                        "parse_stage": "json_invalid",
                        "raw_output_present": True,
                    },
                    metadata={
                        "attempt": 1,
                        "retry_count": 0,
                        "timeout_seconds": 150,
                        "parse_stage": "json_invalid",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
                step_result(
                    "context",
                    {
                        "task_brief": {"chapter": 1, "goal": "Hook the opening accident"},
                        "contract_v2": {
                            "目标": "赶去街口救人",
                            "阻力": "暴雨与信息不足",
                            "代价": "可能暴露异常敏感",
                            "本章变化": "从守店转为主动行动",
                            "未闭合问题": "预警为何提前命中",
                            "核心冲突一句话": "他必须先行动再验证。",
                            "开头类型": "悬疑",
                            "情绪节奏": "低到高",
                            "信息密度": "medium",
                            "是否过渡章": False,
                            "额外长字段": "should be trimmed",
                        },
                        "draft_prompt": long_draft_prompt,
                    },
                    metadata={
                        "attempt": 2,
                        "retry_count": 1,
                        "timeout_seconds": 150,
                        "parse_stage": "strict_json",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
            ],
            "draft": step_result("draft", {"chapter_file": chapter_file, "content": content, "word_count": len("".join(content.split()))}),
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": step_result("continuity-review", review_payload()),
            "ooc-review": step_result("ooc-review", review_payload()),
            "polish": step_result("polish", {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []}),
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

    assert task["status"] == "completed"
    assert runner.calls[:2] == ["context", "context"]
    messages = [event["message"] for event in service.get_events(task["id"])]
    assert "step_auto_retried" in messages

    draft_bundle = next(bundle for step_name, bundle in runner.prompt_bundles if step_name == "draft")
    prior_context = draft_bundle["input"]["prior_step_results"]["context"]["structured_output"]
    assert prior_context["draft_prompt"] == "[stored separately in project context]"
    assert prior_context["draft_prompt_ref"] == ".webnovel/context/current-draft-prompt.txt"
    assert "draft_prompt_preview" in prior_context
    assert "额外长字段" not in prior_context["contract_v2"]

    context_paths = [item["path"] for item in draft_bundle["project_context"]]
    assert ".webnovel/context/current-draft-prompt.txt" in context_paths
    assert ".webnovel/context/current-context-package.json" in context_paths


def test_write_draft_auto_retries_once_after_invalid_json_output(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Chapter 1")
    chapter_file = f"{BODY_DIR_NAME}/ch0001.md"
    runner = SequenceRunner(
        {
            "context": step_result("context", {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"}),
            "draft": [
                step_result(
                    "draft",
                    {},
                    success=False,
                    stdout='{"chapter_file": "正文/当前请求章节正文.md"',
                    error={
                        "code": "INVALID_STEP_OUTPUT",
                        "message": "步骤输出中不包含有效 JSON 对象。",
                        "attempt": 1,
                        "retryable": False,
                        "timeout_seconds": 240,
                        "parse_stage": "json_invalid",
                        "raw_output_present": True,
                    },
                    metadata={
                        "attempt": 1,
                        "retry_count": 0,
                        "timeout_seconds": 240,
                        "parse_stage": "json_invalid",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
                step_result(
                    "draft",
                    {"chapter_file": chapter_file, "content": content, "word_count": len("".join(content.split()))},
                    metadata={
                        "attempt": 2,
                        "retry_count": 1,
                        "timeout_seconds": 240,
                        "parse_stage": "strict_json",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
            ],
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": step_result("continuity-review", review_payload()),
            "ooc-review": step_result("ooc-review", review_payload()),
            "polish": step_result("polish", {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []}),
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

    assert task["status"] == "completed"
    assert runner.calls[:3] == ["context", "draft", "draft"]
    messages = [event["message"] for event in service.get_events(task["id"])]
    assert "step_auto_retried" in messages


def test_review_continuity_auto_retries_once_after_invalid_output(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": [
                step_result(
                    "continuity-review",
                    {},
                    success=False,
                    stdout='{"overall_score": 90',
                    error={
                        "code": "INVALID_STEP_OUTPUT",
                        "message": "步骤输出中不包含有效 JSON 对象。",
                        "attempt": 1,
                        "retryable": False,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "raw_output_present": True,
                    },
                    metadata={
                        "attempt": 1,
                        "retry_count": 0,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
                step_result(
                    "continuity-review",
                    review_payload(),
                    metadata={
                        "attempt": 2,
                        "retry_count": 1,
                        "timeout_seconds": 150,
                        "parse_stage": "strict_json",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
            ],
            "ooc-review": step_result("ooc-review", review_payload()),
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("review", {"chapter_range": "1-3"})
    messages = [event["message"] for event in service.get_events(task["id"])]

    assert task["status"] == "completed"
    assert runner.calls == ["consistency-review", "continuity-review", "continuity-review", "ooc-review"]
    assert "step_auto_retried" in messages


def test_review_invalid_output_terminal_after_second_failure_reports_recoverability(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": [
                step_result(
                    "continuity-review",
                    {},
                    success=False,
                    stdout='{"overall_score": 90',
                    error={
                        "code": "INVALID_STEP_OUTPUT",
                        "message": "步骤输出中不包含有效 JSON 对象。",
                        "attempt": 1,
                        "retryable": False,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "raw_output_present": True,
                    },
                    metadata={
                        "attempt": 1,
                        "retry_count": 0,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
                step_result(
                    "continuity-review",
                    {},
                    success=False,
                    stdout='{"overall_score": 90',
                    error={
                        "code": "INVALID_STEP_OUTPUT",
                        "message": "步骤输出中不包含有效 JSON 对象。",
                        "attempt": 2,
                        "retryable": False,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "raw_output_present": True,
                    },
                    metadata={
                        "attempt": 2,
                        "retry_count": 1,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
            ],
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("review", {"chapter_range": "1-3"})
    task_with_runtime = service.get_task(task["id"])

    assert task["status"] == "failed"
    assert task["error"]["code"] == "INVALID_STEP_OUTPUT"
    assert task["error"]["details"]["recoverability"] == "terminal"
    assert task["error"]["details"]["suggested_resume_step"] == "continuity-review"
    assert task["error"]["details"]["parse_stage"] == "json_truncated"
    assert task_with_runtime["runtime_status"]["recoverability"] == "terminal"
    assert task_with_runtime["runtime_status"]["suggested_resume_step"] == "continuity-review"
    assert "当前解析阶段" in task_with_runtime["runtime_status"]["phase_detail"]


def test_write_data_sync_invalid_output_is_retriable_but_not_auto_retried(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Chapter 1")
    chapter_file = f"{BODY_DIR_NAME}/ch0001.md"
    runner = SequenceRunner(
        {
            "context": step_result("context", {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"}),
            "draft": step_result("draft", {"chapter_file": chapter_file, "content": content, "word_count": len("".join(content.split()))}),
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": step_result("continuity-review", review_payload()),
            "ooc-review": step_result("ooc-review", review_payload()),
            "polish": step_result("polish", {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []}),
            "data-sync": step_result(
                "data-sync",
                {},
                success=False,
                stdout='{"files_written": [',
                error={
                    "code": "INVALID_STEP_OUTPUT",
                    "message": "步骤输出中不包含有效 JSON 对象。",
                    "attempt": 1,
                    "retryable": False,
                    "timeout_seconds": 240,
                    "parse_stage": "json_invalid",
                    "raw_output_present": True,
                },
                metadata={
                    "attempt": 1,
                    "retry_count": 0,
                    "timeout_seconds": 240,
                    "parse_stage": "json_invalid",
                    "json_extraction_recovered": False,
                    "missing_required_keys": [],
                },
            ),
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("write", {"chapter": 1, "require_manual_approval": False})
    task_with_runtime = service.get_task(task["id"])
    messages = [event["message"] for event in service.get_events(task["id"])]

    assert task["status"] == "failed"
    assert runner.calls.count("data-sync") == 1
    assert "step_auto_retried" not in messages
    assert task["error"]["details"]["recoverability"] == "retriable"
    assert task["error"]["details"]["suggested_resume_step"] == "data-sync"
    assert task_with_runtime["runtime_status"]["recoverability"] == "retriable"
    assert "建议从写回同步重试" in task_with_runtime["runtime_status"]["phase_detail"]


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
    assert "可从当前步骤继续处理" in stale["error"]["message"]


def test_service_startup_auto_completes_stale_write_task_when_writeback_is_already_complete(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = make_service(project_root, MappingRunner({}))
    chapter = 2
    chapter_file = service._default_chapter_file(chapter)
    summary_file = service._default_summary_file(chapter)
    chapter_path = project_root / chapter_file
    summary_path = project_root / summary_file
    chapter_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    chapter_path.write_text("第2章正文\n", encoding="utf-8")
    summary_path.write_text("# 第2章摘要\n", encoding="utf-8")

    state_path = project_root / ".webnovel" / "state.json"
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    state_data["progress"]["current_chapter"] = 2
    state_data.setdefault("chapter_meta", {})["0002"] = {"title": "第二章"}
    state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")

    with service.index_manager._get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chapters (chapter, title, location, word_count, characters, summary, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (2, "第二章", "老城区", 3200, json.dumps(["沈言"], ensure_ascii=False), "摘要", chapter_file),
        )
        cursor.execute(
            """
            INSERT INTO review_metrics
            (start_chapter, end_chapter, overall_score, dimension_scores, severity_counts, critical_issues, report_file, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (2, 2, 90, json.dumps({"plot": 90}, ensure_ascii=False), json.dumps({}, ensure_ascii=False), json.dumps([], ensure_ascii=False), "review.md", "ok"),
        )
        conn.commit()

    workflow = {"name": "write", "version": 1, "steps": [{"name": "data-sync", "type": "internal"}]}
    task = service.store.create_task("write", {"chapter": 2}, workflow)
    service.store.update_task(task["id"], workflow_spec=workflow, approval_status="approved")
    service.store.mark_running(task["id"], "data-sync")

    restarted = make_service(project_root, MappingRunner({}))
    recovered = restarted.get_task(task["id"])
    events = restarted.get_events(task["id"])

    assert recovered["status"] == "completed"
    assert recovered["error"] is None
    assert any(event["message"] == "服务重启后检测到写回已完成，任务已自动收口" for event in events)


def test_service_startup_migrates_legacy_chapter_into_inferred_volume_without_using_current_volume(tmp_path: Path):
    project_root = make_project(tmp_path)
    state_path = project_root / ".webnovel" / "state.json"
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    state_data["progress"]["current_chapter"] = 120
    state_data["progress"]["current_volume"] = 3
    state_data["planning"]["latest_volume"] = "3"
    state_data["progress"]["volumes_planned"] = []
    state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")

    legacy_path = project_root / BODY_DIR_NAME / "第0001章.md"
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_path.write_text("legacy chapter\n", encoding="utf-8")

    restarted = make_service(project_root, MappingRunner({}))

    migrated_path = project_root / BODY_DIR_NAME / "第1卷" / "第0001章.md"
    wrong_path = project_root / BODY_DIR_NAME / "第3卷" / "第0001章.md"

    assert restarted._resolve_volume_for_chapter(1) == 1
    assert migrated_path.is_file()
    assert not legacy_path.exists()
    assert not wrong_path.exists()


def test_write_data_sync_rolls_back_partial_mutations_on_consistency_failure(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = make_service(project_root, MappingRunner({}))
    chapter = 1
    chapter_file = service._default_chapter_file(chapter)
    summary_file = service._default_summary_file(chapter)
    chapter_path = project_root / chapter_file
    summary_path = project_root / summary_file
    chapter_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    chapter_path.write_text("旧正文内容\n", encoding="utf-8")
    summary_path.write_text("# 旧摘要\n", encoding="utf-8")

    state_path = project_root / ".webnovel" / "state.json"
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    state_data["progress"] = {"current_chapter": 1, "total_words": 500}
    state_data["chapter_meta"] = {
        "0001": {"title": "旧标题", "location": "旧地点", "characters": ["旧角色"]}
    }
    state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")

    with service.index_manager._get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chapters (chapter, title, location, word_count, characters, summary, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (1, "旧标题", "旧地点", 500, json.dumps(["旧角色"], ensure_ascii=False), "旧摘要", chapter_file),
        )
        cursor.execute(
            """
            INSERT INTO review_metrics
            (start_chapter, end_chapter, overall_score, dimension_scores, severity_counts, critical_issues, report_file, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, 1, 80, json.dumps({"consistency": 80}, ensure_ascii=False), json.dumps({}, ensure_ascii=False), json.dumps([], ensure_ascii=False), "旧报告.md", "旧审查"),
        )
        cursor.execute(
            """
            INSERT INTO entities
            (id, type, canonical_name, tier, desc, current_json, first_appearance, last_appearance, is_protagonist, is_archived)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("shenyan", "角色", "沈言", "核心", "旧描述", json.dumps({"status": "old"}, ensure_ascii=False), 1, 1, 1, 0),
        )
        cursor.execute(
            "INSERT INTO aliases (alias, entity_id, entity_type) VALUES (?, ?, ?)",
            ("小沈", "shenyan", "角色"),
        )
        cursor.execute(
            """
            INSERT INTO relationships (from_entity, to_entity, type, description, chapter)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("shenyan", "bureau", "ally", "旧关系", 1),
        )
        conn.commit()

    content = long_content("Rollback Chapter")
    runner = SequenceRunner(
        {
            "context": step_result("context", {"task_brief": {}, "contract_v2": {}, "draft_prompt": "write"}),
            "draft": step_result("draft", {"chapter_file": chapter_file, "content": content, "word_count": len("".join(content.split()))}),
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": step_result("continuity-review", review_payload()),
            "ooc-review": step_result("ooc-review", review_payload()),
            "polish": step_result("polish", {"chapter_file": chapter_file, "content": content, "anti_ai_force_check": "pass", "change_summary": []}),
            "data-sync": step_result(
                "data-sync",
                {
                    "files_written": [chapter_file],
                    "summary_file": summary_file,
                    "state_updated": True,
                    "index_updated": True,
                    "chapter_meta": {"title": "新标题", "location": "新地点", "characters": ["沈言"]},
                    "entities_new": [{"id": "shenyan", "name": "沈言", "type": "角色", "aliases": ["小沈", "阿言"], "summary": "新描述"}],
                    "relationships_new": [{"from_entity": "shenyan", "to_entity": "bureau", "type": "ally", "description": "新关系"}],
                },
            ),
        }
    )
    service = make_service(project_root, runner)

    with patch.object(service, "_validate_writeback_consistency", side_effect=ValueError("force consistency failure")):
        task = service.run_task_sync("write", {"chapter": chapter, "require_manual_approval": False})

    assert task["status"] == "failed"
    assert chapter_path.read_text(encoding="utf-8") == "旧正文内容\n"
    assert summary_path.read_text(encoding="utf-8") == "# 旧摘要\n"

    rolled_back_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert rolled_back_state["progress"]["current_chapter"] == 1
    assert rolled_back_state["chapter_meta"]["0001"]["title"] == "旧标题"

    chapter_record = service.index_manager.get_chapter(1)
    assert chapter_record["title"] == "旧标题"
    assert chapter_record["file_path"] == chapter_file

    review_metrics = service.index_manager.get_recent_review_metrics(limit=5)
    assert any(record["report_file"] == "旧报告.md" for record in review_metrics)

    with service.index_manager._get_conn() as conn:
        cursor = conn.cursor()
        entity = cursor.execute("SELECT canonical_name, desc FROM entities WHERE id = ?", ("shenyan",)).fetchone()
        aliases = cursor.execute("SELECT alias FROM aliases WHERE entity_id = ? ORDER BY alias", ("shenyan",)).fetchall()
        relationship = cursor.execute(
            "SELECT description FROM relationships WHERE from_entity = ? AND to_entity = ? AND type = ?",
            ("shenyan", "bureau", "ally"),
        ).fetchone()

    assert entity["canonical_name"] == "沈言"
    assert entity["desc"] == "旧描述"
    assert [row["alias"] for row in aliases] == ["小沈"]
    assert relationship["description"] == "旧关系"

    event_messages = [event["message"] for event in service.get_events(task["id"])]
    assert "writeback_rollback_started" in event_messages
    assert "writeback_rollback_finished" in event_messages


def _seed_repair_target(service: OrchestrationService, project_root: Path, *, chapter: int = 1) -> tuple[str, str]:
    chapter_file = service._default_chapter_file(chapter)
    summary_file = service._default_summary_file(chapter)
    chapter_path = project_root / chapter_file
    summary_path = project_root / summary_file
    chapter_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    original_content = long_content("Original Chapter")
    chapter_path.write_text(original_content, encoding="utf-8")
    summary_path.write_text(f"# 第{chapter:04d}章摘要\n\n旧摘要。\n", encoding="utf-8")

    state_path = project_root / ".webnovel" / "state.json"
    state_data = json.loads(state_path.read_text(encoding="utf-8"))
    state_data.setdefault("progress", {})
    state_data["progress"]["current_chapter"] = chapter
    state_data["chapter_meta"] = {
        str(chapter): {"title": "Original Chapter", "location": "Archive", "characters": ["Shen Yan"]},
    }
    state_path.write_text(json.dumps(state_data, ensure_ascii=False, indent=2), encoding="utf-8")

    service.index_manager.add_chapter(
        ChapterMeta(
            chapter=chapter,
            title="Original Chapter",
            location="Archive",
            word_count=len("".join(original_content.split())),
            characters=["Shen Yan"],
            summary="旧摘要",
            file_path=chapter_file,
        )
    )
    return chapter_file, summary_file


def test_review_summary_exposes_repair_candidates_for_whitelist_issues(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = MappingRunner(
        {
            "consistency-review": review_payload(
                issues=[
                    {
                        "chapter": 1,
                        "type": "TRANSITION_CLARITY",
                        "title": "B1 到封存柜 47 的过渡不清",
                        "description": "补足从楼梯口到封存柜 47 的空间与动作过渡。",
                    },
                    {
                        "chapter": 1,
                        "type": "DIALOGUE_VOICE_DRIFT",
                        "title": "角色语气漂移",
                        "description": "角色说话风格偏离既有设定。",
                    },
                ]
            ),
            "continuity-review": review_payload(),
            "ooc-review": review_payload(),
        }
    )
    service = make_service(project_root, runner)

    task = service.run_task_sync("review", {"chapter": 1})

    assert task["status"] == "completed"
    summary = task["artifacts"]["review_summary"]
    assert summary["repairable_issue_count"] == 1
    eligible = next(item for item in summary["repair_candidates"] if item["issue_type"] == "TRANSITION_CLARITY")
    assert eligible["auto_rewrite_eligible"] is True
    assert eligible["operator_action"]["task_type"] == "repair"
    assert eligible["operator_action"]["payload"]["chapter"] == 1
    manual = next(item for item in summary["repair_candidates"] if item["issue_type"] == "DIALOGUE_VOICE_DRIFT")
    assert manual["auto_rewrite_eligible"] is False
    assert "白名单" in manual["reason"]


def test_repair_task_writes_backup_report_and_updated_chapter(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "repair-draft": step_result(
                "repair-draft",
                {
                    "chapter_file": f"{BODY_DIR_NAME}/第1卷/第0001章.md",
                    "content": long_content("Repaired Chapter"),
                    "word_count": len("".join(long_content("Repaired Chapter").split())),
                    "change_summary": ["补足空间转场", "明确预警来源"],
                },
            ),
            "consistency-review": step_result("consistency-review", review_payload(score=95.0)),
            "continuity-review": step_result("continuity-review", review_payload(score=94.0)),
        }
    )
    service = make_service(project_root, runner)
    chapter_file, summary_file = _seed_repair_target(service, project_root, chapter=1)

    task = service.run_task_sync(
        "repair",
        {
            "chapter": 1,
            "mode": "standard",
            "require_manual_approval": False,
            "options": {
                "source_task_id": "task-review-1",
                "issue_type": "TRANSITION_CLARITY",
                "issue_title": "B1 到封存柜 47 的过渡不清",
                "rewrite_goal": "补足空间与动作过渡，使读者可直接验证移动路径。",
                "guardrails": ["仅修复当前章节局部连续性问题", "不要改写卷纲或跨章主线"],
            },
        },
    )

    assert task["status"] == "completed"
    repair_artifact = task["artifacts"]["repair"]
    assert repair_artifact["issue_type"] == "TRANSITION_CLARITY"
    assert repair_artifact["report_file"].startswith(".webnovel/repair-reports/")
    assert repair_artifact["backup_paths"]["chapter"].startswith(".webnovel/repair-backups/")
    assert "Repaired Chapter" in (project_root / chapter_file).read_text(encoding="utf-8")
    assert (project_root / summary_file).is_file()
    assert (project_root / repair_artifact["report_file"]).is_file()
    assert (project_root / repair_artifact["backup_paths"]["chapter"]).is_file()

    state_data = json.loads((project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    chapter_meta = state_data["chapter_meta"]["1"]
    assert chapter_meta["last_repair_task_id"] == task["id"]
    assert "TRANSITION_CLARITY" in chapter_meta["last_repair_issue_types"]

    metrics = service.index_manager.get_recent_review_metrics(limit=5)
    assert any(item["report_file"] == repair_artifact["report_file"] for item in metrics)


def test_repair_task_waits_for_manual_approval_before_writeback(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "repair-draft": step_result(
                "repair-draft",
                {
                    "chapter_file": f"{BODY_DIR_NAME}/第1卷/第0001章.md",
                    "content": long_content("Approved Repair Chapter"),
                    "word_count": len("".join(long_content("Approved Repair Chapter").split())),
                    "change_summary": ["补足空间转场"],
                },
            ),
            "consistency-review": step_result("consistency-review", review_payload(score=95.0)),
            "continuity-review": step_result("continuity-review", review_payload(score=94.0)),
        }
    )
    service = make_service(project_root, runner)
    chapter_file, _ = _seed_repair_target(service, project_root, chapter=1)
    original_text = (project_root / chapter_file).read_text(encoding="utf-8")

    task = service.run_task_sync(
        "repair",
        {
            "chapter": 1,
            "mode": "standard",
            "require_manual_approval": True,
            "options": {
                "issue_type": "TRANSITION_CLARITY",
                "issue_title": "B1 到封存柜 47 的过渡不清",
                "rewrite_goal": "补足空间与动作过渡。",
            },
        },
    )

    assert task["status"] == "awaiting_writeback_approval"
    assert task["current_step"] == "approval-gate"
    assert task["approval_status"] == "pending"
    assert (project_root / chapter_file).read_text(encoding="utf-8") == original_text
    assert not (project_root / ".webnovel" / "repair-reports").exists()


def test_approved_repair_task_resumes_from_approval_gate_and_writes_back(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "repair-draft": step_result(
                "repair-draft",
                {
                    "chapter_file": f"{BODY_DIR_NAME}/第1卷/第0001章.md",
                    "content": long_content("Approved Repair Chapter"),
                    "word_count": len("".join(long_content("Approved Repair Chapter").split())),
                    "change_summary": ["补足空间转场"],
                },
            ),
            "consistency-review": step_result("consistency-review", review_payload(score=95.0)),
            "continuity-review": step_result("continuity-review", review_payload(score=94.0)),
        }
    )
    service = make_service(project_root, runner)
    chapter_file, summary_file = _seed_repair_target(service, project_root, chapter=1)

    task = service.run_task_sync(
        "repair",
        {
            "chapter": 1,
            "mode": "standard",
            "require_manual_approval": True,
            "options": {
                "issue_type": "TRANSITION_CLARITY",
                "issue_title": "B1 到封存柜 47 的过渡不清",
                "rewrite_goal": "补足空间与动作过渡。",
            },
        },
    )

    assert task["status"] == "awaiting_writeback_approval"

    approved = service.approve_writeback(task["id"], reason="manual approval")
    asyncio.run(service._run_task(task["id"], resume_from_step=approved.get("current_step") or "approval-gate"))
    completed = service.get_task(task["id"])

    assert completed["status"] == "completed"
    assert completed["approval_status"] == "approved"
    assert "Approved Repair Chapter" in (project_root / chapter_file).read_text(encoding="utf-8")
    assert (project_root / summary_file).is_file()
    assert (project_root / completed["artifacts"]["repair"]["report_file"]).is_file()


def test_rejected_repair_task_does_not_write_back_chapter(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "repair-draft": step_result(
                "repair-draft",
                {
                    "chapter_file": f"{BODY_DIR_NAME}/第1卷/第0001章.md",
                    "content": long_content("Rejected Repair Chapter"),
                    "word_count": len("".join(long_content("Rejected Repair Chapter").split())),
                    "change_summary": ["补足空间转场"],
                },
            ),
            "consistency-review": step_result("consistency-review", review_payload(score=95.0)),
            "continuity-review": step_result("continuity-review", review_payload(score=94.0)),
        }
    )
    service = make_service(project_root, runner)
    chapter_file, _ = _seed_repair_target(service, project_root, chapter=1)
    original_text = (project_root / chapter_file).read_text(encoding="utf-8")

    task = service.run_task_sync(
        "repair",
        {
            "chapter": 1,
            "mode": "standard",
            "require_manual_approval": True,
            "options": {
                "issue_type": "TRANSITION_CLARITY",
                "issue_title": "B1 到封存柜 47 的过渡不清",
                "rewrite_goal": "补足空间与动作过渡。",
            },
        },
    )

    rejected = service.reject_writeback(task["id"], reason="manual reject")

    assert rejected["status"] == "rejected"
    assert rejected["approval_status"] == "rejected"
    assert (project_root / chapter_file).read_text(encoding="utf-8") == original_text
    assert not (project_root / ".webnovel" / "repair-reports").exists()


def test_retry_repair_task_preserves_approved_state_for_repair_writeback(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = MappingRunner({})
    service = make_service(project_root, runner)
    workflow = service._load_workflow("repair")
    task = service.store.create_task(
        "repair",
        {"chapter": 1, "mode": "standard", "require_manual_approval": True},
        workflow,
    )
    service.store.update_task(
        task["id"],
        status="failed",
        approval_status="approved",
        current_step=None,
        artifacts={
            "approval": {"status": "approved"},
            "step_results": {
                "repair-plan": {"success": True, "structured_output": {"chapter": 1}},
                "review-summary": {"success": True, "structured_output": {"blocking": False}},
            },
        },
        error={"code": "INVALID_STEP_OUTPUT", "message": "failed"},
    )

    retried = service.retry_task(task["id"])
    events = service.get_events(task["id"])
    retry_event = next(event for event in reversed(events) if event["message"] == "Retry requested")

    assert retried["status"] == "retrying"
    assert retried["approval_status"] == "approved"
    assert retry_event["payload"]["resume_from_step"] == "repair-writeback"
    assert retry_event["payload"]["preserve_approval"] is True


def test_repair_task_blocks_writeback_when_review_summary_stays_blocking(tmp_path: Path):
    project_root = make_project(tmp_path)
    runner = SequenceRunner(
        {
            "repair-draft": step_result(
                "repair-draft",
                {
                    "chapter_file": f"{BODY_DIR_NAME}/第1卷/第0001章.md",
                    "content": long_content("Blocked Repair Chapter"),
                    "word_count": len("".join(long_content("Blocked Repair Chapter").split())),
                    "change_summary": ["尝试补足转场"],
                },
            ),
            "consistency-review": step_result(
                "consistency-review",
                review_payload(
                    score=72.0,
                    issues=[{"chapter": 1, "type": "TIMELINE_ISSUE", "severity": "critical", "title": "时间锚点仍然摇摆"}],
                    passed=False,
                ),
            ),
            "continuity-review": step_result("continuity-review", review_payload(score=80.0)),
        }
    )
    service = make_service(project_root, runner)
    chapter_file, _ = _seed_repair_target(service, project_root, chapter=1)
    original_text = (project_root / chapter_file).read_text(encoding="utf-8")

    task = service.run_task_sync(
        "repair",
        {
            "chapter": 1,
            "mode": "standard",
            "require_manual_approval": False,
            "options": {
                "issue_type": "TRANSITION_CLARITY",
                "issue_title": "B1 到封存柜 47 的过渡不清",
                "rewrite_goal": "补足空间与动作过渡。",
            },
        },
    )

    assert task["status"] == "failed"
    assert task["error"]["code"] == "REPAIR_REVIEW_BLOCKED"
    assert (project_root / chapter_file).read_text(encoding="utf-8") == original_text
    assert not (project_root / ".webnovel" / "repair-reports").exists()


def test_repair_draft_auto_retries_once_after_invalid_json_output(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Retried Repair Chapter")
    runner = SequenceRunner(
        {
            "repair-draft": [
                step_result(
                    "repair-draft",
                    {},
                    success=False,
                    stdout='{"chapter_file": "正文/第1卷/第0001章.md"',
                    error={
                        "code": "INVALID_STEP_OUTPUT",
                        "message": "步骤输出中不包含有效 JSON 对象。",
                        "attempt": 1,
                        "retryable": False,
                        "timeout_seconds": 120,
                        "parse_stage": "json_truncated",
                        "raw_output_present": True,
                    },
                    metadata={
                        "attempt": 1,
                        "retry_count": 0,
                        "timeout_seconds": 120,
                        "parse_stage": "json_truncated",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
                step_result(
                    "repair-draft",
                    {
                        "chapter_file": f"{BODY_DIR_NAME}/第1卷/第0001章.md",
                        "content": content,
                        "word_count": len("".join(content.split())),
                        "change_summary": ["补足空间转场"],
                    },
                    metadata={
                        "attempt": 2,
                        "retry_count": 1,
                        "timeout_seconds": 120,
                        "parse_stage": "strict_json",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
            ],
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": step_result("continuity-review", review_payload()),
        }
    )
    service = make_service(project_root, runner)
    _seed_repair_target(service, project_root, chapter=1)

    task = service.run_task_sync("repair", {"chapter": 1, "require_manual_approval": False, "options": {"issue_type": "TRANSITION_CLARITY", "rewrite_goal": "补足空间与动作过渡。"}})
    messages = [event["message"] for event in service.get_events(task["id"])]

    assert task["status"] == "completed"
    assert runner.calls[:2] == ["repair-draft", "repair-draft"]
    assert "step_auto_retried" in messages


def test_repair_continuity_review_auto_retries_once_after_invalid_output(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Retried Repair Review Chapter")
    runner = SequenceRunner(
        {
            "repair-draft": step_result(
                "repair-draft",
                {
                    "chapter_file": f"{BODY_DIR_NAME}/第1卷/第0001章.md",
                    "content": content,
                    "word_count": len("".join(content.split())),
                    "change_summary": ["补足空间转场"],
                },
            ),
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": [
                step_result(
                    "continuity-review",
                    {},
                    success=False,
                    stdout='{"overall_score": 91',
                    error={
                        "code": "INVALID_STEP_OUTPUT",
                        "message": "步骤输出中不包含有效 JSON 对象。",
                        "attempt": 1,
                        "retryable": False,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "raw_output_present": True,
                    },
                    metadata={
                        "attempt": 1,
                        "retry_count": 0,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
                step_result(
                    "continuity-review",
                    review_payload(),
                    metadata={
                        "attempt": 2,
                        "retry_count": 1,
                        "timeout_seconds": 150,
                        "parse_stage": "strict_json",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
            ],
        }
    )
    service = make_service(project_root, runner)
    _seed_repair_target(service, project_root, chapter=1)

    task = service.run_task_sync("repair", {"chapter": 1, "require_manual_approval": False, "options": {"issue_type": "TRANSITION_CLARITY", "rewrite_goal": "补足空间与动作过渡。"}})
    messages = [event["message"] for event in service.get_events(task["id"])]

    assert task["status"] == "completed"
    assert runner.calls == ["repair-draft", "consistency-review", "continuity-review", "continuity-review"]
    assert "step_auto_retried" in messages


def test_repair_invalid_output_terminal_after_second_failure_reports_recoverability(tmp_path: Path):
    project_root = make_project(tmp_path)
    content = long_content("Failed Repair Review Chapter")
    runner = SequenceRunner(
        {
            "repair-draft": step_result(
                "repair-draft",
                {
                    "chapter_file": f"{BODY_DIR_NAME}/第1卷/第0001章.md",
                    "content": content,
                    "word_count": len("".join(content.split())),
                    "change_summary": ["补足空间转场"],
                },
            ),
            "consistency-review": step_result("consistency-review", review_payload()),
            "continuity-review": [
                step_result(
                    "continuity-review",
                    {},
                    success=False,
                    stdout='{"overall_score": 91',
                    error={
                        "code": "INVALID_STEP_OUTPUT",
                        "message": "步骤输出中不包含有效 JSON 对象。",
                        "attempt": 1,
                        "retryable": False,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "raw_output_present": True,
                    },
                    metadata={
                        "attempt": 1,
                        "retry_count": 0,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
                step_result(
                    "continuity-review",
                    {},
                    success=False,
                    stdout='{"overall_score": 91',
                    error={
                        "code": "INVALID_STEP_OUTPUT",
                        "message": "步骤输出中不包含有效 JSON 对象。",
                        "attempt": 2,
                        "retryable": False,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "raw_output_present": True,
                    },
                    metadata={
                        "attempt": 2,
                        "retry_count": 1,
                        "timeout_seconds": 150,
                        "parse_stage": "json_truncated",
                        "json_extraction_recovered": False,
                        "missing_required_keys": [],
                    },
                ),
            ],
        }
    )
    service = make_service(project_root, runner)
    _seed_repair_target(service, project_root, chapter=1)

    task = service.run_task_sync("repair", {"chapter": 1, "require_manual_approval": False, "options": {"issue_type": "TRANSITION_CLARITY", "rewrite_goal": "补足空间与动作过渡。"}})
    task_with_runtime = service.get_task(task["id"])

    assert task["status"] == "failed"
    assert task["error"]["code"] == "INVALID_STEP_OUTPUT"
    assert task["error"]["details"]["recoverability"] == "terminal"
    assert task["error"]["details"]["suggested_resume_step"] == "continuity-review"
    assert task_with_runtime["runtime_status"]["recoverability"] == "terminal"
    assert task_with_runtime["runtime_status"]["suggested_resume_step"] == "continuity-review"
