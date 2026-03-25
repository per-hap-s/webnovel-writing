from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import subprocess
from typing import Any


ARTIFACT_RELATIVE_ROOT = Path('output') / 'verification' / 'multi-agent-test'
CONSOLE_STDOUT_FILENAME = '_dashboard-console.stdout.log'
CONSOLE_STDERR_FILENAME = '_dashboard-console.stderr.log'
STREAM_TO_STEP_PATH_KEY = {
    'stdout': 'stdout_log_path',
    'stderr': 'stderr_log_path',
    'combined': 'combined_log_path',
}
STREAM_TO_CONSOLE_FILENAME = {
    'stdout': CONSOLE_STDOUT_FILENAME,
    'stderr': CONSOLE_STDERR_FILENAME,
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


def verification_console_log_paths(artifact_dir: str | Path) -> dict[str, Path]:
    root = Path(artifact_dir).resolve()
    return {
        'stdout': root / CONSOLE_STDOUT_FILENAME,
        'stderr': root / CONSOLE_STDERR_FILENAME,
    }


def generate_verification_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    return f'{timestamp}-{secrets.token_hex(3)}'


def start_multi_agent_test_process(workspace_root: str | Path, artifact_dir: str | Path, run_id: str) -> subprocess.Popen:
    workspace_root_path = Path(workspace_root).resolve()
    artifact_dir_path = Path(artifact_dir).resolve()
    artifact_dir_path.mkdir(parents=True, exist_ok=True)
    log_paths = verification_console_log_paths(artifact_dir_path)
    script_path = workspace_root_path / 'tools' / 'Tests' / 'Run-Webnovel-MultiAgentTest.ps1'
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    stdout_handle = log_paths['stdout'].open('w', encoding='utf-8')
    stderr_handle = log_paths['stderr'].open('w', encoding='utf-8')
    try:
        return subprocess.Popen(
            [
                'powershell.exe',
                '-NoProfile',
                '-ExecutionPolicy',
                'Bypass',
                '-File',
                str(script_path),
                '-WorkspaceRoot',
                str(workspace_root_path),
                '-OutputRoot',
                str(artifact_dir_path),
                '-RunId',
                str(run_id),
            ],
            cwd=str(workspace_root_path),
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=creationflags,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()


def build_verification_overview(workspace_root: str | Path, *, limit: int = 10, active_execution: dict[str, Any] | None = None) -> dict[str, Any]:
    workspace_root_path = Path(workspace_root).resolve()
    runs = list_verification_runs(workspace_root_path, limit=limit, active_execution=active_execution)
    return {
        'workspace_root': str(workspace_root_path),
        'active_execution': dict(active_execution) if active_execution else None,
        'runs': runs,
    }


def list_verification_runs(workspace_root: str | Path, *, limit: int = 10, active_execution: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    artifact_root = verification_artifact_root(workspace_root)
    if not artifact_root.is_dir():
        runs: list[dict[str, Any]] = []
    else:
        runs = [_summarize_verification_run(path) for path in artifact_root.iterdir() if path.is_dir()]
        runs.sort(key=_run_sort_key, reverse=True)

    if active_execution:
        active_summary = _execution_to_summary(active_execution)
        existing_index = next((index for index, item in enumerate(runs) if item.get('run_id') == active_summary['run_id']), None)
        if existing_index is None:
            runs.insert(0, active_summary)
        else:
            merged = dict(runs[existing_index])
            merged.update({key: value for key, value in active_summary.items() if value not in (None, '', [])})
            runs[existing_index] = merged
            runs.sort(key=_run_sort_key, reverse=True)

    return runs[:limit]


def get_verification_run_detail(workspace_root: str | Path, run_id: str, *, active_execution: dict[str, Any] | None = None) -> dict[str, Any]:
    artifact_dir = verification_artifact_dir(workspace_root, run_id)
    if not artifact_dir.is_dir():
        raise VerificationArtifactError('VERIFICATION_RUN_NOT_FOUND', '未找到对应的验证运行记录。', 404)

    result_path = artifact_dir / 'result.json'
    if result_path.is_file():
        try:
            result_payload = _read_json_file(result_path)
        except json.JSONDecodeError as exc:
            raise VerificationArtifactError('VERIFICATION_RESULT_INVALID', '验证结果文件损坏，无法解析。', 409) from exc
        detail = _build_detail_from_result(run_id, artifact_dir, result_payload, active_execution=active_execution)
    else:
        detail = _build_incomplete_detail(run_id, artifact_dir, active_execution=active_execution)

    return detail


def get_verification_report_path(workspace_root: str | Path, run_id: str) -> Path:
    artifact_dir = verification_artifact_dir(workspace_root, run_id)
    report_path = artifact_dir / 'report.md'
    if not report_path.is_file():
        raise VerificationArtifactError('VERIFICATION_ARTIFACT_NOT_FOUND', '未找到验证报告。', 404)
    return report_path.resolve()


def get_verification_console_log_path(workspace_root: str | Path, run_id: str, stream: str) -> Path:
    artifact_dir = verification_artifact_dir(workspace_root, run_id)
    filename = STREAM_TO_CONSOLE_FILENAME.get(stream)
    if filename is None:
        raise VerificationArtifactError('VERIFICATION_LOG_NOT_FOUND', '未找到对应的日志流。', 404)
    path = artifact_dir / filename
    if not path.is_file():
        raise VerificationArtifactError('VERIFICATION_LOG_NOT_FOUND', '未找到对应的控制台日志。', 404)
    return path.resolve()


def get_verification_step_log_path(workspace_root: str | Path, run_id: str, step_id: str, stream: str) -> Path:
    detail = get_verification_run_detail(workspace_root, run_id)
    target_key = STREAM_TO_STEP_PATH_KEY.get(stream)
    if target_key is None:
        raise VerificationArtifactError('VERIFICATION_LOG_NOT_FOUND', '未找到对应的日志流。', 404)

    for lane in detail.get('lanes') or []:
        for step in lane.get('steps') or []:
            if str(step.get('id') or '').strip() != str(step_id).strip():
                continue
            path_value = str(step.get(target_key) or '').strip()
            if not path_value:
                break
            resolved = _normalize_artifact_path(verification_artifact_dir(workspace_root, run_id), path_value)
            if not resolved.is_file():
                break
            return resolved

    raise VerificationArtifactError('VERIFICATION_LOG_NOT_FOUND', '未找到对应步骤的日志文件。', 404)


def _summarize_verification_run(artifact_dir: Path) -> dict[str, Any]:
    result_path = artifact_dir / 'result.json'
    report_path = artifact_dir / 'report.md'
    summary = {
        'run_id': artifact_dir.name,
        'status': 'incomplete',
        'started_at': '',
        'finished_at': '',
        'classification': 'incomplete',
        'next_action': '',
        'failure_summary': '验证产物尚不完整。',
        'real_e2e_status': '',
        'has_report': report_path.is_file(),
        'has_result': result_path.is_file(),
        'artifact_dir': str(artifact_dir.resolve()),
    }
    if not result_path.is_file():
        summary['started_at'] = _read_preflight_checked_at(artifact_dir)
        summary['finished_at'] = _format_file_timestamp(artifact_dir)
        return summary

    try:
        result_payload = _read_json_file(result_path)
    except json.JSONDecodeError:
        summary['started_at'] = _read_preflight_checked_at(artifact_dir)
        summary['finished_at'] = _format_file_timestamp(result_path)
        summary['failure_summary'] = '验证结果文件无法解析。'
        return summary

    summary.update(
        {
            'status': 'completed',
            'started_at': _extract_started_at(result_payload, artifact_dir),
            'finished_at': _format_file_timestamp(result_path),
            'classification': str(result_payload.get('classification') or 'pass'),
            'next_action': str(result_payload.get('next_action') or ''),
            'failure_summary': str(result_payload.get('failure_summary') or ''),
            'real_e2e_status': str(((result_payload.get('real_e2e') or {}).get('status')) or ''),
        }
    )
    return summary


def _build_detail_from_result(
    run_id: str,
    artifact_dir: Path,
    result_payload: dict[str, Any],
    *,
    active_execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result_path = artifact_dir / 'result.json'
    detail = {
        'run_id': run_id,
        'status': _detail_status_from_execution(active_execution),
        'started_at': _extract_started_at(result_payload, artifact_dir),
        'finished_at': _extract_finished_at(active_execution, result_path),
        'classification': str(result_payload.get('classification') or ''),
        'next_action': str(result_payload.get('next_action') or ''),
        'failure_summary': str(result_payload.get('failure_summary') or ''),
        'blocking_step_ids': list(result_payload.get('blocking_step_ids') or []),
        'minimal_repro': str(result_payload.get('minimal_repro') or ''),
        'preflight': result_payload.get('preflight'),
        'local_decision': result_payload.get('local_decision'),
        'lanes': _decorate_lanes_with_log_urls(run_id, result_payload.get('lanes') or [], artifact_dir),
        'real_e2e': dict(result_payload.get('real_e2e') or {}),
        'artifacts': _build_artifact_payload(run_id, artifact_dir),
    }
    detail['real_e2e'].setdefault('status', '')
    return detail


def _build_incomplete_detail(run_id: str, artifact_dir: Path, *, active_execution: dict[str, Any] | None = None) -> dict[str, Any]:
    status = _detail_status_from_execution(active_execution)
    if status in {'starting', 'running'}:
        summary = '验证仍在运行，结果尚未生成。'
    else:
        status = 'incomplete'
        summary = '验证产物尚不完整。'
    return {
        'run_id': run_id,
        'status': status,
        'started_at': _read_preflight_checked_at(artifact_dir),
        'finished_at': _extract_finished_at(active_execution, artifact_dir),
        'classification': '',
        'next_action': '',
        'failure_summary': summary,
        'blocking_step_ids': [],
        'minimal_repro': '',
        'preflight': _try_read_json_file(artifact_dir / 'preflight.json'),
        'local_decision': None,
        'lanes': _decorate_lanes_with_log_urls(run_id, _read_lane_files(artifact_dir), artifact_dir),
        'real_e2e': {
            'status': 'pending' if status in {'starting', 'running'} else '',
            'classification': '',
            'artifact_dir': str((artifact_dir / 'real-e2e').resolve()),
            'reason': '',
        },
        'artifacts': _build_artifact_payload(run_id, artifact_dir),
    }


def _build_artifact_payload(run_id: str, artifact_dir: Path) -> dict[str, Any]:
    log_paths = verification_console_log_paths(artifact_dir)
    return {
        'artifact_dir': str(artifact_dir.resolve()),
        'result_path': str((artifact_dir / 'result.json').resolve()),
        'report_path': str((artifact_dir / 'report.md').resolve()),
        'real_e2e_result_path': str((artifact_dir / 'real-e2e-result.json').resolve()),
        'console_stdout_path': str(log_paths['stdout'].resolve()),
        'console_stderr_path': str(log_paths['stderr'].resolve()),
        'report_url': f'/api/workbench/verification/runs/{run_id}/report',
        'console_stdout_url': f'/api/workbench/verification/runs/{run_id}/console/stdout',
        'console_stderr_url': f'/api/workbench/verification/runs/{run_id}/console/stderr',
    }


def _decorate_lanes_with_log_urls(run_id: str, lanes: list[dict[str, Any]], artifact_dir: Path) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for lane in lanes:
        lane_copy = dict(lane)
        steps = []
        for step in lane.get('steps') or []:
            step_copy = dict(step)
            step_id = str(step_copy.get('id') or '').strip()
            for stream, path_key in STREAM_TO_STEP_PATH_KEY.items():
                path_value = str(step_copy.get(path_key) or '').strip()
                url_key = f'{stream}_log_url'
                if step_id and path_value:
                    try:
                        _normalize_artifact_path(artifact_dir, path_value)
                    except VerificationArtifactError:
                        step_copy[url_key] = ''
                    else:
                        step_copy[url_key] = f'/api/workbench/verification/runs/{run_id}/steps/{step_id}/logs/{stream}'
                else:
                    step_copy[url_key] = ''
            steps.append(step_copy)
        lane_copy['steps'] = steps
        decorated.append(lane_copy)
    return decorated


def _read_lane_files(artifact_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for filename in ('backend-lane.json', 'data-cli-lane.json', 'frontend-lane.json'):
        payload = _try_read_json_file(artifact_dir / filename)
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _execution_to_summary(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        'run_id': str(execution.get('run_id') or ''),
        'status': str(execution.get('status') or ''),
        'started_at': str(execution.get('started_at') or ''),
        'finished_at': str(execution.get('finished_at') or ''),
        'classification': '',
        'next_action': '',
        'failure_summary': str(execution.get('last_error') or ('验证正在运行中。' if execution.get('status') in {'starting', 'running'} else '')),
        'real_e2e_status': '',
        'has_report': Path(str(execution.get('report_path') or '')).is_file(),
        'has_result': Path(str(execution.get('result_path') or '')).is_file(),
        'artifact_dir': str(execution.get('artifact_dir') or ''),
    }


def _run_sort_key(item: dict[str, Any]) -> tuple[int, str]:
    if item.get('status') in {'starting', 'running'}:
        return (2, str(item.get('started_at') or ''))
    if item.get('status') == 'completed':
        return (1, str(item.get('finished_at') or item.get('started_at') or ''))
    return (0, str(item.get('finished_at') or item.get('started_at') or ''))


def _read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def _try_read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return _read_json_file(path)
    except json.JSONDecodeError:
        return None


def _read_preflight_checked_at(artifact_dir: Path) -> str:
    payload = _try_read_json_file(artifact_dir / 'preflight.json')
    if isinstance(payload, dict):
        return str(payload.get('checked_at') or '')
    return ''


def _extract_started_at(result_payload: dict[str, Any], artifact_dir: Path) -> str:
    preflight = result_payload.get('preflight')
    if isinstance(preflight, dict):
        checked_at = str(preflight.get('checked_at') or '').strip()
        if checked_at:
            return checked_at
    return _read_preflight_checked_at(artifact_dir)


def _extract_finished_at(active_execution: dict[str, Any] | None, path: Path) -> str:
    finished_at = str((active_execution or {}).get('finished_at') or '').strip()
    if finished_at:
        return finished_at
    return _format_file_timestamp(path)


def _detail_status_from_execution(active_execution: dict[str, Any] | None) -> str:
    status = str((active_execution or {}).get('status') or '').strip()
    return status or 'completed'


def _format_file_timestamp(path: Path) -> str:
    target = path if path.is_file() else path
    try:
        timestamp = target.stat().st_mtime
    except FileNotFoundError:
        return ''
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _normalize_artifact_path(artifact_dir: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    resolved = path.resolve() if path.is_absolute() else (artifact_dir / path).resolve()
    artifact_root = artifact_dir.resolve()
    try:
        resolved.relative_to(artifact_root)
    except ValueError as exc:
        raise VerificationArtifactError('VERIFICATION_LOG_NOT_FOUND', '日志路径超出当前验证产物目录。', 404) from exc
    return resolved
