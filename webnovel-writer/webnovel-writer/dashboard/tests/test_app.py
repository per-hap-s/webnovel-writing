from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.orchestrator import OrchestrationService


@pytest.fixture
def mock_project_root(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    (webnovel_dir / "state.json").write_text(
        json.dumps(
            {
                "project_info": {"title": "Test Novel", "genre": "Urban Fantasy"},
                "progress": {"current_chapter": 1, "total_words": 1000},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    conn = sqlite3.connect(str(webnovel_dir / "index.db"))
    conn.execute("CREATE TABLE entities (id TEXT PRIMARY KEY, canonical_name TEXT, type TEXT, is_archived INTEGER DEFAULT 0, last_appearance INTEGER)")
    conn.execute("CREATE TABLE relationships (id INTEGER PRIMARY KEY AUTOINCREMENT, from_entity TEXT, to_entity TEXT, type TEXT, chapter INTEGER)")
    conn.execute("CREATE TABLE chapters (chapter INTEGER PRIMARY KEY, title TEXT, word_count INTEGER)")
    conn.execute("CREATE TABLE scenes (id INTEGER PRIMARY KEY AUTOINCREMENT, chapter INTEGER, scene_index INTEGER, content TEXT)")
    conn.commit()
    conn.close()
    return project_root


@pytest.fixture
def mock_orchestrator() -> MagicMock:
    orchestrator = MagicMock(spec=OrchestrationService)
    orchestrator.probe_llm.return_value = {
        "provider": "openai-compatible",
        "installed": True,
        "configured": True,
        "connection_status": "connected",
        "connection_checked_at": "2026-03-14T00:00:00Z",
        "connection_error": None,
    }
    orchestrator.probe_rag.return_value = {
        "provider": "siliconflow",
        "configured": True,
        "base_url": "https://api.siliconflow.cn/v1",
        "embed_model": "BAAI/bge-m3",
        "rerank_model": "BAAI/bge-reranker-v2-m3",
        "retry_policy": {"max_retries": 6, "initial_delay_ms": 500, "max_delay_ms": 8000},
        "last_error": None,
        "last_error_at": None,
        "connection_status": "connected",
        "connection_checked_at": "2026-03-14T00:00:00Z",
        "connection_error": None,
    }
    orchestrator.list_tasks.return_value = []
    orchestrator.list_supervisor_recommendations.return_value = []
    return orchestrator


@pytest.fixture
def client(mock_project_root: Path, mock_orchestrator: MagicMock) -> TestClient:
    with patch("dashboard.app.OrchestrationService", return_value=mock_orchestrator):
        app = create_app(project_root=mock_project_root)
        app.state.orchestrator = mock_orchestrator
        with TestClient(app) as test_client:
            yield test_client


def _create_workbench_client(workspace_root: Path, mock_orchestrator: MagicMock, app_home: Path) -> TestClient:
    env_patch = patch.dict("os.environ", {"WEBNOVEL_HOME": str(app_home)}, clear=False)
    env_patch.start()
    try:
        with patch("dashboard.app.OrchestrationService", return_value=mock_orchestrator):
            app = create_app(workspace_root=workspace_root)
            app.state.orchestrator = mock_orchestrator
            client = TestClient(app)
            client.__enter__()
            client._webnovel_env_patch = env_patch
            return client
    except Exception:
        env_patch.stop()
        raise


def _close_workbench_client(test_client: TestClient) -> None:
    env_patch = getattr(test_client, "_webnovel_env_patch", None)
    try:
        test_client.__exit__(None, None, None)
    finally:
        if env_patch is not None:
            env_patch.stop()


def _seed_narrative_tables(project_root: Path) -> None:
    conn = sqlite3.connect(str(project_root / ".webnovel" / "index.db"))
    conn.execute(
        """
        CREATE TABLE foreshadowing_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            entity_id TEXT,
            introduced_chapter INTEGER,
            payoff_chapter INTEGER,
            status TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT,
            chapter INTEGER,
            summary TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE character_arcs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT,
            chapter INTEGER,
            arc_stage TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE knowledge_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT,
            chapter INTEGER,
            fact TEXT,
            state TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO foreshadowing_items (name, entity_id, introduced_chapter, payoff_chapter, status) VALUES (?, ?, ?, ?, ?)",
        [
            ("setup-1", "hero", 1, None, "open"),
            ("setup-2", "hero", 2, None, "open"),
            ("setup-3", "ally", 3, None, "open"),
        ],
    )
    conn.executemany(
        "INSERT INTO timeline_events (entity_id, chapter, summary) VALUES (?, ?, ?)",
        [
            ("hero", 2, "timeline hero chapter 2"),
            ("ally", 2, "timeline ally chapter 2"),
            ("hero", 3, "timeline hero chapter 3"),
        ],
    )
    conn.executemany(
        "INSERT INTO character_arcs (entity_id, chapter, arc_stage) VALUES (?, ?, ?)",
        [
            ("hero", 1, "hesitant"),
            ("hero", 2, "committed"),
            ("ally", 2, "watching"),
        ],
    )
    conn.executemany(
        "INSERT INTO knowledge_states (entity_id, chapter, fact, state) VALUES (?, ?, ?, ?)",
        [
            ("hero", 1, "secret-a", "suspects"),
            ("hero", 2, "secret-b", "confirmed"),
            ("ally", 2, "secret-a", "unknown"),
        ],
    )
    conn.commit()
    conn.close()


def test_llm_status_success(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.probe_llm.return_value = {
        "provider": "openai-compatible",
        "mode": "api",
        "model": "gpt-test",
        "configured": True,
        "probe_status": "failed",
        "effective_status": "degraded",
        "status_source": "recent_task_success",
        "last_successful_request_at": "2026-03-17T00:00:00Z",
        "last_successful_task_type": "write",
        "last_probe_error": {"code": "PROBE_HTTP_ERROR"},
        "connection_status": "degraded",
    }
    response = client.get("/api/llm/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openai-compatible"
    assert data["probe_status"] == "failed"
    assert data["effective_status"] == "degraded"
    assert data["status_source"] == "recent_task_success"
    assert data["last_successful_request_at"] == "2026-03-17T00:00:00Z"
    assert data["last_successful_task_type"] == "write"
    mock_orchestrator.probe_llm.assert_called_once()


def test_rag_status_success(client: TestClient, mock_orchestrator: MagicMock):
    response = client.get("/api/rag/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "siliconflow"
    assert data["embed_model"] == "BAAI/bge-m3"
    assert data["retry_policy"]["max_retries"] == 6
    mock_orchestrator.probe_rag.assert_called_once()


def test_cancel_task_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.cancel_task.return_value = {
        "id": "task-1",
        "status": "interrupted",
        "error": {"code": "TASK_CANCELLED", "message": "由仪表盘手动停止任务"},
    }

    response = client.post("/api/tasks/task-1/cancel", json={"reason": "由仪表盘手动停止任务"})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "interrupted"
    assert data["error"]["code"] == "TASK_CANCELLED"
    mock_orchestrator.cancel_task.assert_called_once_with("task-1", reason="由仪表盘手动停止任务")


def test_retry_task_accepts_resume_from_step(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.retry_task.return_value = {"id": "task-1", "status": "retrying"}

    response = client.post("/api/tasks/task-1/retry", json={"resume_from_step": "story-director"})

    assert response.status_code == 200
    assert response.json()["status"] == "retrying"
    mock_orchestrator.retry_task.assert_called_once_with("task-1", resume_from_step="story-director")


def test_task_summary_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.list_task_summaries.return_value = [{"id": "task-1", "status": "retrying"}]

    response = client.get("/api/tasks/summary?limit=10")

    assert response.status_code == 200
    assert response.json() == [{"id": "task-1", "status": "retrying"}]
    mock_orchestrator.list_task_summaries.assert_called_once_with(limit=10)


def test_task_detail_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.get_task_detail.return_value = {
        "task": {"id": "task-1", "status": "resuming_writeback"},
        "events": [{"id": "evt-1", "message": "Writeback approved"}],
    }

    response = client.get("/api/tasks/task-1/detail?event_limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task"]["status"] == "resuming_writeback"
    assert payload["events"][0]["message"] == "Writeback approved"
    mock_orchestrator.get_task_detail.assert_called_once_with("task-1", event_limit=20)


def test_review_approve_calls_orchestrator_and_returns_resuming_status(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.approve_writeback.return_value = {"id": "task-1", "status": "resuming_writeback"}

    response = client.post("/api/review/approve", json={"task_id": "task-1", "reason": "批准继续回写"})

    assert response.status_code == 200
    assert response.json()["status"] == "resuming_writeback"
    mock_orchestrator.approve_writeback.assert_called_once_with("task-1", "批准继续回写")


def test_create_resume_task_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock, mock_project_root: Path):
    mock_orchestrator.create_task.return_value = {"id": "task-resume-1", "status": "queued", "task_type": "resume"}

    response = client.post("/api/tasks/resume", json={"mode": "standard"})

    assert response.status_code == 200
    assert response.json()["task_type"] == "resume"
    mock_orchestrator.create_task.assert_called_once_with(
        "resume",
        {
            "project_root": str(mock_project_root),
            "chapter": None,
            "start_chapter": None,
            "max_chapters": None,
            "chapter_range": None,
            "volume": None,
            "mode": "standard",
            "require_manual_approval": False,
            "options": {},
        },
    )


def test_create_repair_task_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock, mock_project_root: Path):
    mock_orchestrator.create_task.return_value = {"id": "task-repair-1", "status": "queued", "task_type": "repair"}

    response = client.post(
        "/api/tasks/repair",
        json={
            "chapter": 2,
            "mode": "standard",
            "require_manual_approval": False,
            "options": {
                "source_task_id": "task-review-1",
                "issue_type": "TRANSITION_CLARITY",
                "issue_title": "B1 到封存柜 47 的过渡不清",
                "rewrite_goal": "补足空间与动作过渡。",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["task_type"] == "repair"
    mock_orchestrator.create_task.assert_called_once_with(
        "repair",
        {
            "project_root": str(mock_project_root),
            "chapter": 2,
            "start_chapter": None,
            "max_chapters": None,
            "chapter_range": None,
            "volume": None,
            "mode": "standard",
            "require_manual_approval": False,
            "options": {
                "source_task_id": "task-review-1",
                "issue_type": "TRANSITION_CLARITY",
                "issue_title": "B1 到封存柜 47 的过渡不清",
                "rewrite_goal": "补足空间与动作过渡。",
            },
        },
    )


def test_create_guarded_write_task_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock, mock_project_root: Path):
    mock_orchestrator.create_task.return_value = {"id": "task-guarded-1", "status": "queued", "task_type": "guarded-write"}

    response = client.post("/api/tasks/guarded-write", json={"chapter": 2, "mode": "standard", "require_manual_approval": False})

    assert response.status_code == 200
    assert response.json()["task_type"] == "guarded-write"
    mock_orchestrator.create_task.assert_called_once_with(
        "guarded-write",
        {
            "project_root": str(mock_project_root),
            "chapter": 2,
            "start_chapter": None,
            "max_chapters": None,
            "chapter_range": None,
            "volume": None,
            "mode": "standard",
            "require_manual_approval": False,
            "options": {},
        },
    )


def test_create_guarded_batch_write_task_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock, mock_project_root: Path):
    mock_orchestrator.create_task.return_value = {"id": "task-guarded-batch-1", "status": "queued", "task_type": "guarded-batch-write"}

    response = client.post(
        "/api/tasks/guarded-batch-write",
        json={"start_chapter": 2, "max_chapters": 3, "mode": "standard", "require_manual_approval": False},
    )

    assert response.status_code == 200
    assert response.json()["task_type"] == "guarded-batch-write"
    mock_orchestrator.create_task.assert_called_once_with(
        "guarded-batch-write",
        {
            "project_root": str(mock_project_root),
            "chapter": None,
            "start_chapter": 2,
            "max_chapters": 3,
            "chapter_range": None,
            "volume": None,
            "mode": "standard",
            "require_manual_approval": False,
            "options": {},
        },
    )


def test_workbench_shell_mode_hub_starts_without_project(mock_orchestrator: MagicMock, tmp_path: Path):
    app_home = tmp_path / "app-home"
    client = _create_workbench_client(tmp_path, mock_orchestrator, app_home)

    try:
        response = client.get("/api/workbench/hub")

        assert response.status_code == 200
        payload = response.json()
        assert payload["workspace_root"] == str(tmp_path)
        assert payload["current_project"] is None
        assert payload["projects"] == []

        project_response = client.get("/api/project/info")
        assert project_response.status_code == 409
        assert project_response.json()["code"] == "PROJECT_NOT_SELECTED"
    finally:
        _close_workbench_client(client)


def test_workbench_open_project_sets_current_and_returns_dashboard_url(mock_project_root: Path, mock_orchestrator: MagicMock, tmp_path: Path):
    app_home = tmp_path / "app-home"
    client = _create_workbench_client(tmp_path, mock_orchestrator, app_home)

    try:
        response = client.post("/api/workbench/open-project", json={"project_root": str(mock_project_root)})

        assert response.status_code == 200
        payload = response.json()
        assert payload["opened"] is True
        assert payload["project_initialized"] is True
        assert payload["suggested_dashboard_url"].startswith("/?project_root=")

        hub_response = client.get("/api/workbench/hub")
        hub_payload = hub_response.json()
        assert hub_payload["current_project"]["project_root"] == str(mock_project_root)
        assert hub_payload["recent_projects"][0]["project_root"] == str(mock_project_root)
        assert (tmp_path / ".webnovel" / "current-project").read_text(encoding="utf-8").strip() == str(mock_project_root)
    finally:
        _close_workbench_client(client)


def test_workbench_open_project_returns_create_hint_for_uninitialized_folder(mock_orchestrator: MagicMock, tmp_path: Path):
    app_home = tmp_path / "app-home"
    project_root = tmp_path / "draft-folder"
    project_root.mkdir(parents=True)
    client = _create_workbench_client(tmp_path, mock_orchestrator, app_home)

    try:
        response = client.post("/api/workbench/open-project", json={"project_root": str(project_root)})

        assert response.status_code == 200
        payload = response.json()
        assert payload["opened"] is False
        assert payload["project_initialized"] is False
        assert payload["next_recommended_action"]
    finally:
        _close_workbench_client(client)


def test_workbench_pin_and_remove_only_update_registry(mock_project_root: Path, mock_orchestrator: MagicMock, tmp_path: Path):
    app_home = tmp_path / "app-home"
    client = _create_workbench_client(tmp_path, mock_orchestrator, app_home)

    try:
        open_response = client.post("/api/workbench/open-project", json={"project_root": str(mock_project_root)})
        assert open_response.status_code == 200

        pin_response = client.post("/api/workbench/pin-project", json={"project_root": str(mock_project_root)})
        assert pin_response.status_code == 200
        assert str(mock_project_root) in pin_response.json()["entry"]["pinned_project_roots"]

        remove_response = client.post("/api/workbench/remove-project", json={"project_root": str(mock_project_root)})
        assert remove_response.status_code == 200
        assert str(mock_project_root) not in [item["project_root"] for item in remove_response.json()["entry"]["recent_projects"]]
        assert (mock_project_root / ".webnovel" / "state.json").is_file()
    finally:
        _close_workbench_client(client)


def test_workbench_tools_forward_to_launcher_script(mock_project_root: Path, mock_orchestrator: MagicMock, tmp_path: Path):
    app_home = tmp_path / "app-home"
    client = _create_workbench_client(tmp_path, mock_orchestrator, app_home)

    try:
        with patch("dashboard.app.run", return_value=SimpleNamespace(returncode=0, stdout="", stderr="")) as run_mock:
            response = client.post("/api/workbench/tools/open-shell", json={"project_root": str(mock_project_root)})

        assert response.status_code == 200
        assert response.json()["launched"] is True
        command = run_mock.call_args.args[0]
        assert str(command[0]).endswith("powershell.exe")
        assert command[4] == "-File"
        assert "Start-Webnovel-Writer.ps1" in str(command[5])
        assert command[6:] == ["shell", "-ProjectRoot", str(mock_project_root)]
    finally:
        _close_workbench_client(client)


def test_supervisor_recommendations_endpoint_returns_backend_payload(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.list_supervisor_recommendations.return_value = [
        {
            "stableKey": "approval:task-1",
            "category": "approval",
            "categoryLabel": "审批",
            "priority": 10,
            "tone": "warning",
            "badge": "先处理",
            "title": "第 3 章待回写审批",
            "summary": "当前任务正在等待人工确认后再继续回写。",
            "detail": "不先处理这个审批，护栏推进无法安全往后继续。",
            "rationale": "人工审批是硬阻断。",
            "sourceTaskId": "task-1",
            "sourceUpdatedAt": "2026-03-19T10:00:00+00:00",
            "fingerprint": "approval:task-1|task-1",
            "action": {"type": "open-task", "taskId": "task-1"},
            "actionLabel": "打开待审批任务",
            "secondaryAction": None,
            "secondaryLabel": None,
        }
    ]

    response = client.get("/api/supervisor/recommendations")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["stableKey"] == "approval:task-1"
    assert payload[0]["action"]["type"] == "open-task"
    assert "approval-gate" not in payload[0]["summary"]
    assert "等待人工确认后再继续回写" in payload[0]["summary"]
    assert "secondaryAction" in payload[0]
    mock_orchestrator.list_supervisor_recommendations.assert_called_once_with(limit=4)


def test_cancel_task_returns_not_found_when_missing(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.cancel_task.side_effect = KeyError("missing")

    response = client.post("/api/tasks/missing/cancel", json={"reason": "stop"})

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_bootstrap_project_success(client: TestClient, mock_project_root: Path):
    target_root = mock_project_root.parent / "bootstrap-target"

    def fake_run(command, cwd, capture_output, text, encoding, errors, check):
        webnovel_dir = target_root / ".webnovel"
        webnovel_dir.mkdir(parents=True, exist_ok=True)
        (target_root / "大纲").mkdir(parents=True, exist_ok=True)
        (target_root / "大纲" / "总纲.md").write_text("# 总纲\n\n## 故事前提\n- 书名：Test Book\n", encoding="utf-8")
        (webnovel_dir / "planning-profile.json").write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")
        (webnovel_dir / "state.json").write_text(
            json.dumps(
                {
                    "project_info": {"title": "Test Book", "genre": "Urban Fantasy"},
                    "planning": {
                        "project_info": {"title": "Test Book", "genre": "Urban Fantasy", "outline_file": "大纲/总纲.md"},
                        "profile": {},
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with patch("dashboard.app.run", side_effect=fake_run):
        response = client.post(
            "/api/project/bootstrap",
            json={
                "project_root": str(target_root),
                "title": "Test Book",
                "genre": "Urban Fantasy",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data["created"] is True
    assert data["project_root"] == str(target_root)
    assert data["project_switch_required"] is True
    assert data["suggested_dashboard_url"].startswith("/?project_root=")
    assert "bootstrap_hint=planning" in data["suggested_dashboard_url"]
    assert Path(data["state_file"]).is_file()
    assert (target_root / ".webnovel" / "planning-profile.json").is_file()
    assert data["planning_profile"]["outline_file"] == "大纲/总纲.md"
    assert data["planning_profile"]["project_info"]["title"] == "Test Book"
    assert data["planning_profile"]["profile"]["protagonist_name"] == ""
    assert data["planning_profile"]["readiness"]["ok"] is False
    assert data["next_recommended_action"]
    assert (mock_project_root.parent / ".webnovel" / "current-project").read_text(encoding="utf-8").strip() == str(target_root)


def test_bootstrap_project_conflict_for_existing_project(client: TestClient, mock_project_root: Path):
    response = client.post("/api/project/bootstrap", json={"project_root": str(mock_project_root)})
    assert response.status_code == 409
    data = response.json()
    assert data["code"] == "CONFLICT"


def test_request_validation_error_returns_standard_payload(client: TestClient):
    response = client.post("/api/review/confirm-invalid-facts", json={"ids": "bad-payload", "action": "confirm"})
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert data["details"]["status_code"] == 422
    assert data["details"]["errors"]


def test_get_llm_settings_defaults(client: TestClient):
    response = client.get("/api/settings/llm")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openai-compatible"
    assert "api_key_masked" in data


def test_save_llm_settings_updates_env_and_status(client: TestClient, mock_project_root: Path):
    response = client.post(
        "/api/settings/llm",
        json={
            "provider": "openai-compatible",
            "base_url": "https://example.com/v1",
            "model": "gpt-test",
            "api_key": "secret-key-1234",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["saved"] is True
    env_text = (mock_project_root / ".env").read_text(encoding="utf-8")
    assert "WEBNOVEL_LLM_MODEL=gpt-test" in env_text
    assert data["settings"]["has_api_key"] is True


def test_save_rag_settings_updates_env_and_status(client: TestClient, mock_project_root: Path):
    response = client.post(
        "/api/settings/rag",
        json={
            "base_url": "https://rag.example.com/v1",
            "embed_model": "embed-test",
            "rerank_model": "rerank-test",
            "api_key": "rag-secret-1234",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["saved"] is True
    env_text = (mock_project_root / ".env").read_text(encoding="utf-8")
    assert "WEBNOVEL_RAG_EMBED_MODEL=embed-test" in env_text
    assert data["settings"]["has_api_key"] is True


def test_planning_profile_endpoints_sync_state_and_outline(client: TestClient, mock_project_root: Path):
    state_path = mock_project_root / ".webnovel" / "state.json"
    seeded = json.loads(state_path.read_text(encoding="utf-8"))
    seeded["chapter_meta"] = {"1": {"title": "Existing Chapter"}}
    seeded["disambiguation_warnings"] = [{"chapter": 1, "mention": "雨城"}]
    state_path.write_text(json.dumps(seeded, ensure_ascii=False, indent=2), encoding="utf-8")
    outline_path = mock_project_root / "大纲" / "总纲.md"
    outline_path.parent.mkdir(parents=True, exist_ok=True)
    outline_path.write_text("# 总纲\n", encoding="utf-8")

    response = client.post(
        "/api/project/planning-profile",
        json={
            "story_logline": "Hero can rewind ten minutes at the cost of permanent memory loss.",
            "protagonist_name": "Shen Yan",
            "protagonist_identity": "Clock repairer in Night Rain City",
            "protagonist_initial_state": "Mother missing, debts piling up",
            "protagonist_desire": "Find the truth behind the city anomalies",
            "protagonist_flaw": "Keeps spending memory to force progress",
            "core_setting": "Urban anomaly network hidden under constant rain",
            "ability_cost": "Each rewind erases one real memory forever",
            "volume_1_title": "First Rewind in the Rain",
            "volume_1_conflict": "Break the warning chain before memory collapse",
            "volume_1_climax": "Expose rewind traces at the observation point",
            "major_characters_text": "Shen Yan | lead | self | discovers the cost",
            "factions_text": "Bureau | official | unstable ally",
            "rules_outline": "Anomaly warnings leak ten minutes early on rainy nights",
            "foreshadowing_text": "Repeated warning source | 1 | 5 | A",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["saved"] is True
    assert payload["readiness"]["ok"] is True

    state = json.loads((mock_project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    profile_path = mock_project_root / ".webnovel" / "planning-profile.json"
    assert state["planning"]["profile"]["protagonist_name"] == "Shen Yan"
    assert state["planning"]["readiness"]["ok"] is True
    assert state["chapter_meta"]["1"]["title"] == "Existing Chapter"
    assert state["disambiguation_warnings"][0]["mention"] == "雨城"
    assert profile_path.is_file()
    saved_profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert saved_profile["protagonist_name"] == "Shen Yan"
    outline_text = outline_path.read_text(encoding="utf-8")
    assert "## 故事前提" in outline_text
    assert "First Rewind in the Rain" in outline_text

    get_response = client.get("/api/project/planning-profile")
    assert get_response.status_code == 200
    assert get_response.json()["profile"]["volume_1_title"] == "First Rewind in the Rain"


def test_planning_profile_endpoints_fail_when_state_file_is_corrupted(client: TestClient, mock_project_root: Path):
    state_path = mock_project_root / ".webnovel" / "state.json"
    state_path.write_text("{broken json", encoding="utf-8")

    get_response = client.get("/api/project/planning-profile")
    assert get_response.status_code == 500
    assert get_response.json()["code"] == "STATE_FILE_CORRUPTED"

    post_response = client.post(
        "/api/project/planning-profile",
        json={
            "story_logline": "Corrupted state test",
            "protagonist_name": "Tester",
            "core_setting": "Broken state",
        },
    )
    assert post_response.status_code == 500
    assert post_response.json()["code"] == "STATE_FILE_CORRUPTED"


def test_project_info_supports_request_scoped_project_root(client: TestClient, mock_project_root: Path):
    other_root = mock_project_root.parent / "other-project"
    (other_root / ".webnovel").mkdir(parents=True)
    (other_root / ".webnovel" / "state.json").write_text(
        json.dumps({"project_info": {"title": "Other Root"}}, ensure_ascii=False),
        encoding="utf-8",
    )

    response = client.get("/api/project/info", params={"project_root": str(other_root)})

    assert response.status_code == 200
    assert response.json()["project_info"]["title"] == "Other Root"
    assert response.json()["dashboard_context"]["project_root"] == str(other_root)
    assert response.json()["dashboard_context"]["project_initialized"] is True


def test_file_read_returns_metadata_for_text_file(client: TestClient, mock_project_root: Path):
    target = mock_project_root / "正文" / "第0001章.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("测试正文", encoding="utf-8")

    response = client.get("/api/files/read", params={"path": "正文/第0001章.md"})

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["is_binary"] is False
    assert data["encoding"] == "utf-8"
    assert data["size"] > 0
    assert data["modified_at"]
    assert data["content"] == "测试正文"


def test_file_read_returns_binary_metadata_for_non_text_file(client: TestClient, mock_project_root: Path):
    target = mock_project_root / "正文" / "封面.bin"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"\xff\x00\xab")

    response = client.get("/api/files/read", params={"path": "正文/封面.bin"})

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["is_binary"] is True
    assert data["encoding"] == "binary"
    assert data["size"] == 3
    assert data["modified_at"]
    assert data["content"] == ""


def test_file_tree_includes_project_state_and_summaries(client: TestClient, mock_project_root: Path):
    summaries_dir = mock_project_root / ".webnovel" / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    (summaries_dir / "ch0001.md").write_text("# 第1章摘要\n", encoding="utf-8")

    response = client.get("/api/files/tree")

    assert response.status_code == 200
    payload = response.json()
    assert "项目状态" in payload
    state_paths = [item["path"] for item in payload["项目状态"]]
    assert ".webnovel/state.json" in state_paths
    summary_dir = next(item for item in payload["项目状态"] if item["path"] == ".webnovel/summaries")
    assert any(child["path"] == ".webnovel/summaries/ch0001.md" for child in summary_dir["children"])


def test_file_read_supports_state_json_and_summaries(client: TestClient, mock_project_root: Path):
    summaries_dir = mock_project_root / ".webnovel" / "summaries"
    summaries_dir.mkdir(parents=True, exist_ok=True)
    (summaries_dir / "ch0002.md").write_text("# 第2章摘要\n", encoding="utf-8")

    state_response = client.get("/api/files/read", params={"path": ".webnovel/state.json"})
    summary_response = client.get("/api/files/read", params={"path": ".webnovel/summaries/ch0002.md"})

    assert state_response.status_code == 200
    assert summary_response.status_code == 200
    assert state_response.json()["content"]
    assert summary_response.json()["content"] == "# 第2章摘要\n"


def test_relationships_endpoint_returns_entity_display_names(client: TestClient, mock_project_root: Path):
    conn = sqlite3.connect(str(mock_project_root / ".webnovel" / "index.db"))
    conn.execute(
        "INSERT INTO entities (id, canonical_name, type, is_archived, last_appearance) VALUES (?, ?, ?, 0, ?)",
        ("shenyan", "沈言", "character", 2),
    )
    conn.execute(
        "INSERT INTO entities (id, canonical_name, type, is_archived, last_appearance) VALUES (?, ?, ?, 0, ?)",
        ("shenmu", "沈母", "character", 1),
    )
    conn.execute(
        "INSERT INTO relationships (from_entity, to_entity, type, chapter) VALUES (?, ?, ?, ?)",
        ("shenyan", "shenmu", "family", 2),
    )
    conn.commit()
    conn.close()

    response = client.get("/api/relationships")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["from_entity_name"] == "沈言"
    assert payload[0]["to_entity_name"] == "沈母"


def test_file_tree_uses_hierarchical_display_names_for_volume_and_chapter(client: TestClient, mock_project_root: Path):
    chapter_file = mock_project_root / "正文" / "第1卷" / "第0002章.md"
    chapter_file.parent.mkdir(parents=True, exist_ok=True)
    chapter_file.write_text("测试正文", encoding="utf-8")

    response = client.get("/api/files/tree")

    assert response.status_code == 200
    payload = response.json()
    body_root = next(item for item in payload["正文"] if item["path"] == "正文/第1卷")
    assert body_root["display_name"] == "第1卷"
    chapter_node = next(item for item in body_root["children"] if item["path"] == "正文/第1卷/第0002章.md")
    assert chapter_node["display_name"] == "第2章"


def test_file_read_returns_hierarchical_display_name_and_display_timestamp(client: TestClient, mock_project_root: Path):
    chapter_file = mock_project_root / "正文" / "第1卷" / "第0001章.md"
    chapter_file.parent.mkdir(parents=True, exist_ok=True)
    chapter_file.write_text("测试正文", encoding="utf-8")

    response = client.get("/api/files/read", params={"path": "正文/第1卷/第0001章.md"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["display_name"] == "第1章"
    assert payload["modified_at_display"]


def test_review_metrics_and_relationships_expose_display_helpers(client: TestClient, mock_project_root: Path):
    conn = sqlite3.connect(str(mock_project_root / ".webnovel" / "index.db"))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS review_metrics (id INTEGER PRIMARY KEY AUTOINCREMENT, end_chapter INTEGER, overall_score REAL, created_at TEXT)"
    )
    conn.execute(
        "INSERT INTO entities (id, canonical_name, type, is_archived, last_appearance) VALUES (?, ?, ?, 0, ?)",
        ("shenyan", "沈言", "character", 2),
    )
    conn.execute(
        "INSERT INTO entities (id, canonical_name, type, is_archived, last_appearance) VALUES (?, ?, ?, 0, ?)",
        ("shenmu", "沈母", "character", 1),
    )
    conn.execute(
        "INSERT INTO relationships (from_entity, to_entity, type, chapter) VALUES (?, ?, ?, ?)",
        ("shenyan", "shenmu", "family", 2),
    )
    conn.execute(
        "INSERT INTO review_metrics (end_chapter, overall_score, created_at) VALUES (?, ?, ?)",
        (2, 95, "2026-03-18T09:59:08+00:00"),
    )
    conn.commit()
    conn.close()

    relationship_response = client.get("/api/relationships")
    review_response = client.get("/api/review-metrics")

    assert relationship_response.status_code == 200
    assert review_response.status_code == 200
    relationship = relationship_response.json()[0]
    metric = review_response.json()[0]
    assert relationship["from_entity_display"] == "沈言"
    assert relationship["to_entity_display"] == "沈母"
    assert relationship["type_label"] == "家庭"
    assert relationship["from_entity_label"] == "起始实体"
    assert relationship["to_entity_label"] == "目标实体"
    assert relationship["type_label_label"] == "关系类型"
    assert metric["created_at_display"] == "2026-03-18 17:59:08"


def test_story_plans_endpoint_reads_file_backed_story_director_payloads(client: TestClient, mock_project_root: Path):
    story_dir = mock_project_root / ".webnovel" / "story-director"
    story_dir.mkdir(parents=True, exist_ok=True)
    (story_dir / "plan-ch0012.json").write_text(
        json.dumps(
            {
                "anchor_chapter": 12,
                "planning_horizon": 4,
                "priority_threads": ["黑匣子真相", "信任裂缝"],
                "payoff_schedule": [{"thread": "黑匣子真相", "target_chapter": 12, "mode": "major"}],
                "defer_schedule": [{"thread": "终局身份揭露", "not_before_chapter": 18, "reason": "too early"}],
                "risk_flags": ["最近两章信息揭露偏密"],
                "transition_notes": ["第12章先把调查线切到家族线"],
                "chapters": [
                    {
                        "chapter": 12,
                        "role": "current-execution",
                        "chapter_goal": "让主角确认黑匣子线索可信，但付出关系代价",
                        "must_advance_threads": ["黑匣子真相", "信任裂缝"],
                        "optional_payoffs": ["黑匣子真相"],
                        "forbidden_resolutions": ["不要公开幕后主使"],
                        "ending_hook_target": "章末迫使主角进入敌方地盘",
                    }
                ],
                "rationale": "当前最需要解决的是中程驱动力不足。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    response = client.get("/api/story-plans")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["anchor_chapter"] == 12
    assert payload[0]["current_role"] == "current-execution"
    assert payload[0]["current_goal"] == "让主角确认黑匣子线索可信，但付出关系代价"
    assert payload[0]["priority_threads"] == ["黑匣子真相", "信任裂缝"]
    assert payload[0]["updated_at_display"]


def test_director_hub_endpoint_returns_current_brief_and_continuity_ledgers(
    client: TestClient,
    mock_project_root: Path,
    mock_orchestrator: MagicMock,
):
    director_dir = mock_project_root / ".webnovel" / "director"
    director_dir.mkdir(parents=True, exist_ok=True)
    (director_dir / "ch0003.json").write_text(
        json.dumps(
            {
                "chapter": 3,
                "chapter_goal": "Push the bureau clue forward.",
                "primary_conflict": "Shen Yan must move before the cost spikes.",
                "must_advance_threads": ["warning source", "bureau debt"],
                "forbidden_terms": ["system panel"],
                "voice_constraints": ["Keep Shen Yan terse."],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    state = json.loads((mock_project_root / ".webnovel" / "state.json").read_text(encoding="utf-8"))
    state["progress"]["current_chapter"] = 2
    state["voice_bible"] = {"characters": {"Shen Yan": {"constraints": ["Keep Shen Yan terse."]}}}
    state["mystery_ledger"] = [{"name": "warning source", "status": "active"}]
    state["rule_assertions"] = [{"name": "Every rewind burns one memory"}]
    state["trust_map"] = {"Shen Yan->Bureau": {"status": "fragile", "chapter": 3}}
    state["director_decisions"] = [{"chapter": 3, "decision": "Hold back the watcher identity."}]
    state["plot_threads"] = {"active_threads": [{"title": "warning source", "stage": "active"}], "foreshadowing": []}
    (mock_project_root / ".webnovel" / "state.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    mock_orchestrator.get_director_hub.return_value = {
        "current_chapter": 3,
        "current_brief": {
            "chapter": 3,
            "chapter_goal": "Push the bureau clue forward.",
            "primary_conflict": "Shen Yan must move before the cost spikes.",
        },
        "voice_bible": {"characters": {"Shen Yan": {"constraints": ["Keep Shen Yan terse."]}}},
        "continuity": {
            "mystery_ledger": [{"name": "warning source", "status": "active"}],
            "rule_assertions": [{"name": "Every rewind burns one memory"}],
            "trust_map": {"Shen Yan->Bureau": {"status": "fragile", "chapter": 3}},
            "director_decisions": [{"chapter": 3, "decision": "Hold back the watcher identity."}],
            "plot_threads": [{"title": "warning source", "stage": "active"}],
        },
    }

    response = client.get("/api/project/director-hub")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_brief"]["chapter"] == 3
    assert payload["voice_bible"]["characters"]["Shen Yan"]["constraints"] == ["Keep Shen Yan terse."]
    assert payload["continuity"]["mystery_ledger"][0]["name"] == "warning source"
    assert payload["continuity"]["plot_threads"][0]["title"] == "warning source"
    mock_orchestrator.get_director_hub.assert_called_once()


def test_chapter_brief_approve_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.approve_chapter_brief.return_value = {
        "id": "task-brief-1",
        "status": "queued",
        "current_step": "chapter-brief-approval",
    }

    response = client.post("/api/chapters/3/brief/approve", json={"reason": "批准开写"})

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
    mock_orchestrator.approve_chapter_brief.assert_called_once_with(3, "批准开写")


def test_foreshadowing_endpoint_supports_chapter_entity_and_limit(client: TestClient, mock_project_root: Path):
    _seed_narrative_tables(mock_project_root)

    response = client.get("/api/foreshadowing", params={"chapter": 2, "entity": "hero", "limit": 1})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["name"] == "setup-2"
    assert payload[0]["entity_id"] == "hero"


def test_foreshadowing_endpoint_excludes_paid_off_items_for_planted_schema(client: TestClient, mock_project_root: Path):
    conn = sqlite3.connect(str(mock_project_root / ".webnovel" / "index.db"))
    conn.execute(
        """
        CREATE TABLE foreshadowing_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            owner_entity TEXT,
            planted_chapter INTEGER,
            payoff_chapter INTEGER DEFAULT 0,
            status TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO foreshadowing_items (name, owner_entity, planted_chapter, payoff_chapter, status) VALUES (?, ?, ?, ?, ?)",
        [
            ("paid-off-setup", "hero", 1, 2, "paid_off"),
            ("active-setup", "hero", 3, 0, "active"),
        ],
    )
    conn.commit()
    conn.close()

    response = client.get("/api/foreshadowing", params={"chapter": 10, "entity": "hero", "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload] == ["active-setup"]


def test_timeline_events_endpoint_supports_chapter_entity_and_limit(client: TestClient, mock_project_root: Path):
    _seed_narrative_tables(mock_project_root)

    response = client.get("/api/timeline-events", params={"chapter": 2, "entity": "hero", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["summary"] == "timeline hero chapter 2"
    assert payload[0]["chapter"] == 2


def test_character_arcs_endpoint_supports_chapter_entity_and_limit(client: TestClient, mock_project_root: Path):
    _seed_narrative_tables(mock_project_root)

    response = client.get("/api/character-arcs", params={"chapter": 2, "entity": "hero", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["entity_id"] == "hero"
    assert payload[0]["arc_stage"] == "committed"


def test_knowledge_states_endpoint_supports_chapter_entity_and_limit(client: TestClient, mock_project_root: Path):
    _seed_narrative_tables(mock_project_root)

    response = client.get("/api/knowledge-states", params={"chapter": 2, "entity": "hero", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["fact"] == "secret-b"
    assert payload[0]["state"] == "confirmed"


def test_supervisor_dismiss_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.dismiss_supervisor_recommendation.return_value = {
        "stableKey": "approval:task-1",
        "fingerprint": "approval:task-1|task-1",
        "dismissedAt": "2026-03-19T10:00:00+00:00",
        "dismissalReason": "defer",
        "dismissalNote": "等本轮结束",
        "dismissed": True,
    }

    response = client.post(
        "/api/supervisor/dismiss",
        json={
            "stable_key": "approval:task-1",
            "fingerprint": "approval:task-1|task-1",
            "reason": "defer",
            "note": "等本轮结束",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dismissed"] is True
    assert payload["dismissalReason"] == "defer"
    mock_orchestrator.dismiss_supervisor_recommendation.assert_called_once_with(
        "approval:task-1",
        "approval:task-1|task-1",
        reason="defer",
        note="等本轮结束",
    )


def test_supervisor_undismiss_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.undismiss_supervisor_recommendation.return_value = {
        "stableKey": "approval:task-1",
        "dismissed": False,
    }

    response = client.post(
        "/api/supervisor/undismiss",
        json={"stable_key": "approval:task-1", "fingerprint": ""},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dismissed"] is False
    mock_orchestrator.undismiss_supervisor_recommendation.assert_called_once_with("approval:task-1")


def test_supervisor_recommendations_endpoint_passes_include_dismissed(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.list_supervisor_recommendations.return_value = []

    response = client.get("/api/supervisor/recommendations", params={"include_dismissed": "true"})

    assert response.status_code == 200
    mock_orchestrator.list_supervisor_recommendations.assert_called_once_with(limit=4, include_dismissed=True)


def test_supervisor_batch_dismiss_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.dismiss_supervisor_recommendations_batch.return_value = {"updated": [], "count": 2}

    response = client.post(
        "/api/supervisor/dismiss-batch",
        json={
            "items": [
                {"stable_key": "approval:task-1", "fingerprint": "fp-1"},
                {"stable_key": "review:task-2", "fingerprint": "fp-2"},
            ],
            "reason": "batch_later",
            "note": "统一稍后处理",
        },
    )

    assert response.status_code == 200
    assert response.json()["count"] == 2
    mock_orchestrator.dismiss_supervisor_recommendations_batch.assert_called_once_with(
        [
            {"stable_key": "approval:task-1", "fingerprint": "fp-1"},
            {"stable_key": "review:task-2", "fingerprint": "fp-2"},
        ],
        reason="batch_later",
        note="统一稍后处理",
    )


def test_supervisor_batch_undismiss_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.undismiss_supervisor_recommendations_batch.return_value = {"updated": [], "count": 2}

    response = client.post(
        "/api/supervisor/undismiss-batch",
        json={"stable_keys": ["approval:task-1", "review:task-2"]},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 2
    mock_orchestrator.undismiss_supervisor_recommendations_batch.assert_called_once_with(["approval:task-1", "review:task-2"])


def test_supervisor_tracking_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.set_supervisor_recommendation_tracking.return_value = {
        "stableKey": "approval:task-1",
        "trackingStatus": "in_progress",
        "trackingLabel": "处理中",
        "trackingNote": "等待审批",
        "trackingUpdatedAt": "2026-03-19T10:05:00+00:00",
    }

    response = client.post(
        "/api/supervisor/tracking",
        json={
            "stable_key": "approval:task-1",
            "fingerprint": "fp-1",
            "status": "in_progress",
            "note": "等待审批",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trackingStatus"] == "in_progress"
    mock_orchestrator.set_supervisor_recommendation_tracking.assert_called_once_with(
        "approval:task-1",
        "fp-1",
        status="in_progress",
        note="等待审批",
    )


def test_supervisor_tracking_clear_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.clear_supervisor_recommendation_tracking.return_value = {
        "stableKey": "approval:task-1",
        "trackingStatus": "",
        "trackingLabel": "",
        "trackingNote": "",
        "trackingUpdatedAt": None,
    }

    response = client.post(
        "/api/supervisor/tracking/clear",
        json={"stable_key": "approval:task-1", "fingerprint": "", "status": "", "note": ""},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["trackingStatus"] == ""
    mock_orchestrator.clear_supervisor_recommendation_tracking.assert_called_once_with("approval:task-1")


def test_supervisor_tracking_endpoint_accepts_task_and_checklist_links(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.set_supervisor_recommendation_tracking.return_value = {
        "stableKey": "approval:task-1",
        "trackingStatus": "completed",
        "trackingLabel": "已处理",
        "trackingNote": "linked-proof",
        "linkedTaskId": "task-approval-1",
        "linkedChecklistPath": ".webnovel/supervisor/checklists/checklist-ch0003-20260319-100000.md",
        "trackingUpdatedAt": "2026-03-19T10:05:00+00:00",
    }

    response = client.post(
        "/api/supervisor/tracking",
        json={
            "stable_key": "approval:task-1",
            "fingerprint": "fp-1",
            "status": "completed",
            "note": "linked-proof",
            "linked_task_id": "task-approval-1",
            "linked_checklist_path": ".webnovel/supervisor/checklists/checklist-ch0003-20260319-100000.md",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["linkedTaskId"] == "task-approval-1"
    assert payload["linkedChecklistPath"] == ".webnovel/supervisor/checklists/checklist-ch0003-20260319-100000.md"
    mock_orchestrator.set_supervisor_recommendation_tracking.assert_called_with(
        "approval:task-1",
        "fp-1",
        status="completed",
        note="linked-proof",
        linked_task_id="task-approval-1",
        linked_checklist_path=".webnovel/supervisor/checklists/checklist-ch0003-20260319-100000.md",
    )


def test_supervisor_checklist_save_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.save_supervisor_checklist.return_value = {
        "savedAt": "2026-03-19T10:10:00+00:00",
        "chapter": 6,
        "filename": "checklist-ch0006-20260319-181000.md",
        "path": "/tmp/novel/.webnovel/supervisor/checklists/checklist-ch0006-20260319-181000.md",
        "relativePath": ".webnovel/supervisor/checklists/checklist-ch0006-20260319-181000.md",
        "selectedCount": 2,
        "title": "第6章开写前清单",
        "note": "本轮先处理审批和刷新建议",
    }

    response = client.post(
        "/api/supervisor/checklists",
        json={
            "content": "# Supervisor Checklist\n\n- item",
            "chapter": 6,
            "selected_keys": ["approval:task-1", "review:task-2"],
            "category_filter": "approval",
            "sort_mode": "priority",
            "title": "第6章开写前清单",
            "note": "本轮先处理审批和刷新建议",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chapter"] == 6
    assert payload["selectedCount"] == 2
    assert payload["title"] == "第6章开写前清单"
    mock_orchestrator.save_supervisor_checklist.assert_called_once_with(
        "# Supervisor Checklist\n\n- item",
        chapter=6,
        selected_keys=["approval:task-1", "review:task-2"],
        category_filter="approval",
        sort_mode="priority",
        title="第6章开写前清单",
        note="本轮先处理审批和刷新建议",
    )


def test_supervisor_checklist_list_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.list_supervisor_checklists.return_value = [
        {
            "filename": "checklist-ch0006-20260319-181000.md",
            "relativePath": ".webnovel/supervisor/checklists/checklist-ch0006-20260319-181000.md",
            "chapter": 6,
            "savedAt": "2026-03-19T10:10:00+00:00",
            "categoryFilter": "all",
            "sortMode": "priority",
            "selectedCount": 2,
            "title": "第6章开写前清单",
            "note": "本轮先处理审批和刷新建议",
            "selectedKeys": ["approval:task-1", "review:task-2"],
            "content": "# Checklist",
            "summary": "- item",
        }
    ]

    response = client.get("/api/supervisor/checklists", params={"limit": 6})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["chapter"] == 6
    assert payload[0]["selectedCount"] == 2
    assert payload[0]["title"] == "第6章开写前清单"
    mock_orchestrator.list_supervisor_checklists.assert_called_once_with(limit=6)


def test_supervisor_audit_repair_reports_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.list_supervisor_audit_repair_reports.return_value = [
        {
            "filename": "repair-report-20260320-101500-000001.json",
            "relativePath": ".webnovel/supervisor/audit-repair-reports/repair-report-20260320-101500-000001.json",
            "generatedAt": "2026-03-20T10:15:00+00:00",
            "changed": True,
            "droppedCount": 1,
            "rewrittenCount": 2,
            "manualReviewCount": 1,
            "content": {"summary": {"dropped_count": 1}},
        }
    ]

    response = client.get("/api/supervisor/audit-repair-reports", params={"limit": 6})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["changed"] is True
    assert payload[0]["rewrittenCount"] == 2
    mock_orchestrator.list_supervisor_audit_repair_reports.assert_called_once_with(limit=6)


def test_supervisor_audit_log_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.list_supervisor_audit_log.return_value = [
        {
            "schema_version": 1,
            "schemaState": "supported",
            "timestamp": "2026-03-19T10:15:00+00:00",
            "action": "tracking_updated",
            "stableKey": "approval:task-1",
            "category": "approval",
            "categoryLabel": "审批",
            "title": "第 3 章待回写审批",
            "status_snapshot": "completed",
            "linked_task_id": "task-approval-1",
        }
    ]

    response = client.get("/api/supervisor/audit-log", params={"limit": 12})

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["action"] == "tracking_updated"
    assert payload[0]["stableKey"] == "approval:task-1"
    assert payload[0]["schema_version"] == 1
    assert payload[0]["schemaState"] == "supported"
    mock_orchestrator.list_supervisor_audit_log.assert_called_once_with(limit=12)


def test_supervisor_audit_health_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.get_supervisor_audit_health.return_value = {
        "healthy": False,
        "exists": True,
        "total_lines": 4,
        "nonempty_lines": 3,
        "valid_entries": 2,
        "issue_count": 1,
        "issueCounts": {"invalid_json": 1},
        "schemaStateCounts": {"supported": 1, "future": 1},
        "schemaVersionCounts": {"1": 1, "3": 1},
        "issues": [{"code": "invalid_json", "severity": "danger", "line": 2, "message": "bad json"}],
        "latestTimestamp": "2026-03-19T10:15:00+00:00",
        "earliestTimestamp": "2026-03-19T10:10:00+00:00",
    }

    response = client.get("/api/supervisor/audit-health", params={"issue_limit": 8})

    assert response.status_code == 200
    payload = response.json()
    assert payload["healthy"] is False
    assert payload["issueCounts"]["invalid_json"] == 1
    assert payload["issues"][0]["code"] == "invalid_json"
    mock_orchestrator.get_supervisor_audit_health.assert_called_once_with(issue_limit=8)


def test_supervisor_audit_repair_preview_endpoint_calls_orchestrator(client: TestClient, mock_orchestrator: MagicMock):
    mock_orchestrator.get_supervisor_audit_repair_preview.return_value = {
        "exists": True,
        "total_lines": 3,
        "nonempty_lines": 3,
        "repairable_count": 1,
        "manual_review_count": 1,
        "actionCounts": {"rewrite_normalized_event": 1, "manual_review": 1},
        "proposals": [
            {"line": 1, "action": "rewrite_normalized_event", "severity": "warning", "reason": "normalize legacy aliases"},
            {"line": 2, "action": "manual_review", "severity": "danger", "reason": "missing action"},
        ],
    }

    response = client.get("/api/supervisor/audit-repair-preview", params={"proposal_limit": 6})

    assert response.status_code == 200
    payload = response.json()
    assert payload["repairable_count"] == 1
    assert payload["manual_review_count"] == 1
    assert payload["proposals"][0]["action"] == "rewrite_normalized_event"
    mock_orchestrator.get_supervisor_audit_repair_preview.assert_called_once_with(proposal_limit=6)
