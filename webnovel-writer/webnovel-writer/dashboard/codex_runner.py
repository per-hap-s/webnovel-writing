from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .llm_runner import StepResult, extract_json_payload_details

STEP_ERROR_MESSAGES = {
    "CODEX_CLI_NOT_FOUND": "未找到 Codex CLI 可执行文件。",
    "CODEX_TIMEOUT": "Codex 步骤执行超时。",
    "CODEX_EXEC_ERROR": "Codex CLI 调用失败。",
    "INVALID_STEP_OUTPUT": "Codex 输出中不包含有效 JSON 对象。",
    "CODEX_AUTH_REQUIRED": "Codex CLI 尚未登录。",
    "CODEX_STEP_FAILED": "Codex 步骤执行失败。",
}


class CodexRunner:
    """Thin non-interactive wrapper around Codex CLI."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.binary = os.environ.get("WEBNOVEL_CODEX_BIN", "codex")
        self.timeout_ms = int(os.environ.get("WEBNOVEL_CODEX_TIMEOUT_MS", "120000"))

    def probe(self) -> Dict[str, Any]:
        exists = shutil.which(self.binary) is not None
        version = None
        if exists:
            try:
                completed = subprocess.run(
                    [self.binary, "--version"],
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                version = (completed.stdout or completed.stderr).strip() or None
            except OSError:
                exists = False
        return {"binary": self.binary, "installed": exists, "version": version}

    def run(self, step_spec: Dict[str, Any], workspace: Path, prompt_bundle: Dict[str, Any]) -> StepResult:
        runs_root = self.project_root / ".webnovel" / "observability" / "codex-runs"
        run_dir = runs_root / f"{prompt_bundle['task_id']}-{step_spec['name']}"
        run_dir.mkdir(parents=True, exist_ok=True)

        prompt_file = run_dir / "prompt.md"
        bundle_file = run_dir / "prompt-bundle.json"
        output_file = run_dir / "raw-output.txt"

        prompt_text = self._build_prompt(step_spec, prompt_bundle)
        prompt_file.write_text(prompt_text, encoding="utf-8")
        bundle_file.write_text(json.dumps(prompt_bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        if shutil.which(self.binary) is None:
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=127,
                timing_ms=0,
                stdout="",
                stderr="未找到 Codex CLI",
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "CODEX_CLI_NOT_FOUND", "message": f"缺少 CLI 可执行文件：{self.binary}"},
            )

        started_at = time.perf_counter()
        try:
            completed = subprocess.run(
                [self.binary, "exec", prompt_text],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=max(1, self.timeout_ms // 1000),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            timing_ms = int((time.perf_counter() - started_at) * 1000)
            output_file.write_text((exc.stdout or "") + "\n" + (exc.stderr or ""), encoding="utf-8")
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=124,
                timing_ms=timing_ms,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "CODEX_TIMEOUT", "message": f"步骤执行超时：{self.timeout_ms} 毫秒"},
            )
        except OSError as exc:
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=126,
                timing_ms=0,
                stdout="",
                stderr=str(exc),
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "CODEX_EXEC_ERROR", "message": str(exc)},
            )

        timing_ms = int((time.perf_counter() - started_at) * 1000)
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        output_file.write_text(stdout + ("\n" if stdout and stderr else "") + stderr, encoding="utf-8")

        extraction = extract_json_payload_details(stdout, required_keys=step_spec.get("required_output_keys"))
        metadata = {
            "attempt": 1,
            "retry_count": 0,
            "parse_stage": extraction.stage,
            "json_extraction_recovered": extraction.recovered,
            "missing_required_keys": list(extraction.missing_required_keys),
        }
        structured_output = extraction.payload
        error = None
        success = completed.returncode == 0
        if not success:
            error = self._map_error(stderr or stdout)
        elif structured_output is None:
            success = False
            error = {
                "code": "INVALID_STEP_OUTPUT",
                "message": STEP_ERROR_MESSAGES["INVALID_STEP_OUTPUT"],
                "attempt": 1,
                "retryable": False,
                "parse_stage": extraction.stage,
                "raw_output_present": bool(stdout.strip()),
                "missing_required_keys": list(extraction.missing_required_keys),
                "details": {
                    "parse_stage": extraction.stage,
                    "raw_output_present": bool(stdout.strip()),
                    "missing_required_keys": list(extraction.missing_required_keys),
                },
            }

        return StepResult(
            step_name=step_spec["name"],
            success=success,
            return_code=int(completed.returncode),
            timing_ms=timing_ms,
            stdout=stdout,
            stderr=stderr,
            structured_output=structured_output,
            prompt_file=str(prompt_file),
            output_file=str(output_file),
            error=self._normalize_error(error),
            metadata=metadata,
        )

    def _build_prompt(self, step_spec: Dict[str, Any], prompt_bundle: Dict[str, Any]) -> str:
        references = prompt_bundle.get("references", [])
        references_block = "\n".join(f"- {item}" for item in references) or "- None"
        payload = json.dumps(prompt_bundle.get("input", {}), ensure_ascii=False, indent=2)
        schema_hint = json.dumps(step_spec.get("output_schema", {}), ensure_ascii=False, indent=2)
        instructions = step_spec.get("instructions", "").strip()
        return (
            f"# Task\n{instructions}\n\n"
            f"# References\n{references_block}\n\n"
            f"# Input Payload\n```json\n{payload}\n```\n\n"
            f"# Output Contract\nReturn exactly one JSON object matching this shape:\n```json\n{schema_hint}\n```\n"
        )

    def _map_error(self, raw: str) -> Dict[str, str]:
        text = (raw or "").lower()
        if "login" in text or "auth" in text:
            return {"code": "CODEX_AUTH_REQUIRED", "message": "Codex CLI 尚未登录。"}
        if "not found" in text:
            return {"code": "CODEX_CLI_NOT_FOUND", "message": "未找到 Codex CLI 可执行文件。"}
        return {"code": "CODEX_STEP_FAILED", "message": "Codex 步骤执行失败。"}

    def _normalize_error(self, error: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if not error:
            return error
        normalized = dict(error)
        code = str(normalized.get("code") or "").strip()
        if code in STEP_ERROR_MESSAGES:
            normalized["message"] = STEP_ERROR_MESSAGES[code]
        return normalized
