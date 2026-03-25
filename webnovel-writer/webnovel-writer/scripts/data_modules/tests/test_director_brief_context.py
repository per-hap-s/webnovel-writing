# -*- coding: utf-8 -*-

import json
import sys
from pathlib import Path

import pytest


TEST_ROOT = Path(__file__).resolve().parents[2]
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

from scripts.data_modules.config import DataModulesConfig
from scripts.data_modules.context_manager import ContextManager


@pytest.fixture
def temp_project(tmp_path):
    cfg = DataModulesConfig.from_project_root(tmp_path)
    cfg.ensure_dirs()
    (cfg.webnovel_dir / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "Director Context Test", "genre": "mystery"},
                "progress": {"current_chapter": 3, "total_words": 9000},
                "protagonist_state": {"name": "Shen Yan", "location": {"current": "Night Rain City"}},
                "chapter_meta": {},
                "disambiguation_warnings": [],
                "disambiguation_pending": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    director_dir = cfg.project_root / ".webnovel" / "director"
    director_dir.mkdir(parents=True, exist_ok=True)
    story_director_dir = cfg.project_root / ".webnovel" / "story-director"
    story_director_dir.mkdir(parents=True, exist_ok=True)
    (story_director_dir / "plan-ch0003.json").write_text(
        json.dumps(
            {
                "anchor_chapter": 3,
                "planning_horizon": 4,
                "priority_threads": ["warning source", "trust fracture"],
                "payoff_schedule": [{"thread": "rain warning", "target_chapter": 3, "mode": "major"}],
                "defer_schedule": [{"thread": "final mastermind", "not_before_chapter": 6, "reason": "too early"}],
                "risk_flags": ["Need to avoid another empty setup chapter."],
                "transition_notes": ["Chapter 3 should convert the warning clue into visible action."],
                "chapters": [
                    {
                        "chapter": 3,
                        "role": "current-execution",
                        "chapter_goal": "Turn the warning clue into visible action and cost.",
                        "must_advance_threads": ["warning source", "trust fracture"],
                        "optional_payoffs": ["rain warning"],
                        "forbidden_resolutions": ["Do not fully explain the source this chapter."],
                        "ending_hook_target": "Leave an actionable next-step clue at the end.",
                    },
                    {
                        "chapter": 4,
                        "role": "transition",
                        "chapter_goal": "Carry the warning clue into the next confrontation.",
                        "must_advance_threads": ["warning source", "trust fracture"],
                        "optional_payoffs": ["tower clue"],
                        "forbidden_resolutions": ["Do not reveal the mastermind in chapter 4."],
                        "ending_hook_target": "Force Shen Yan to choose a side at the end of chapter 4.",
                    }
                ],
                "rationale": "Keep the next few chapters focused on converting setup into movement.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (director_dir / "ch0003.json").write_text(
        json.dumps(
            {
                "chapter": 3,
                "chapter_goal": "Push the warning-source mystery forward.",
                "primary_conflict": "Shen Yan must investigate before losing more memory.",
                "must_advance_threads": ["warning source"],
                "payoff_targets": ["rain warning"],
                "setup_targets": ["observation tower clue"],
                "must_use_entities": ["Shen Yan", "Zhou Lan"],
                "relationship_moves": ["Shen Yan and Zhou Lan move from distrust to tactical cooperation."],
                "knowledge_reveals": ["warning source"],
                "forbidden_resolutions": ["Do not fully explain the source this chapter."],
                "ending_hook_target": "Leave an actionable next-step clue at the end.",
                "tempo": "steady escalation",
                "review_focus": ["Check that the chapter still centers the warning-source mystery."],
                "rationale": "Current chapter should bind the active mystery to visible action.",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return cfg


def test_context_manager_includes_director_brief_section(temp_project):
    manager = ContextManager(temp_project)
    payload = manager.build_context(3, use_snapshot=False, save_snapshot=False)

    assert "story_plan" in payload["sections"]
    story_plan = payload["sections"]["story_plan"]["content"]
    assert story_plan["anchor_chapter"] == 3
    assert story_plan["chapters"][0]["chapter_goal"] == "Turn the warning clue into visible action and cost."
    assert "director_brief" in payload["sections"]
    director_brief = payload["sections"]["director_brief"]["content"]
    assert director_brief["chapter"] == 3
    assert director_brief["chapter_goal"] == "Push the warning-source mystery forward."


def test_extract_chapter_context_payload_exposes_director_brief(temp_project):
    from extract_chapter_context import _render_text, build_chapter_context_payload

    payload = build_chapter_context_payload(temp_project.project_root, 3)

    assert payload["story_plan"]["anchor_chapter"] == 3
    assert payload["director_brief"]["chapter"] == 3
    rendered = _render_text(payload)
    assert "Story Plan" in rendered
    assert "Director Brief" in rendered
    assert "chapter_goal" in rendered


def test_extract_chapter_context_payload_reuses_covering_story_plan_for_followup_chapter(temp_project):
    from extract_chapter_context import build_chapter_context_payload

    payload = build_chapter_context_payload(temp_project.project_root, 4)

    assert payload["story_plan"]["anchor_chapter"] == 3
    assert any(item["chapter"] == 4 for item in payload["story_plan"]["chapters"])
    assert payload["story_plan"]["chapters"][1]["chapter_goal"] == "Carry the warning clue into the next confrontation."

