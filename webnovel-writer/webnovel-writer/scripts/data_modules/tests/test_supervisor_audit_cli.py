#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    (project_root / ".webnovel").mkdir(parents=True, exist_ok=True)
    (project_root / ".webnovel" / "state.json").write_text("{}", encoding="utf-8")
    return project_root


def test_supervisor_audit_cli_repair_preview_outputs_json(tmp_path: Path):
    project_root = make_project(tmp_path)
    audit_path = project_root / ".webnovel" / "supervisor" / "audit-log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        "\n".join(
            [
                "not-json",
                json.dumps(
                    {
                        "timestamp": "2026-03-19T10:15:00+00:00",
                        "action": "tracking_updated",
                        "stable_key": "approval:task-v1",
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "supervisor_audit.py"),
            "--project-root",
            str(project_root),
            "--format",
            "json",
            "repair-preview",
            "--proposal-limit",
            "5",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["repairable_count"] == 2
    assert payload["actionCounts"]["drop_line"] == 1
    assert payload["actionCounts"]["rewrite_normalized_event"] == 1


def test_supervisor_audit_cli_repair_outputs_report_path(tmp_path: Path):
    project_root = make_project(tmp_path)
    audit_path = project_root / ".webnovel" / "supervisor" / "audit-log.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        "\n".join(
            [
                "not-json",
                json.dumps(
                    {
                        "timestamp": "2026-03-19T10:15:00+00:00",
                        "action": "tracking_updated",
                        "stable_key": "approval:task-v1",
                    },
                    ensure_ascii=False,
                ),
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "supervisor_audit.py"),
            "--project-root",
            str(project_root),
            "--format",
            "json",
            "repair",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["changed"] is True
    assert payload["reportCreated"] is True
    assert Path(payload["reportPath"]).is_file()
