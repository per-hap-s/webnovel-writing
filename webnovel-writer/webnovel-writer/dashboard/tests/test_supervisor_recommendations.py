from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from dashboard.orchestrator import OrchestrationService


def make_project(tmp_path: Path, *, current_chapter: int = 3) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    (webnovel_dir / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "Supervisor Test", "genre": "Urban Fantasy"},
                "progress": {"current_chapter": current_chapter, "total_words": 9000},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return project_root


def _store_task(service: OrchestrationService, task_type: str, request: dict, *, status: str = "completed", error: dict | None = None, artifacts: dict | None = None, updated_at: str | None = None) -> dict:
    task = service.store.create_task(task_type, request, {"name": task_type, "version": 1, "steps": []})
    updates = {"status": status}
    if error is not None:
        updates["error"] = error
    if artifacts is not None:
        updates["artifacts"] = artifacts
    if updated_at is not None:
        updates["updated_at"] = updated_at
    return service.store.update_task(task["id"], **updates)


def test_supervisor_recommendations_return_prioritized_actions(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    approval = _store_task(service, "write", {"chapter": 3, "mode": "standard", "require_manual_approval": True}, status="awaiting_writeback_approval", updated_at="2026-03-19T10:00:00+00:00")
    _store_task(service, "write", {"chapter": 4}, status="failed", error={"code": "REVIEW_GATE_BLOCKED", "message": "blocked"}, updated_at="2026-03-19T09:00:00+00:00")
    _store_task(
        service,
        "write",
        {"chapter": 5, "mode": "standard", "require_manual_approval": False},
        artifacts={"step_results": {}, "review_summary": None, "approval": {}, "writeback": {"story_refresh": {"should_refresh": True}}},
        updated_at="2026-03-19T08:00:00+00:00",
    )
    _store_task(
        service,
        "guarded-write",
        {"chapter": 5, "mode": "standard", "require_manual_approval": False},
        artifacts={
            "step_results": {},
            "review_summary": None,
            "approval": {},
            "guarded_runner": {
                "chapter": 5,
                "outcome": "completed_one_chapter",
                "next_action": {"can_enqueue_next": True, "next_chapter": 6},
            },
        },
        updated_at="2026-03-19T07:00:00+00:00",
    )

    items = service.list_supervisor_recommendations()

    assert [item["stableKey"] for item in items] == [
        f"approval:{approval['id']}",
        items[1]["stableKey"],
        items[2]["stableKey"],
        items[3]["stableKey"],
    ]
    assert items[0]["action"]["type"] == "open-task"
    assert items[0]["category"] == "approval"
    assert items[0]["categoryLabel"] == "审批"
    assert any(item["action"]["type"] == "retry-story" for item in items)
    assert any(item["category"] == "story_refresh" for item in items)
    assert any(item["action"]["taskType"] == "guarded-write" for item in items if item["action"]["type"] == "create-task")


def test_supervisor_recommendations_dedupe_story_refresh_by_chapter(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    older = _store_task(
        service,
        "write",
        {"chapter": 6},
        artifacts={"step_results": {}, "review_summary": None, "approval": {}, "writeback": {"story_refresh": {"should_refresh": True}}},
        updated_at="2026-03-19T08:00:00+00:00",
    )
    newer = _store_task(
        service,
        "write",
        {"chapter": 6},
        artifacts={"step_results": {}, "review_summary": None, "approval": {}, "writeback": {"story_refresh": {"should_refresh": True}}},
        updated_at="2026-03-19T09:00:00+00:00",
    )

    items = service.list_supervisor_recommendations()
    refresh_items = [item for item in items if item["stableKey"] == "refresh:chapter:6"]

    assert len(refresh_items) == 1
    assert refresh_items[0]["sourceTaskId"] == newer["id"]
    assert refresh_items[0]["sourceTaskId"] != older["id"]


def test_supervisor_dismissal_filters_items_until_fingerprint_changes(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    approval = _store_task(
        service,
        "write",
        {"chapter": 3, "mode": "standard", "require_manual_approval": True},
        status="awaiting_writeback_approval",
        updated_at="2026-03-19T10:00:00+00:00",
    )

    items = service.list_supervisor_recommendations()
    assert len(items) == 1
    item = items[0]

    dismiss_result = service.dismiss_supervisor_recommendation(
        item["stableKey"],
        item["fingerprint"],
        reason="defer",
        note="等本轮写作任务收尾后再看",
    )
    assert dismiss_result["dismissed"] is True
    assert dismiss_result["dismissalReason"] == "defer"
    assert dismiss_result["dismissalNote"] == "等本轮写作任务收尾后再看"

    assert service.list_supervisor_recommendations() == []

    all_items = service.list_supervisor_recommendations(include_dismissed=True)
    assert len(all_items) == 1
    assert all_items[0]["dismissed"] is True
    assert all_items[0]["dismissedAt"]
    assert all_items[0]["dismissalReason"] == "defer"
    assert all_items[0]["dismissalNote"] == "等本轮写作任务收尾后再看"

    service.store.update_task(approval["id"], approval_status="pending")

    visible_again = service.list_supervisor_recommendations()
    assert len(visible_again) == 1
    assert visible_again[0]["stableKey"] == item["stableKey"]
    assert visible_again[0]["fingerprint"] != item["fingerprint"]
    assert visible_again[0]["dismissed"] is False


def test_supervisor_undismiss_removes_persisted_state(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    _store_task(
        service,
        "write",
        {"chapter": 3, "mode": "standard", "require_manual_approval": True},
        status="awaiting_writeback_approval",
        updated_at="2026-03-19T10:00:00+00:00",
    )

    item = service.list_supervisor_recommendations()[0]
    service.dismiss_supervisor_recommendation(item["stableKey"], item["fingerprint"], reason="waiting_info", note="等更多上下文")

    state_path = project_root / ".webnovel" / "supervisor" / "state.json"
    assert state_path.exists()

    result = service.undismiss_supervisor_recommendation(item["stableKey"])
    assert result == {"stableKey": item["stableKey"], "dismissed": False}
    assert service.list_supervisor_recommendations()[0]["stableKey"] == item["stableKey"]

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["dismissals"] == {}


def test_supervisor_batch_dismiss_and_undismiss(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    first = _store_task(
        service,
        "write",
        {"chapter": 3, "mode": "standard", "require_manual_approval": True},
        status="awaiting_writeback_approval",
        updated_at="2026-03-19T10:00:00+00:00",
    )
    second = _store_task(
        service,
        "write",
        {"chapter": 4},
        status="failed",
        error={"code": "REVIEW_GATE_BLOCKED", "message": "blocked"},
        updated_at="2026-03-19T09:00:00+00:00",
    )

    items = service.list_supervisor_recommendations(include_dismissed=True)
    targets = [
        {"stable_key": item["stableKey"], "fingerprint": item["fingerprint"]}
        for item in items
        if item["sourceTaskId"] in {first["id"], second["id"]}
    ]

    dismiss_result = service.dismiss_supervisor_recommendations_batch(targets, reason="batch_later", note="统一稍后处理")
    assert dismiss_result["count"] == 2
    assert len(service.list_supervisor_recommendations()) == 0

    undismiss_result = service.undismiss_supervisor_recommendations_batch([item["stable_key"] for item in targets])
    assert undismiss_result["count"] == 2
    assert len(service.list_supervisor_recommendations()) == 2


def test_supervisor_tracking_status_persists_and_can_clear(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    _store_task(
        service,
        "write",
        {"chapter": 3, "mode": "standard", "require_manual_approval": True},
        status="awaiting_writeback_approval",
        updated_at="2026-03-19T10:00:00+00:00",
    )

    item = service.list_supervisor_recommendations()[0]
    result = service.set_supervisor_recommendation_tracking(item["stableKey"], item["fingerprint"], status="in_progress", note="等待主线审批")

    assert result["trackingStatus"] == "in_progress"
    assert result["trackingLabel"]
    tracked = service.list_supervisor_recommendations(include_dismissed=True)[0]
    assert tracked["trackingStatus"] == "in_progress"
    assert tracked["trackingNote"] == "等待主线审批"
    assert tracked["trackingUpdatedAt"]

    cleared = service.clear_supervisor_recommendation_tracking(item["stableKey"])
    assert cleared["trackingStatus"] == ""
    assert service.list_supervisor_recommendations(include_dismissed=True)[0]["trackingStatus"] == ""

    state_path = project_root / ".webnovel" / "supervisor" / "state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["tracking"] == {}


def test_supervisor_tracking_state_expires_when_fingerprint_changes(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    approval = _store_task(
        service,
        "write",
        {"chapter": 3, "mode": "standard", "require_manual_approval": True},
        status="awaiting_writeback_approval",
        updated_at="2026-03-19T10:00:00+00:00",
    )

    item = service.list_supervisor_recommendations()[0]
    service.set_supervisor_recommendation_tracking(item["stableKey"], item["fingerprint"], status="completed", note="已人工处理")

    service.store.update_task(approval["id"], approval_status="pending")
    visible_again = service.list_supervisor_recommendations(include_dismissed=True)
    assert visible_again[0]["trackingStatus"] == ""

    state_path = project_root / ".webnovel" / "supervisor" / "state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["tracking"] == {}


def test_supervisor_tracking_supports_task_and_checklist_links(tmp_path: Path):
    project_root = make_project(tmp_path)
    service = OrchestrationService(project_root)

    _store_task(
        service,
        "write",
        {"chapter": 3, "mode": "standard", "require_manual_approval": True},
        status="awaiting_writeback_approval",
        updated_at="2026-03-19T10:00:00+00:00",
    )

    item = service.list_supervisor_recommendations()[0]
    result = service.set_supervisor_recommendation_tracking(
        item["stableKey"],
        item["fingerprint"],
        status="completed",
        note="linked-proof",
        linked_task_id="task-approval-1",
        linked_checklist_path=".webnovel/supervisor/checklists/checklist-ch0003-20260319-100000.md",
    )

    assert result["linkedTaskId"] == "task-approval-1"
    assert result["linkedChecklistPath"] == ".webnovel/supervisor/checklists/checklist-ch0003-20260319-100000.md"

    tracked = service.list_supervisor_recommendations(include_dismissed=True)[0]
    assert tracked["linkedTaskId"] == "task-approval-1"
    assert tracked["linkedChecklistPath"] == ".webnovel/supervisor/checklists/checklist-ch0003-20260319-100000.md"


def test_supervisor_checklist_save_persists_markdown_artifact(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=6)
    service = OrchestrationService(project_root)

    result = service.save_supervisor_checklist(
        "# Supervisor Checklist\n\n- item",
        chapter=6,
        selected_keys=["approval:task-1", "review:task-2"],
        category_filter="approval",
        sort_mode="priority",
        title="第6章开写前清单",
        note="本轮先处理审批和刷新建议",
    )

    saved_path = project_root / result["relativePath"]
    assert result["chapter"] == 6
    assert result["selectedCount"] == 2
    assert result["title"] == "第6章开写前清单"
    assert result["note"] == "本轮先处理审批和刷新建议"
    assert saved_path.exists()
    content = saved_path.read_text(encoding="utf-8")
    assert "saved_at:" in content
    assert "chapter: 6" in content
    assert "category_filter: approval" in content
    assert "sort_mode: priority" in content
    assert 'title: "第6章开写前清单"' in content
    assert 'note: "本轮先处理审批和刷新建议"' in content
    assert '  - "approval:task-1"' in content
    assert "# Supervisor Checklist" in content


def test_supervisor_checklist_save_uses_unique_paths_within_same_second(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=6)
    service = OrchestrationService(project_root)

    first_saved_at = datetime(2026, 3, 19, 10, 10, 0, 123456, tzinfo=timezone.utc)
    second_saved_at = datetime(2026, 3, 19, 10, 10, 0, 654321, tzinfo=timezone.utc)
    with patch("dashboard.orchestrator.datetime") as mocked_datetime:
        mocked_datetime.now.side_effect = [first_saved_at, second_saved_at]
        first = service.save_supervisor_checklist("# Checklist A", chapter=6)
        second = service.save_supervisor_checklist("# Checklist B", chapter=6)

    assert first["relativePath"] != second["relativePath"]
    assert (project_root / first["relativePath"]).read_text(encoding="utf-8").strip().endswith("# Checklist A")
    assert (project_root / second["relativePath"]).read_text(encoding="utf-8").strip().endswith("# Checklist B")


def test_supervisor_checklist_list_returns_recent_saved_items(tmp_path: Path):
    project_root = make_project(tmp_path, current_chapter=6)
    service = OrchestrationService(project_root)

    service.save_supervisor_checklist(
        "# Checklist A\n\n- first item",
        chapter=5,
        selected_keys=["approval:task-1"],
        category_filter="approval",
        sort_mode="priority",
        title="第一轮清单",
        note="优先处理审批",
    )
    service.save_supervisor_checklist(
        "# Checklist B\n\n- second item",
        chapter=6,
        selected_keys=["review:task-2", "refresh:chapter:6"],
        category_filter="all",
        sort_mode="updated_desc",
        title="第二轮清单",
        note="切换到刷新评估",
    )

    items = service.list_supervisor_checklists(limit=5)

    assert len(items) == 2
    assert items[0]["content"].startswith("# Checklist")
    assert items[0]["relativePath"].startswith(".webnovel/supervisor/checklists/")
    assert items[0]["summary"]
    assert isinstance(items[0]["selectedKeys"], list)
    assert items[0]["savedAt"]
    assert items[0]["title"]
    assert "note" in items[0]
