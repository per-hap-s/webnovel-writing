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
    conn.execute("CREATE TABLE entities (id TEXT PRIMARY KEY, name TEXT, type TEXT, is_archived INTEGER DEFAULT 0, last_appearance INTEGER)")
    conn.execute("CREATE TABLE relationships (id INTEGER PRIMARY KEY AUTOINCREMENT, from_entity TEXT, to_entity TEXT, relation_type TEXT, chapter INTEGER)")
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
    return orchestrator


@pytest.fixture
def client(mock_project_root: Path, mock_orchestrator: MagicMock) -> TestClient:
    with patch("dashboard.app.OrchestrationService", return_value=mock_orchestrator):
        app = create_app(project_root=mock_project_root)
        app.state.orchestrator = mock_orchestrator
        with TestClient(app) as test_client:
            yield test_client


def test_llm_status_success(client: TestClient, mock_orchestrator: MagicMock):
    response = client.get("/api/llm/status")
    assert response.status_code == 200
    assert response.json()["provider"] == "openai-compatible"
    mock_orchestrator.probe_llm.assert_called_once()


def test_rag_status_success(client: TestClient, mock_orchestrator: MagicMock):
    response = client.get("/api/rag/status")
    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "siliconflow"
    assert data["embed_model"] == "BAAI/bge-m3"
    assert data["retry_policy"]["max_retries"] == 6
    mock_orchestrator.probe_rag.assert_called_once()


def test_bootstrap_project_success(client: TestClient, mock_project_root: Path):
    target_root = mock_project_root.parent / "bootstrap-target"

    def fake_run(command, cwd, capture_output, text, encoding, errors, check):
        webnovel_dir = target_root / ".webnovel"
        webnovel_dir.mkdir(parents=True, exist_ok=True)
        (webnovel_dir / "state.json").write_text("{}", encoding="utf-8")
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
    assert Path(data["state_file"]).is_file()


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
    assert state["planning"]["profile"]["protagonist_name"] == "Shen Yan"
    assert state["planning"]["readiness"]["ok"] is True
    outline_text = outline_path.read_text(encoding="utf-8")
    assert "## 故事前提" in outline_text
    assert "First Rewind in the Rain" in outline_text

    get_response = client.get("/api/project/planning-profile")
    assert get_response.status_code == 200
    assert get_response.json()["profile"]["volume_1_title"] == "First Rewind in the Rain"


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
