from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import subprocess
from typing import Any


ARTIFACT_RELATIVE_ROOT = Path("output") / "verification" / "multi-agent-test"
RUNTIME_DIRNAME = "_runtime"
ACTIVE_EXECUTION_FILENAME = "active-execution.json"
LAST_KNOWN_EXECUTION_FILENAME = "last-known.json"
CONSOLE_STDOUT_FILENAME = "_dashboard-console.stdout.log"
CONSOLE_STDERR_FILENAME = "_dashboard-console.stderr.log"
LOG_TAIL_DEFAULT_LINES = 200
LOG_TAIL_MAX_LINES = 1000
STREAM_TO_STEP_PATH_KEY = {
    "stdout": "stdout_log_path",
    "stderr": "stderr_log_path",
    "combined": "combined_log_path",
}
STREAM_TO_CONSOLE_FILENAME = {
    "stdout": CONSOLE_STDOUT_FILENAME,
    "stderr": CONSOLE_STDERR_FILENAME,
}


@dataclass(slots=True)
class VerificationArtifactError(Exception):
    code: str
    message: str
    status_code: int = 404


def verification_artifact_root(workspace_root: str | Path) -> Path:
    return Path(workspace_root).resolve() / ARTIFACT_RELATIVE_ROOT


def verification_artifact_dir(workspace_root: str | Path, run_id: str) -> Path:
    return verification_artifact_root(workspace_root) / str(run_id).strip()


def verification_runtime_dir(workspace_root: str | Path) -> Path:
    return verification_artifact_root(workspace_root) / RUNTIME_DIRNAME


def verification_runtime_paths(workspace_root: str | Path) -> dict[str, Path]:
    runtime_dir = verification_runtime_dir(workspace_root)
    return {
        "runtime_dir": runtime_dir,
        "active_execution": runtime_dir / ACTIVE_EXECUTION_FILENAME,
        "last_known": runtime_dir / LAST_KNOWN_EXECUTION_FILENAME,
    }


def verification_console_log_paths(artifact_dir: str | Path) -> dict[str, Path]:
    root = Path(artifact_dir).resolve()
    return {
        "stdout": root / CONSOLE_STDOUT_FILENAME,
        "stderr": root / CONSOLE_STDERR_FILENAME,
    }


def generate_verification_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{secrets.token_hex(3)}"


def start_multi_agent_test_process(workspace_root: str | Path, artifact_dir: str | Path, run_id: str) -> subprocess.Popen:
    workspace_root_path = Path(workspace_root).resolve()
    artifact_dir_path = Path(artifact_dir).resolve()
    artifact_dir_path.mkdir(parents=True, exist_ok=True)
    log_paths = verification_console_log_paths(artifact_dir_path)
    script_path = workspace_root_path / "tools" / "Tests" / "Run-Webnovel-MultiAgentTest.ps1"
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    stdout_handle = log_paths["stdout"].open("w", encoding="utf-8")
    stderr_handle = log_paths["stderr"].open("w", encoding="utf-8")
    try:
        return subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
                "-WorkspaceRoot",
                str(workspace_root_path),
                "-OutputRoot",
                str(artifact_dir_path),
                "-RunId",
                str(run_id),
            ],
            cwd=str(workspace_root_path),
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()


def is_verification_pid_active(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        normalized = int(pid)
    except (TypeError, ValueError):
        return False
    if normalized <= 0:
        return False

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {normalized}", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        creationflags=creationflags,
    )
    output = (result.stdout or "").strip()
    if not output or "No tasks are running" in output:
        return False
    return f'"{normalized}"' in output or f",{normalized}," in output


def persist_active_execution(workspace_root: str | Path, execution: dict[str, Any]) -> dict[str, Any]:
    paths = verification_runtime_paths(workspace_root)
    paths["runtime_dir"].mkdir(parents=True, exist_ok=True)
    payload = dict(execution)
    _write_json_file(paths["active_execution"], payload)
    _write_json_file(paths["last_known"], payload)
    return payload


def clear_active_execution(workspace_root: str | Path, execution: dict[str, Any] | None = None) -> None:
    paths = verification_runtime_paths(workspace_root)
    paths["runtime_dir"].mkdir(parents=True, exist_ok=True)
    if execution:
        _write_json_file(paths["last_known"], dict(execution))
    try:
        paths["active_execution"].unlink()
    except FileNotFoundError:
        pass


def load_active_execution(workspace_root: str | Path) -> dict[str, Any] | None:
    path = verification_runtime_paths(workspace_root)["active_execution"]
    payload = _try_read_json_file(path)
    return dict(payload) if isinstance(payload, dict) else None


def recover_active_verification_execution(workspace_root: str | Path) -> dict[str, Any] | None:
    execution = load_active_execution(workspace_root)
    if not execution:
        return None

    status = str(execution.get("status") or "").strip()
    run_id = str(execution.get("run_id") or "").strip()
    if not run_id:
        clear_active_execution(workspace_root, execution)
        return None

    artifact_dir = verification_artifact_dir(workspace_root, run_id)
    progress = _read_progress_file(artifact_dir)
    if progress:
        execution["progress"] = progress

    if status == "failed_to_launch":
        persist_active_execution(workspace_root, execution)
        return execution

    if is_verification_pid_active(execution.get("pid")):
        execution["status"] = "running"
        persist_active_execution(workspace_root, execution)
        return execution

    result_path = artifact_dir / "result.json"
    if result_path.is_file():
        archived = dict(execution)
        archived["status"] = "completed"
        archived["finished_at"] = archived.get("finished_at") or _format_file_timestamp(result_path)
        clear_active_execution(workspace_root, archived)
        return None

    archived = dict(execution)
    archived["status"] = "incomplete"
    archived["finished_at"] = archived.get("finished_at") or _format_file_timestamp(artifact_dir)
    clear_active_execution(workspace_root, archived)
    return None


def build_verification_overview(
    workspace_root: str | Path,
    *,
    limit: int = 10,
    active_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace_root_path = Path(workspace_root).resolve()
    runtime_execution = active_execution or recover_active_verification_execution(workspace_root_path)
    runs = list_verification_runs(workspace_root_path, limit=limit, active_execution=runtime_execution)
    active_payload = dict(runtime_execution) if runtime_execution else None
    if active_payload:
        active_payload["progress"] = _read_progress_for_execution(workspace_root_path, active_payload)
    return {
        "workspace_root": str(workspace_root_path),
        "active_execution": active_payload,
        "runs": runs,
    }


def build_verification_history(
    workspace_root: str | Path,
    *,
    limit: int = 20,
    cursor: str | None = None,
    classification: str = "",
    status: str = "",
    next_action: str = "",
) -> dict[str, Any]:
    items = list_verification_runs(workspace_root, limit=1000, active_execution=None)
    if classification:
        items = [item for item in items if str(item.get("classification") or "") == classification]
    if status:
        items = [item for item in items if str(item.get("status") or "") == status]
    if next_action:
        items = [item for item in items if str(item.get("next_action") or "") == next_action]

    offset = 0
    if cursor:
        try:
            offset = max(0, int(cursor))
        except ValueError:
            offset = 0

    page = items[offset : offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(items) else ""
    groups = _group_history_items(items)
    return {
        "runs": page,
        "groups": groups,
        "next_cursor": next_cursor,
    }


def list_verification_runs(
    workspace_root: str | Path,
    *,
    limit: int = 10,
    active_execution: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    artifact_root = verification_artifact_root(workspace_root)
    if not artifact_root.is_dir():
        runs: list[dict[str, Any]] = []
    else:
        runs = [
            _summarize_verification_run(path)
            for path in artifact_root.iterdir()
            if path.is_dir() and path.name != RUNTIME_DIRNAME
        ]
        runs.sort(key=_run_sort_key, reverse=True)

    if active_execution:
        active_summary = _execution_to_summary(Path(workspace_root).resolve(), active_execution)
        existing_index = next((index for index, item in enumerate(runs) if item.get("run_id") == active_summary["run_id"]), None)
        if existing_index is None:
            runs.insert(0, active_summary)
        else:
            merged = dict(runs[existing_index])
            merged.update({key: value for key, value in active_summary.items() if value not in (None, "", [])})
            runs[existing_index] = merged
            runs.sort(key=_run_sort_key, reverse=True)

    return runs[:limit]


def get_verification_run_detail(
    workspace_root: str | Path,
    run_id: str,
    *,
    active_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_dir = verification_artifact_dir(workspace_root, run_id)
    if not artifact_dir.is_dir():
        raise VerificationArtifactError("VERIFICATION_RUN_NOT_FOUND", "未找到对应的验证运行记录。", 404)

    progress = get_verification_run_progress(workspace_root, run_id, active_execution=active_execution, raise_on_missing=False)
    manifest = _ensure_manifest(artifact_dir)
    result_path = artifact_dir / "result.json"
    if result_path.is_file():
        try:
            result_payload = _read_json_file(result_path)
        except json.JSONDecodeError as exc:
            raise VerificationArtifactError("VERIFICATION_RESULT_INVALID", "验证结果文件损坏，无法解析。", 409) from exc
        return _build_detail_from_result(
            run_id,
            artifact_dir,
            result_payload,
            progress=progress,
            manifest=manifest,
            active_execution=active_execution,
        )
    return _build_incomplete_detail(
        run_id,
        artifact_dir,
        progress=progress,
        manifest=manifest,
        active_execution=active_execution,
    )


def get_verification_run_progress(
    workspace_root: str | Path,
    run_id: str,
    *,
    active_execution: dict[str, Any] | None = None,
    raise_on_missing: bool = True,
) -> dict[str, Any] | None:
    artifact_dir = verification_artifact_dir(workspace_root, run_id)
    if not artifact_dir.is_dir():
        raise VerificationArtifactError("VERIFICATION_RUN_NOT_FOUND", "未找到对应的验证运行记录。", 404)

    progress = _read_progress_file(artifact_dir)
    if progress:
        return progress

    active_run_id = str((active_execution or {}).get("run_id") or "").strip()
    if active_run_id == str(run_id).strip():
        active_progress = _read_progress_for_execution(workspace_root, active_execution or {})
        if active_progress:
            return active_progress

    result_payload = _try_read_json_file(artifact_dir / "result.json")
    if isinstance(result_payload, dict):
        total_steps = _count_total_steps(result_payload.get("lanes") or [])
        return {
            "run_id": run_id,
            "status": "completed",
            "phase": "finalizing",
            "current_lane": "",
            "current_step_id": "",
            "current_step_name": "",
            "completed_steps": total_steps,
            "total_steps": total_steps,
            "started_at": _extract_started_at(result_payload, artifact_dir),
            "updated_at": _format_file_timestamp(artifact_dir / "result.json"),
            "last_completed_step_id": _extract_last_completed_step_id(result_payload.get("lanes") or []),
            "real_e2e_status": str(((result_payload.get("real_e2e") or {}).get("status")) or ""),
        }

    if raise_on_missing:
        raise VerificationArtifactError("VERIFICATION_ARTIFACT_NOT_FOUND", "未找到对应的运行进度。", 404)
    return None


def get_verification_report_path(workspace_root: str | Path, run_id: str) -> Path:
    artifact_dir = verification_artifact_dir(workspace_root, run_id)
    report_path = artifact_dir / "report.md"
    if not report_path.is_file():
        raise VerificationArtifactError("VERIFICATION_ARTIFACT_NOT_FOUND", "未找到对应的验证报告。", 404)
    return report_path.resolve()


def get_verification_console_log_path(workspace_root: str | Path, run_id: str, stream: str) -> Path:
    artifact_dir = verification_artifact_dir(workspace_root, run_id)
    filename = STREAM_TO_CONSOLE_FILENAME.get(stream)
    if filename is None:
        raise VerificationArtifactError("VERIFICATION_LOG_NOT_FOUND", "未找到对应的日志流。", 404)
    path = artifact_dir / filename
    if not path.is_file():
        raise VerificationArtifactError("VERIFICATION_LOG_NOT_FOUND", "未找到对应的控制台日志。", 404)
    return path.resolve()


def get_verification_step_log_path(workspace_root: str | Path, run_id: str, step_id: str, stream: str) -> Path:
    detail = get_verification_run_detail(workspace_root, run_id)
    target_key = STREAM_TO_STEP_PATH_KEY.get(stream)
    if target_key is None:
        raise VerificationArtifactError("VERIFICATION_LOG_NOT_FOUND", "未找到对应的日志流。", 404)

    for lane in detail.get("lanes") or []:
        for step in lane.get("steps") or []:
            if str(step.get("id") or "").strip() != str(step_id).strip():
                continue
            path_value = str(step.get(target_key) or "").strip()
            if not path_value:
                break
            resolved = _normalize_artifact_path(verification_artifact_dir(workspace_root, run_id), path_value)
            if not resolved.is_file():
                break
            return resolved

    raise VerificationArtifactError("VERIFICATION_LOG_NOT_FOUND", "未找到对应步骤的日志文件。", 404)


def get_verification_console_log_payload(
    workspace_root: str | Path,
    run_id: str,
    stream: str,
    *,
    tail_lines: int = LOG_TAIL_DEFAULT_LINES,
) -> dict[str, Any]:
    return _read_log_payload(get_verification_console_log_path(workspace_root, run_id, stream), stream=stream, tail_lines=tail_lines)


def get_verification_step_log_payload(
    workspace_root: str | Path,
    run_id: str,
    step_id: str,
    stream: str,
    *,
    tail_lines: int = LOG_TAIL_DEFAULT_LINES,
) -> dict[str, Any]:
    payload = _read_log_payload(get_verification_step_log_path(workspace_root, run_id, step_id, stream), stream=stream, tail_lines=tail_lines)
    payload["step_id"] = step_id
    return payload


def write_verification_request_metadata(artifact_dir: str | Path, metadata: dict[str, Any]) -> Path:
    path = Path(artifact_dir).resolve() / "request.json"
    _write_json_file(path, metadata)
    return path


def ensure_cancelled_result(
    workspace_root: str | Path,
    run_id: str,
    *,
    reason: str,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_dir = verification_artifact_dir(workspace_root, run_id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    result_path = artifact_dir / "result.json"
    existing = _try_read_json_file(result_path) or {}
    payload = dict(existing)
    payload.update(
        {
            "classification": "cancelled",
            "passed": False,
            "workspace_root": str(Path(workspace_root).resolve()),
            "artifact_dir": str(artifact_dir.resolve()),
            "next_action": "rerun_after_cancel",
            "failure_summary": str(payload.get("failure_summary") or reason),
            "minimal_repro": str(payload.get("minimal_repro") or "重新运行正式验证脚本。"),
            "blocking_step_ids": list(payload.get("blocking_step_ids") or []),
            "failure_fingerprint": "cancelled",
        }
    )
    payload.setdefault("preflight", _try_read_json_file(artifact_dir / "preflight.json"))
    payload.setdefault("lanes", _read_lane_files(artifact_dir))
    payload.setdefault(
        "local_decision",
        {
            "should_run_real_e2e": False,
            "classification": "cancelled",
            "blocking_lane_names": [],
            "blocking_step_ids": [],
            "reason": "stop_requested",
        },
    )
    real_e2e = dict(payload.get("real_e2e") or {})
    real_e2e["status"] = "skipped_due_to_cancel"
    real_e2e.setdefault("classification", "")
    real_e2e.setdefault("artifact_dir", str((artifact_dir / "real-e2e").resolve()))
    real_e2e["reason"] = reason
    payload["real_e2e"] = real_e2e
    _write_json_file(result_path, payload)
    (artifact_dir / "report.md").write_text(
        "# Multi-Agent Test Report\n\n- Classification: `cancelled`\n- Next action: `rerun_after_cancel`\n- Failure summary: 已取消当前验证运行。\n",
        encoding="utf-8",
    )
    _ensure_manifest(artifact_dir, result_payload=payload, force_rewrite=True)
    return payload


def _summarize_verification_run(artifact_dir: Path) -> dict[str, Any]:
    result_path = artifact_dir / "result.json"
    report_path = artifact_dir / "report.md"
    progress = _read_progress_file(artifact_dir)
    manifest = _ensure_manifest(artifact_dir)
    summary = {
        "run_id": artifact_dir.name,
        "status": "incomplete",
        "started_at": "",
        "finished_at": "",
        "classification": "incomplete",
        "next_action": "",
        "failure_summary": "验证产物尚不完整。",
        "real_e2e_status": "",
        "has_report": report_path.is_file(),
        "has_result": result_path.is_file(),
        "artifact_dir": str(artifact_dir.resolve()),
        "progress": progress,
        "failure_fingerprint": str((manifest or {}).get("failure_fingerprint") or ""),
        "rerun_of_run_id": str((manifest or {}).get("rerun_of_run_id") or ""),
    }
    if not result_path.is_file():
        summary["started_at"] = _read_preflight_checked_at(artifact_dir)
        summary["finished_at"] = _format_file_timestamp(artifact_dir)
        return summary

    try:
        result_payload = _read_json_file(result_path)
    except json.JSONDecodeError:
        summary["started_at"] = _read_preflight_checked_at(artifact_dir)
        summary["finished_at"] = _format_file_timestamp(result_path)
        summary["failure_summary"] = "验证结果文件无法解析。"
        return summary

    summary.update(
        {
            "status": "completed",
            "started_at": _extract_started_at(result_payload, artifact_dir),
            "finished_at": _format_file_timestamp(result_path),
            "classification": str(result_payload.get("classification") or "pass"),
            "next_action": str(result_payload.get("next_action") or ""),
            "failure_summary": str(result_payload.get("failure_summary") or ""),
            "real_e2e_status": str(((result_payload.get("real_e2e") or {}).get("status")) or ""),
            "failure_fingerprint": str(
                result_payload.get("failure_fingerprint")
                or (manifest or {}).get("failure_fingerprint")
                or _derive_failure_fingerprint(result_payload)
            ),
            "rerun_of_run_id": str(result_payload.get("rerun_of_run_id") or (manifest or {}).get("rerun_of_run_id") or ""),
        }
    )
    if summary["progress"] is None:
        total_steps = _count_total_steps(result_payload.get("lanes") or [])
        summary["progress"] = {
            "phase": "finalizing",
            "completed_steps": total_steps,
            "total_steps": total_steps,
            "updated_at": summary["finished_at"],
        }
    return summary


def _build_detail_from_result(
    run_id: str,
    artifact_dir: Path,
    result_payload: dict[str, Any],
    *,
    progress: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
    active_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result_path = artifact_dir / "result.json"
    detail = {
        "run_id": run_id,
        "status": _detail_status_from_execution(active_execution),
        "started_at": _extract_started_at(result_payload, artifact_dir),
        "finished_at": _extract_finished_at(active_execution, result_path),
        "classification": str(result_payload.get("classification") or ""),
        "next_action": str(result_payload.get("next_action") or ""),
        "failure_summary": str(result_payload.get("failure_summary") or ""),
        "blocking_step_ids": list(result_payload.get("blocking_step_ids") or []),
        "minimal_repro": str(result_payload.get("minimal_repro") or ""),
        "failure_fingerprint": str(
            result_payload.get("failure_fingerprint")
            or (manifest or {}).get("failure_fingerprint")
            or _derive_failure_fingerprint(result_payload)
        ),
        "rerun_of_run_id": str(result_payload.get("rerun_of_run_id") or (manifest or {}).get("rerun_of_run_id") or ""),
        "preflight": result_payload.get("preflight"),
        "local_decision": result_payload.get("local_decision"),
        "progress": progress,
        "lanes": _decorate_lanes_with_log_urls(run_id, result_payload.get("lanes") or [], artifact_dir),
        "real_e2e": dict(result_payload.get("real_e2e") or {}),
        "manifest": manifest or {},
        "artifacts": _build_artifact_payload(run_id, artifact_dir),
    }
    detail["real_e2e"].setdefault("status", "")
    return detail


def _build_incomplete_detail(
    run_id: str,
    artifact_dir: Path,
    *,
    progress: dict[str, Any] | None,
    manifest: dict[str, Any] | None,
    active_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = _detail_status_from_execution(active_execution)
    if status in {"starting", "running"}:
        summary = "验证仍在运行，结果尚未生成。"
    else:
        status = "incomplete"
        summary = "验证产物尚不完整。"
    return {
        "run_id": run_id,
        "status": status,
        "started_at": _read_preflight_checked_at(artifact_dir),
        "finished_at": _extract_finished_at(active_execution, artifact_dir),
        "classification": "",
        "next_action": "",
        "failure_summary": summary,
        "blocking_step_ids": [],
        "minimal_repro": "",
        "failure_fingerprint": str((manifest or {}).get("failure_fingerprint") or ""),
        "rerun_of_run_id": str((manifest or {}).get("rerun_of_run_id") or ""),
        "preflight": _try_read_json_file(artifact_dir / "preflight.json"),
        "local_decision": None,
        "progress": progress,
        "lanes": _decorate_lanes_with_log_urls(run_id, _read_lane_files(artifact_dir), artifact_dir),
        "real_e2e": {
            "status": "pending" if status in {"starting", "running"} else "",
            "classification": "",
            "artifact_dir": str((artifact_dir / "real-e2e").resolve()),
            "reason": "",
        },
        "manifest": manifest or {},
        "artifacts": _build_artifact_payload(run_id, artifact_dir),
    }


def _build_artifact_payload(run_id: str, artifact_dir: Path) -> dict[str, Any]:
    log_paths = verification_console_log_paths(artifact_dir)
    return {
        "artifact_dir": str(artifact_dir.resolve()),
        "result_path": str((artifact_dir / "result.json").resolve()),
        "report_path": str((artifact_dir / "report.md").resolve()),
        "progress_path": str((artifact_dir / "progress.json").resolve()),
        "manifest_path": str((artifact_dir / "manifest.json").resolve()),
        "real_e2e_result_path": str((artifact_dir / "real-e2e-result.json").resolve()),
        "console_stdout_path": str(log_paths["stdout"].resolve()),
        "console_stderr_path": str(log_paths["stderr"].resolve()),
        "report_url": f"/api/workbench/verification/runs/{run_id}/report",
        "progress_url": f"/api/workbench/verification/runs/{run_id}/progress",
        "console_stdout_url": f"/api/workbench/verification/runs/{run_id}/console/stdout",
        "console_stderr_url": f"/api/workbench/verification/runs/{run_id}/console/stderr",
    }


def _decorate_lanes_with_log_urls(run_id: str, lanes: list[dict[str, Any]], artifact_dir: Path) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for lane in lanes:
        lane_copy = dict(lane)
        steps = []
        for step in lane.get("steps") or []:
            step_copy = dict(step)
            step_id = str(step_copy.get("id") or "").strip()
            for stream, path_key in STREAM_TO_STEP_PATH_KEY.items():
                path_value = str(step_copy.get(path_key) or "").strip()
                url_key = f"{stream}_log_url"
                if step_id and path_value:
                    try:
                        _normalize_artifact_path(artifact_dir, path_value)
                    except VerificationArtifactError:
                        step_copy[url_key] = ""
                    else:
                        step_copy[url_key] = f"/api/workbench/verification/runs/{run_id}/steps/{step_id}/logs/{stream}"
                else:
                    step_copy[url_key] = ""
            steps.append(step_copy)
        lane_copy["steps"] = steps
        decorated.append(lane_copy)
    return decorated


def _read_lane_files(artifact_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for filename in ("backend-lane.json", "data-cli-lane.json", "frontend-lane.json"):
        payload = _try_read_json_file(artifact_dir / filename)
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _execution_to_summary(workspace_root: Path, execution: dict[str, Any]) -> dict[str, Any]:
    progress = _read_progress_for_execution(workspace_root, execution)
    return {
        "run_id": str(execution.get("run_id") or ""),
        "status": str(execution.get("status") or ""),
        "started_at": str(execution.get("started_at") or ""),
        "finished_at": str(execution.get("finished_at") or ""),
        "classification": "",
        "next_action": "",
        "failure_summary": str(execution.get("last_error") or ("验证正在运行中。" if execution.get("status") in {"starting", "running"} else "")),
        "real_e2e_status": str((progress or {}).get("real_e2e_status") or ""),
        "has_report": Path(str(execution.get("report_path") or "")).is_file(),
        "has_result": Path(str(execution.get("result_path") or "")).is_file(),
        "artifact_dir": str(execution.get("artifact_dir") or ""),
        "progress": progress,
        "failure_fingerprint": "",
        "rerun_of_run_id": str(execution.get("rerun_of_run_id") or ""),
    }


def _group_history_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        fingerprint = str(item.get("failure_fingerprint") or "").strip()
        if fingerprint:
            groups.setdefault(fingerprint, []).append(item)

    aggregated: list[dict[str, Any]] = []
    for fingerprint, group_items in groups.items():
        ordered = sorted(group_items, key=_run_sort_key, reverse=True)
        latest = ordered[0]
        latest_time = str(latest.get("finished_at") or latest.get("started_at") or "")
        recovered_by_later_pass = any(
            str(item.get("classification") or "") == "pass"
            and str(item.get("finished_at") or item.get("started_at") or "") > latest_time
            for item in items
        )
        aggregated.append(
            {
                "failure_fingerprint": fingerprint,
                "run_count": len(group_items),
                "latest_run_id": str(latest.get("run_id") or ""),
                "latest_classification": str(latest.get("classification") or ""),
                "latest_finished_at": latest_time,
                "latest_next_action": str(latest.get("next_action") or ""),
                "recovered_by_later_pass": recovered_by_later_pass,
            }
        )
    aggregated.sort(key=lambda item: (item.get("latest_finished_at") or "", item.get("latest_run_id") or ""), reverse=True)
    return aggregated


def _run_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    if item.get("status") in {"starting", "running"}:
        return (2, str(item.get("started_at") or ""))
    if item.get("status") == "completed":
        return (1, str(item.get("finished_at") or item.get("started_at") or ""))
    return (0, str(item.get("finished_at") or item.get("started_at") or ""))


def _read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _try_read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return _read_json_file(path)
    except json.JSONDecodeError:
        return None


def _read_progress_file(artifact_dir: Path) -> dict[str, Any] | None:
    payload = _try_read_json_file(artifact_dir / "progress.json")
    return dict(payload) if isinstance(payload, dict) else None


def _read_progress_for_execution(workspace_root: str | Path, execution: dict[str, Any]) -> dict[str, Any] | None:
    embedded = execution.get("progress")
    if isinstance(embedded, dict):
        return dict(embedded)
    run_id = str(execution.get("run_id") or "").strip()
    return _read_progress_file(verification_artifact_dir(workspace_root, run_id)) if run_id else None


def _read_preflight_checked_at(artifact_dir: Path) -> str:
    payload = _try_read_json_file(artifact_dir / "preflight.json")
    return str(payload.get("checked_at") or "") if isinstance(payload, dict) else ""


def _extract_started_at(result_payload: dict[str, Any], artifact_dir: Path) -> str:
    preflight = result_payload.get("preflight")
    if isinstance(preflight, dict):
        checked_at = str(preflight.get("checked_at") or "").strip()
        if checked_at:
            return checked_at
    return _read_preflight_checked_at(artifact_dir)


def _extract_finished_at(active_execution: dict[str, Any] | None, path: Path) -> str:
    finished_at = str((active_execution or {}).get("finished_at") or "").strip()
    return finished_at or _format_file_timestamp(path)


def _detail_status_from_execution(active_execution: dict[str, Any] | None) -> str:
    status = str((active_execution or {}).get("status") or "").strip()
    return status or "completed"


def _format_file_timestamp(path: Path) -> str:
    try:
        timestamp = path.stat().st_mtime
    except FileNotFoundError:
        return ""
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _normalize_artifact_path(artifact_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    resolved = path.resolve() if path.is_absolute() else (artifact_dir / path).resolve()
    try:
        resolved.relative_to(artifact_dir.resolve())
    except ValueError as exc:
        raise VerificationArtifactError("VERIFICATION_LOG_NOT_FOUND", "日志路径超出当前验证产物目录。", 404) from exc
    return resolved


def _read_log_payload(path: Path, *, stream: str, tail_lines: int) -> dict[str, Any]:
    if not path.is_file():
        raise VerificationArtifactError("VERIFICATION_LOG_NOT_FOUND", "未找到对应的验证日志。", 404)
    normalized_tail = max(1, min(int(tail_lines or LOG_TAIL_DEFAULT_LINES), LOG_TAIL_MAX_LINES))
    content = path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    truncated = len(lines) > normalized_tail
    trimmed = "\n".join(lines[-normalized_tail:]) if truncated else content
    return {
        "stream": stream,
        "content": trimmed,
        "truncated": truncated,
        "total_bytes": path.stat().st_size,
        "last_modified_at": _format_file_timestamp(path),
    }


def _count_total_steps(lanes: list[dict[str, Any]]) -> int:
    return sum(len(lane.get("steps") or []) for lane in lanes)


def _extract_last_completed_step_id(lanes: list[dict[str, Any]]) -> str:
    completed: list[dict[str, Any]] = []
    for lane in lanes:
        for step in lane.get("steps") or []:
            if step.get("passed"):
                completed.append(step)
    completed.sort(key=lambda step: str(step.get("finished_at") or ""))
    return str(completed[-1].get("id") or "") if completed else ""


def _derive_failure_fingerprint(result_payload: dict[str, Any]) -> str:
    classification = str(result_payload.get("classification") or "").strip()
    if classification == "cancelled":
        return "cancelled"
    if classification == "environment_blocked":
        preflight = result_payload.get("preflight") or {}
        issues = [str(item.get("name") or "").strip() for item in preflight.get("issues") or [] if str(item.get("name") or "").strip()]
        if issues:
            return f"environment:{'|'.join(sorted(set(issues)))}"
    if classification in {"local_blocker", "local_regression"}:
        for lane in result_payload.get("lanes") or []:
            for step in lane.get("steps") or []:
                if step.get("passed") is False:
                    return f"{step.get('id')}:{step.get('failure_kind') or 'unknown'}"
    if classification in {"mainline_failure", "page_regression", "readonly_audit_failure"}:
        reason = str((result_payload.get("real_e2e") or {}).get("reason") or "").strip()
        return f"{classification}:{reason}" if reason else classification
    return classification or "unknown"


def _ensure_manifest(
    artifact_dir: Path,
    *,
    result_payload: dict[str, Any] | None = None,
    force_rewrite: bool = False,
) -> dict[str, Any] | None:
    manifest_path = artifact_dir / "manifest.json"
    if not force_rewrite:
        payload = _try_read_json_file(manifest_path)
        if isinstance(payload, dict):
            return payload

    payload = result_payload if result_payload is not None else _try_read_json_file(artifact_dir / "result.json")
    request_payload = _try_read_json_file(artifact_dir / "request.json") or {}
    if not isinstance(payload, dict) and not request_payload:
        return None

    manifest = {
        "manifest_version": 1,
        "run_id": artifact_dir.name,
        "classification": str((payload or {}).get("classification") or "incomplete"),
        "next_action": str((payload or {}).get("next_action") or ""),
        "failure_fingerprint": str((payload or {}).get("failure_fingerprint") or (_derive_failure_fingerprint(payload) if isinstance(payload, dict) else "")),
        "rerun_of_run_id": str((payload or {}).get("rerun_of_run_id") or request_payload.get("rerun_of_run_id") or ""),
        "artifact_paths": {
            "result": str((artifact_dir / "result.json").resolve()),
            "report": str((artifact_dir / "report.md").resolve()),
            "progress": str((artifact_dir / "progress.json").resolve()),
            "manifest": str(manifest_path.resolve()),
        },
    }
    _write_json_file(manifest_path, manifest)
    return manifest
