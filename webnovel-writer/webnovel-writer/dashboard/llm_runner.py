from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Union
from urllib import error as urlerror
from urllib import request as urlrequest

from scripts.data_modules.config import load_runtime_env

STEP_ERROR_MESSAGES = {
    "LLM_NOT_CONFIGURED": "请先配置写作模型的 API Key 和模型名称。",
    "LLM_HTTP_ERROR": "写作模型接口请求失败。",
    "LLM_REQUEST_FAILED": "写作模型接口连接失败。",
    "LLM_RESPONSE_INVALID": "写作模型返回的数据格式无效。",
    "INVALID_STEP_OUTPUT": "步骤输出中不包含有效 JSON 对象。",
    "CODEX_CLI_NOT_FOUND": "未找到 Codex CLI 可执行文件。",
    "CODEX_AUTH_REQUIRED": "Codex CLI 尚未登录。",
    "CODEX_TIMEOUT": "Codex 步骤执行超时。",
    "CODEX_EXEC_ERROR": "Codex CLI 调用失败。",
    "CODEX_STEP_FAILED": "Codex 步骤执行失败。",
}


def _ensure_str(data: Union[str, bytes, None]) -> str:
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def extract_json_payload(raw: str) -> Optional[Dict[str, Any]]:
    raw = (raw or "").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```json\s*(\{.*?\})\s*```", raw, flags=re.DOTALL)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


@dataclass
class StepResult:
    step_name: str
    success: bool
    return_code: int
    timing_ms: int
    stdout: str
    stderr: str
    structured_output: Optional[Dict[str, Any]]
    prompt_file: str
    output_file: str
    error: Optional[Dict[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_name": self.step_name,
            "success": self.success,
            "return_code": self.return_code,
            "timing_ms": self.timing_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "structured_output": self.structured_output,
            "prompt_file": self.prompt_file,
            "output_file": self.output_file,
            "error": self.error,
        }


class LLMRunner:
    runs_dirname = "llm-runs"

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        load_runtime_env(self.project_root)
        self.timeout_ms = int(os.environ.get("WEBNOVEL_LLM_TIMEOUT_MS", "120000"))
        self.health_ttl_seconds = int(os.environ.get("WEBNOVEL_LLM_HEALTH_TTL_SECONDS", "30"))
        self.health_timeout_seconds = int(os.environ.get("WEBNOVEL_LLM_HEALTH_TIMEOUT_SECONDS", "10"))

    def probe(self) -> Dict[str, Any]:
        raise NotImplementedError

    def run(self, step_spec: Dict[str, Any], workspace: Path, prompt_bundle: Dict[str, Any]) -> StepResult:
        run_dir = self._prepare_run_dir(prompt_bundle, step_spec)
        prompt_file = run_dir / "prompt.md"
        bundle_file = run_dir / "prompt-bundle.json"
        output_file = run_dir / "raw-output.txt"

        prompt_text = self._build_prompt(step_spec, prompt_bundle)
        prompt_file.write_text(prompt_text, encoding="utf-8")
        bundle_file.write_text(json.dumps(prompt_bundle, ensure_ascii=False, indent=2), encoding="utf-8")

        started_at = time.perf_counter()
        result = self._execute(step_spec, Path(workspace).resolve(), prompt_bundle, prompt_text, prompt_file, output_file)
        if result.timing_ms == 0:
            result.timing_ms = int((time.perf_counter() - started_at) * 1000)
        return self._normalize_result(result)

    def _prepare_run_dir(self, prompt_bundle: Dict[str, Any], step_spec: Dict[str, Any]) -> Path:
        runs_root = self.project_root / ".webnovel" / "observability" / self.runs_dirname
        run_dir = runs_root / f"{prompt_bundle['task_id']}-{step_spec['name']}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _build_prompt(self, step_spec: Dict[str, Any], prompt_bundle: Dict[str, Any]) -> str:
        payload = json.dumps(prompt_bundle.get("input", {}), ensure_ascii=False, indent=2)
        schema_hint = json.dumps(step_spec.get("output_schema", {}), ensure_ascii=False, indent=2)
        instructions = (step_spec.get("instructions", "") or "").strip()

        reference_docs = prompt_bundle.get("reference_documents", [])
        if reference_docs:
            reference_blocks = []
            for item in reference_docs:
                title = item.get("path", "reference")
                content = item.get("content", "")
                reference_blocks.append(f"## {title}\n```text\n{content}\n```")
            references_block = "\n\n".join(reference_blocks)
        else:
            references_block = "No inline references were provided."

        project_docs = prompt_bundle.get("project_context", [])
        if project_docs:
            project_blocks = []
            for item in project_docs:
                title = item.get("path", "project-context")
                content = item.get("content", "")
                project_blocks.append(f"## {title}\n```text\n{content}\n```")
            project_block = "\n\n".join(project_blocks)
        else:
            project_block = "No project snapshot was provided."

        return (
            "You are the structured workflow engine for Webnovel Writer.\n"
            "Return exactly one JSON object with no prose before or after it.\n\n"
            f"# Task\n{instructions}\n\n"
            f"# Reference Documents\n{references_block}\n\n"
            f"# Project Snapshot\n{project_block}\n\n"
            f"# Input Payload\n```json\n{payload}\n```\n\n"
            f"# Output Contract\nReturn exactly one JSON object matching this shape:\n```json\n{schema_hint}\n```\n"
        )

    def _normalize_result(self, result: StepResult) -> StepResult:
        if not result.error:
            return result

        error = dict(result.error)
        code = str(error.get("code") or "").strip()
        normalized_message = STEP_ERROR_MESSAGES.get(code)
        if normalized_message:
            error["message"] = normalized_message
        result.error = error
        return result

    def _execute(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        prompt_text: str,
        prompt_file: Path,
        output_file: Path,
    ) -> StepResult:
        raise NotImplementedError


class MockRunner(LLMRunner):
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.responses_file = (os.environ.get("WEBNOVEL_MOCK_RESPONSES_FILE") or "").strip()

    def _is_configured(self) -> bool:
        return bool(self.responses_file and Path(self.responses_file).is_file())

    def probe(self) -> Dict[str, Any]:
        configured = self._is_configured()
        return {
            "provider": "mock",
            "mode": "mock",
            "installed": configured,
            "configured": configured,
            "model": "mock-json",
            "base_url": None,
            "binary": None,
            "version": None,
            "connection_status": "connected" if configured else "not_configured",
            "connection_checked_at": datetime.now(timezone.utc).isoformat(),
            "connection_error": None,
        }

    def _load_payloads(self) -> Dict[str, Any]:
        if not self._is_configured():
            return {}
        raw = Path(self.responses_file).read_text(encoding="utf-8-sig")
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}

    def _normalize_payload(self, step_spec: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(payload)
        step_name = str(step_spec.get("name") or "")
        if step_name.endswith("-review"):
            score = normalized.get("overall_score", normalized.get("score", 0))
            normalized.setdefault("overall_score", score)
            normalized.setdefault("pass", True)
            normalized.setdefault("issues", [])
            normalized.setdefault("metrics", {})
            normalized.setdefault("summary", "")
        return normalized

    def _execute(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        prompt_text: str,
        prompt_file: Path,
        output_file: Path,
    ) -> StepResult:
        payloads = self._load_payloads()
        if not payloads:
            message = "请设置 WEBNOVEL_MOCK_RESPONSES_FILE 指向有效 JSON 文件。"
            output_file.write_text(message, encoding="utf-8")
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=78,
                timing_ms=0,
                stdout="",
                stderr=message,
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "MOCK_NOT_CONFIGURED", "message": message},
            )

        payload = payloads.get(step_spec["name"])
        if not isinstance(payload, dict):
            message = f"mock responses 缺少步骤输出: {step_spec['name']}"
            output_file.write_text(message, encoding="utf-8")
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=65,
                timing_ms=0,
                stdout="",
                stderr=message,
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "MOCK_STEP_MISSING", "message": message},
            )

        payload = self._normalize_payload(step_spec, payload)
        raw = json.dumps(payload, ensure_ascii=False)
        output_file.write_text(raw, encoding="utf-8")
        return StepResult(
            step_name=step_spec["name"],
            success=True,
            return_code=0,
            timing_ms=0,
            stdout=raw,
            stderr="",
            structured_output=payload,
            prompt_file=str(prompt_file),
            output_file=str(output_file),
        )


class OpenAICompatibleRunner(LLMRunner):
    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.provider = os.environ.get("WEBNOVEL_LLM_PROVIDER", "openai-compatible").strip() or "openai-compatible"
        self.model = (os.environ.get("WEBNOVEL_LLM_MODEL") or os.environ.get("OPENAI_MODEL") or "").strip()
        self.api_key = (os.environ.get("WEBNOVEL_LLM_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()
        self.base_url = (
            os.environ.get("WEBNOVEL_LLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.temperature = float(os.environ.get("WEBNOVEL_LLM_TEMPERATURE", "0.1"))
        self._health_checked_at_epoch = 0.0
        self._connection_status = "not_checked"
        self._connection_checked_at: Optional[str] = None
        self._connection_error: Optional[Dict[str, Any]] = None

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    def _health_cache_valid(self) -> bool:
        return self._health_checked_at_epoch > 0 and (time.time() - self._health_checked_at_epoch) < self.health_ttl_seconds

    def _set_connection_state(self, status: str, error: Optional[Dict[str, Any]] = None) -> None:
        self._connection_status = status
        self._connection_error = error
        self._connection_checked_at = datetime.now(timezone.utc).isoformat()
        self._health_checked_at_epoch = time.time()

    def _check_connection(self, force: bool = False) -> None:
        if not self.is_configured():
            self._set_connection_state("not_configured", None)
            return
        if not force and self._health_cache_valid():
            return

        payload = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "health-check"}],
        }
        req = urlrequest.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urlrequest.urlopen(req, timeout=self.health_timeout_seconds) as response:
                raw_response = response.read().decode("utf-8")
            data = json.loads(raw_response)
            if not isinstance(data.get("choices"), list):
                self._set_connection_state(
                    "failed",
                    {"code": "LLM_RESPONSE_INVALID", "message": "写作模型健康检查返回格式无效。"},
                )
                return
            self._set_connection_state("connected", None)
        except urlerror.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self._set_connection_state(
                "failed",
                {
                    "code": "LLM_HTTP_ERROR",
                    "message": "写作模型健康检查失败。",
                    "original_message": body or str(exc),
                    "status_code": int(exc.code),
                },
            )
        except (urlerror.URLError, TimeoutError, OSError) as exc:
            self._set_connection_state(
                "failed",
                {
                    "code": "LLM_REQUEST_FAILED",
                    "message": "写作模型连接失败。",
                    "original_message": str(exc),
                },
            )
        except json.JSONDecodeError as exc:
            self._set_connection_state(
                "failed",
                {
                    "code": "LLM_RESPONSE_INVALID",
                    "message": "写作模型健康检查返回的 JSON 无法解析。",
                    "original_message": str(exc),
                },
            )

    def probe(self) -> Dict[str, Any]:
        self._check_connection()
        return {
            "provider": self.provider,
            "mode": "api",
            "installed": self.is_configured(),
            "configured": self.is_configured(),
            "model": self.model or None,
            "base_url": self.base_url,
            "binary": None,
            "version": None,
            "connection_status": self._connection_status,
            "connection_checked_at": self._connection_checked_at,
            "connection_error": self._connection_error,
        }

    def _execute(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        prompt_text: str,
        prompt_file: Path,
        output_file: Path,
    ) -> StepResult:
        if not self.is_configured():
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=78,
                timing_ms=0,
                stdout="",
                stderr="LLM API 未配置",
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={
                    "code": "LLM_NOT_CONFIGURED",
                    "message": "请设置 WEBNOVEL_LLM_API_KEY 和 WEBNOVEL_LLM_MODEL。",
                },
            )

        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "Return exactly one JSON object. Do not wrap it in markdown fences.",
                },
                {"role": "user", "content": prompt_text},
            ],
        }
        req = urlrequest.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urlrequest.urlopen(req, timeout=max(1, self.timeout_ms // 1000)) as response:
                raw_response = response.read().decode("utf-8")
        except urlerror.HTTPError as exc:
            raw_response = exc.read().decode("utf-8", errors="replace")
            output_file.write_text(raw_response, encoding="utf-8")
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=int(exc.code),
                timing_ms=0,
                stdout="",
                stderr=raw_response,
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "LLM_HTTP_ERROR", "message": raw_response or str(exc)},
            )
        except (urlerror.URLError, TimeoutError) as exc:
            output_file.write_text(str(exc), encoding="utf-8")
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=124,
                timing_ms=0,
                stdout="",
                stderr=str(exc),
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "LLM_REQUEST_FAILED", "message": str(exc)},
            )

        output_file.write_text(raw_response, encoding="utf-8")
        parsed = json.loads(raw_response)
        content = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
        structured_output = extract_json_payload(content)
        if structured_output is None:
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=65,
                timing_ms=0,
                stdout=content,
                stderr="",
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "INVALID_STEP_OUTPUT", "message": "LLM 输出中不包含有效 JSON 对象"},
            )

        return StepResult(
            step_name=step_spec["name"],
            success=True,
            return_code=0,
            timing_ms=0,
            stdout=content,
            stderr="",
            structured_output=structured_output,
            prompt_file=str(prompt_file),
            output_file=str(output_file),
        )


class CodexCliRunner(LLMRunner):
    runs_dirname = "codex-runs"

    def __init__(self, project_root: Path):
        super().__init__(project_root)
        self.binary = self._discover_binary()[0]

    def _binary_candidates(self) -> list[str]:
        explicit = (os.environ.get("WEBNOVEL_CODEX_BIN") or "").strip()
        if explicit:
            return [explicit]
        if os.name == "nt":
            return ["codex.cmd", "codex.exe", "codex"]
        return ["codex"]

    def _discover_binary(self) -> tuple[str, Optional[str]]:
        candidates = self._binary_candidates()
        for candidate in candidates:
            resolved = shutil.which(candidate)
            if resolved:
                return candidate, resolved
        return candidates[0], None

    def probe(self) -> Dict[str, Any]:
        binary, resolved_binary = self._discover_binary()
        self.binary = binary
        exists = resolved_binary is not None
        version = None
        if exists:
            try:
                completed = subprocess.run(
                    [resolved_binary, "--version"],
                    cwd=str(self.project_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    check=False,
                )
                version = (completed.stdout or completed.stderr).strip() or None
            except OSError:
                exists = False
                resolved_binary = None
        return {
            "provider": "codex-cli",
            "mode": "cli",
            "binary": binary,
            "resolved_binary": resolved_binary,
            "installed": exists,
            "configured": exists,
            "version": version,
            "model": None,
            "base_url": None,
            "connection_status": "connected" if exists else "failed",
            "connection_checked_at": datetime.now(timezone.utc).isoformat(),
            "connection_error": None if exists else {
                "code": "CODEX_CLI_NOT_FOUND",
                "message": "未找到 Codex CLI 可执行文件。",
                "original_message": f"Missing CLI executable: {binary}",
            },
        }

    def _execute(
        self,
        step_spec: Dict[str, Any],
        workspace: Path,
        prompt_bundle: Dict[str, Any],
        prompt_text: str,
        prompt_file: Path,
        output_file: Path,
    ) -> StepResult:
        binary, resolved_binary = self._discover_binary()
        self.binary = binary
        if resolved_binary is None:
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=127,
                timing_ms=0,
                stdout="",
                stderr="Codex CLI not found",
                structured_output=None,
                prompt_file=str(prompt_file),
                output_file=str(output_file),
                error={"code": "CODEX_CLI_NOT_FOUND", "message": f"Missing CLI executable: {binary}"},
            )

        last_message_file = output_file.with_name("assistant-last-message.txt")
        try:
            completed = subprocess.run(
                [resolved_binary, "exec", "-o", str(last_message_file), "-"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                encoding="utf-8",
                input=prompt_text,
                timeout=max(1, self.timeout_ms // 1000),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            partial_stdout = _ensure_str(exc.stdout)
            partial_stderr = _ensure_str(exc.stderr)
            output_file.write_text(partial_stdout + "\n" + partial_stderr, encoding="utf-8")
            assistant_message = ""
            if last_message_file.exists():
                assistant_message = last_message_file.read_text(encoding="utf-8")
            structured_output = extract_json_payload(assistant_message or partial_stdout)
            if structured_output is not None:
                return StepResult(
                    step_name=step_spec["name"],
                    success=True,
                    return_code=0,
                    timing_ms=0,
                    stdout=assistant_message or partial_stdout,
                    stderr=partial_stderr,
                    structured_output=structured_output,
                    prompt_file=str(prompt_file),
                    output_file=str(output_file),
                )
            return StepResult(
                step_name=step_spec["name"],
                success=False,
                return_code=124,
                timing_ms=0,
                stdout=partial_stdout,
                stderr=partial_stderr,
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

        stdout = _ensure_str(completed.stdout)
        stderr = _ensure_str(completed.stderr)
        output_file.write_text(stdout + ("\n" if stdout and stderr else "") + stderr, encoding="utf-8")

        assistant_message = ""
        if last_message_file.exists():
            assistant_message = last_message_file.read_text(encoding="utf-8")
        structured_output = extract_json_payload(assistant_message or stdout)
        error = None
        success = completed.returncode == 0
        if not success:
            error = self._map_error(stderr or stdout)
        elif structured_output is None:
            success = False
            error = {
                "code": "INVALID_STEP_OUTPUT",
                "message": "Codex 输出中不包含有效 JSON 对象",
            }

        return StepResult(
            step_name=step_spec["name"],
            success=success,
            return_code=int(completed.returncode),
            timing_ms=0,
            stdout=assistant_message or stdout,
            stderr=stderr,
            structured_output=structured_output,
            prompt_file=str(prompt_file),
            output_file=str(output_file),
            error=error,
        )

    def _map_error(self, raw: str) -> Dict[str, str]:
        text = (raw or "").lower()
        if "login" in text or "auth" in text:
            return {"code": "CODEX_AUTH_REQUIRED", "message": raw.strip() or "需要先登录 Codex"}
        if "not found" in text:
            return {"code": "CODEX_CLI_NOT_FOUND", "message": raw.strip() or "未找到 Codex CLI"}
        return {"code": "CODEX_STEP_FAILED", "message": raw.strip() or "Codex 步骤执行失败"}


def create_default_runner(project_root: Path) -> LLMRunner:
    load_runtime_env(project_root)
    provider = (os.environ.get("WEBNOVEL_LLM_PROVIDER") or "openai-compatible").strip().lower()
    api_runner = OpenAICompatibleRunner(project_root)
    if provider == "mock":
        return MockRunner(project_root)
    if provider in {"codex", "codex-cli", "cli"}:
        return CodexCliRunner(project_root)
    if api_runner.is_configured():
        return api_runner
    cli_runner = CodexCliRunner(project_root)
    if cli_runner.probe().get("installed"):
        return cli_runner
    return api_runner
