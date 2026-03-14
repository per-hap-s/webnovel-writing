from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from scripts.data_modules.api_client import get_client
from scripts.data_modules.config import get_config
from scripts.data_modules.index_manager import IndexManager, ReviewMetrics
from scripts.data_modules.state_manager import StateManager

from .llm_runner import LLMRunner, StepResult, create_default_runner
from .task_store import TaskStore

BODY_DIR_NAME = "正文"
OUTLINE_DIR_NAME = "大纲"
OUTLINE_SUMMARY_FILE = "总纲.md"
SUMMARY_SECTION_PLOT = "## 剧情摘要"
SUMMARY_SECTION_REVIEW = "## 审查结果"
SUMMARY_SECTION_ISSUES = "## 主要问题"


class OrchestrationService:
    def __init__(self, project_root: Path, runner: Optional[LLMRunner] = None):
        self.project_root = Path(project_root).resolve()
        self.spec_dir = Path(__file__).resolve().parent.parent / "workflow_specs"
        self.template_dir = self.spec_dir / "templates"
        self.store = TaskStore(self.project_root)
        self.runner = runner or create_default_runner(self.project_root)
        self.config = get_config(project_root=self.project_root)
        self.rag_client = get_client(self.config)
        self.index_manager = IndexManager(self.config)
        self._jobs: dict[str, asyncio.Task] = {}

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.store.list_tasks(limit=limit)

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_task(task_id)

    def get_events(self, task_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        return self.store.get_events(task_id, limit=limit)

    def probe_llm(self) -> Dict[str, Any]:
        return self.runner.probe()

    def probe_codex(self) -> Dict[str, Any]:
        return self.probe_llm()

    def probe_rag(self) -> Dict[str, Any]:
        return self.rag_client.probe()

    def create_task(self, task_type: str, request: Dict[str, Any]) -> Dict[str, Any]:
        workflow = self._load_workflow(task_type)
        task = self.store.create_task(task_type, request, workflow)
        task = self.store.update_task(task["id"], workflow_spec=workflow)
        self._schedule(task["id"])
        return task

    def run_task_sync(self, task_type: str, request: Dict[str, Any], *, resume_from_step: Optional[str] = None) -> Dict[str, Any]:
        workflow = self._load_workflow(task_type)
        task = self.store.create_task(task_type, request, workflow)
        task = self.store.update_task(task["id"], workflow_spec=workflow)
        asyncio.run(self._run_task(task["id"], resume_from_step=resume_from_step))
        refreshed = self.store.get_task(task["id"])
        if refreshed is None:
            raise KeyError(task["id"])
        return refreshed

    def retry_task(self, task_id: str, resume_from_step: Optional[str] = None) -> Dict[str, Any]:
        task = self.store.reset_for_retry(task_id)
        self.store.append_event(task_id, "info", "Retry requested", payload={"resume_from_step": resume_from_step})
        self._schedule(task_id, resume_from_step=resume_from_step or task.get("current_step"))
        return self.store.get_task(task_id)

    def approve_writeback(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        self.store.update_task(task_id, approval_status="approved", status="queued")
        self.store.append_event(task_id, "info", "Writeback approved", payload={"reason": reason})
        self._schedule(task_id, resume_from_step=task.get("current_step") or "approval-gate")
        return self.store.get_task(task_id)

    def reject_writeback(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        self.store.append_event(task_id, "warning", "Writeback rejected", payload={"reason": reason})
        return self.store.mark_rejected(task_id, reason or "Rejected by operator")

    def confirm_invalid_facts(self, ids: List[int], action: str) -> Dict[str, Any]:
        updated = 0
        for invalid_id in ids:
            if self.index_manager.resolve_invalid_fact(int(invalid_id), action):
                updated += 1
        return {"updated": updated, "action": action, "ids": ids}

    def _resolve_task_workflow(self, task: Dict[str, Any]) -> Dict[str, Any]:
        workflow = task.get("workflow_spec")
        if isinstance(workflow, dict) and workflow.get("steps") is not None:
            return workflow
        workflow = self._load_workflow(task["task_type"])
        self.store.update_task(task["id"], workflow_spec=workflow)
        return workflow

    def _schedule(self, task_id: str, resume_from_step: Optional[str] = None) -> bool:
        existing = self._jobs.get(task_id)
        if existing and not existing.done():
            return True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.info("No running event loop; task %s remains queued", task_id)
            return False
        self._jobs[task_id] = loop.create_task(self._run_task(task_id, resume_from_step=resume_from_step))
        return True

    async def _run_task(self, task_id: str, resume_from_step: Optional[str] = None) -> None:
        task = self.store.get_task(task_id)
        if task is None:
            return

        current_step_name: Optional[str] = None
        try:
            workflow = self._resolve_task_workflow(task)
            steps = workflow.get("steps", [])
            start_index = 0
            if resume_from_step:
                for idx, step in enumerate(steps):
                    if step["name"] == resume_from_step:
                        start_index = idx
                        break

            for index in range(start_index, len(steps)):
                step = steps[index]
                current_step_name = step["name"]
                self.store.mark_running(task_id, current_step_name)
                self.store.append_event(task_id, "info", f"Step started: {current_step_name}", step_name=current_step_name)
                current_task = self.store.get_task(task_id)
                if current_task is None:
                    return

                if step["type"] == "internal":
                    outcome = await self._run_internal_step(task_id, current_task, workflow, step, index)
                    if outcome in {"paused", "failed"}:
                        return
                    continue

                prompt_bundle = self._build_prompt_bundle(current_task, step)
                result = await asyncio.to_thread(self.runner.run, prompt_bundle["step_spec"], self.project_root, prompt_bundle)
                result_dict = result.to_dict()
                self.store.save_step_result(task_id, current_step_name, result_dict)
                self.store.append_event(
                    task_id,
                    "info" if result.success else "error",
                    f"{'Step completed' if result.success else 'Step failed'}: {current_step_name}",
                    step_name=current_step_name,
                    payload={"timing_ms": result.timing_ms, "error": result.error},
                )

                if not result.success:
                    self.store.mark_failed(
                        task_id,
                        current_step_name,
                        result.error or {"code": "STEP_FAILED", "message": "步骤执行失败。"},
                    )
                    return

                validation_error = self._validate_output(step, result.structured_output or {})
                if validation_error:
                    self.store.mark_failed(task_id, current_step_name, validation_error)
                    self.store.append_event(task_id, "error", "Schema validation failed", step_name=current_step_name, payload=validation_error)
                    return

                apply_error = self._apply_step_side_effects(task_id, step, result.structured_output or {})
                if apply_error:
                    self.store.mark_failed(task_id, current_step_name, apply_error)
                    self.store.append_event(task_id, "error", "Step writeback failed", step_name=current_step_name, payload=apply_error)
                    return

            self.store.mark_completed(task_id)
            self.store.append_event(task_id, "info", "Task completed")
        except FileNotFoundError as exc:
            error_info = {"code": "WORKFLOW_NOT_FOUND", "message": f"未找到工作流定义文件：{exc}"}
            logger.error("Task %s workflow spec not found: %s", task_id, exc, exc_info=True)
            self.store.mark_failed(task_id, current_step_name or "init", error_info)
            self.store.append_event(task_id, "error", "Workflow spec not found", step_name=current_step_name, payload=error_info)
        except json.JSONDecodeError as exc:
            error_info = {"code": "WORKFLOW_PARSE_ERROR", "message": f"工作流定义解析失败：{exc}"}
            logger.error("Task %s workflow spec parse failed: %s", task_id, exc, exc_info=True)
            self.store.mark_failed(task_id, current_step_name or "init", error_info)
            self.store.append_event(task_id, "error", "Workflow parse failed", step_name=current_step_name, payload=error_info)
        except KeyError as exc:
            error_info = {"code": "WORKFLOW_CONFIG_ERROR", "message": f"工作流配置缺少必要字段：{exc}"}
            logger.error("Task %s workflow config error: %s", task_id, exc, exc_info=True)
            self.store.mark_failed(task_id, current_step_name or "init", error_info)
            self.store.append_event(task_id, "error", "Workflow config error", step_name=current_step_name, payload=error_info)
        except Exception as exc:
            error_info = {"code": "UNEXPECTED_ERROR", "message": f"任务执行时发生未预期错误：{exc}"}
            logger.critical("Task %s raised an unexpected error: %s", task_id, exc, exc_info=True)
            self.store.mark_failed(task_id, current_step_name or "init", error_info)
            self.store.append_event(task_id, "error", "Task execution failed", step_name=current_step_name, payload=error_info)

    async def _run_internal_step(
        self,
        task_id: str,
        task: Dict[str, Any],
        workflow: Dict[str, Any],
        step: Dict[str, Any],
        index: int,
    ) -> str:
        step_name = step["name"]
        if step_name == "review-summary":
            summary = self._aggregate_review(task)
            self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": summary})
            artifacts = dict(task.get("artifacts") or {})
            artifacts["review_summary"] = summary
            self.store.update_task(task_id, artifacts=artifacts)
            self._persist_review_summary(task, summary)
            self.store.append_event(task_id, "info", "Review summary persisted", step_name=step_name, payload=summary)
            blocking_error = self._build_review_gate_error(task, summary)
            if blocking_error is not None:
                self.store.mark_failed(task_id, step_name, blocking_error)
                self.store.append_event(task_id, "error", "Review gate blocked execution", step_name=step_name, payload=blocking_error)
                return "failed"
            return "ok"

        if step_name == "approval-gate":
            request = task.get("request", {})
            require_manual_approval = bool(request.get("require_manual_approval", True))
            summary = (task.get("artifacts") or {}).get("review_summary")
            if task.get("approval_status") == "approved":
                self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": {"approval_required": True, "approved": True}})
                return "ok"
            if task["task_type"] == "write" and require_manual_approval:
                approval = {
                    "status": "pending",
                    "requested_at": task.get("updated_at"),
                    "summary": summary,
                    "next_step": self._next_step_name(workflow, index),
                }
                self.store.mark_waiting_for_approval(task_id, step_name, approval)
                self.store.append_event(task_id, "warning", "Waiting for writeback approval", step_name=step_name)
                return "paused"
            self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": {"approval_required": False}})
            return "ok"

        self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": {"skipped": True}})
        return "ok"

    def _build_prompt_bundle(self, task: Dict[str, Any], step: Dict[str, Any]) -> Dict[str, Any]:
        reference_paths: List[Path] = []
        for rel_path in step.get("references", []):
            reference_paths.append((Path(__file__).resolve().parent.parent / rel_path).resolve())

        instructions = self._load_template(step.get("template"))
        step_spec = dict(step)
        step_spec["instructions"] = instructions
        task_input = {
            "request": task.get("request", {}),
            "project_root": task.get("project_root"),
            "prior_step_results": self._compact_prior_step_results((task.get("artifacts") or {}).get("step_results", {})),
            "review_summary": (task.get("artifacts") or {}).get("review_summary"),
        }
        return {
            "task_id": task["id"],
            "task_type": task["task_type"],
            "step_name": step["name"],
            "references": [str(path) for path in reference_paths],
            "reference_documents": self._load_reference_documents(reference_paths),
            "project_context": self._collect_project_context(task, step),
            "input": task_input,
            "instructions": instructions,
            "step_spec": step_spec,
        }

    def _load_reference_documents(self, paths: List[Path]) -> List[Dict[str, str]]:
        documents: List[Dict[str, str]] = []
        for path in paths:
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            documents.append(
                {
                    "path": self._label_reference_path(path),
                    "content": self._sanitize_reference_text(content)[:12000],
                }
            )
        return documents


    def _label_reference_path(self, path: Path) -> str:
        app_root = Path(__file__).resolve().parent.parent
        try:
            return str(path.relative_to(app_root)).replace('\\', '/')
        except ValueError:
            return path.name
    def _sanitize_reference_text(self, text: str) -> str:
        cleaned = text
        if cleaned.startswith("---"):
            marker = cleaned.find("\n---", 3)
            if marker != -1:
                cleaned = cleaned[marker + 4 :]
        replacements = {
            "allowed-tools:": "runtime-note:",
            "CLAUDE_PLUGIN_ROOT": "WEBNOVEL_APP_ROOT",
            "CLAUDE_PROJECT_DIR": "WEBNOVEL_WORKSPACE_ROOT",
            "/webnovel-": "webnovel ",
            "Claude Code": "Webnovel CLI",
            "AskUserQuestion": "question-step",
            "Task": "subtask",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        lines = []
        for line in cleaned.splitlines():
            lowered = line.lower()
            if "allowed-tools:" in lowered:
                continue
            lines.append(line)
        return "\n".join(lines).strip()

    def _collect_project_context(self, task: Dict[str, Any], step: Dict[str, Any]) -> List[Dict[str, str]]:
        request = task.get("request") or {}
        chapter = int(request.get("chapter") or 0)
        project_docs: List[Dict[str, str]] = []

        self._append_snapshot(project_docs, self.project_root / ".webnovel" / "state.json", ".webnovel/state.json", 12000)
        self._append_snapshot(project_docs, self.project_root / OUTLINE_DIR_NAME / OUTLINE_SUMMARY_FILE, f"{OUTLINE_DIR_NAME}/{OUTLINE_SUMMARY_FILE}", 12000)

        outline_dir = self.project_root / OUTLINE_DIR_NAME
        if outline_dir.is_dir():
            for candidate in sorted(outline_dir.glob("*.md"))[:2]:
                if candidate.name == OUTLINE_SUMMARY_FILE:
                    continue
                self._append_snapshot(project_docs, candidate, f"{OUTLINE_DIR_NAME}/{candidate.name}", 8000)

        if chapter > 0:
            padded = f"{chapter:04d}"
            self._append_glob_snapshot(project_docs, self.project_root / BODY_DIR_NAME, [f"*{padded}*.md", f"*{chapter}*.md"], 8000)
            self._append_snapshot(project_docs, self.project_root / ".webnovel" / "summaries" / f"ch{padded}.md", f".webnovel/summaries/ch{padded}.md", 4000)
            if chapter > 1:
                prev = f"{chapter - 1:04d}"
                self._append_snapshot(project_docs, self.project_root / ".webnovel" / "summaries" / f"ch{prev}.md", f".webnovel/summaries/ch{prev}.md", 4000)

        return project_docs

    def _compact_prior_step_results(self, step_results: Dict[str, Any]) -> Dict[str, Any]:
        compact: Dict[str, Any] = {}
        for step_name, result in (step_results or {}).items():
            if not isinstance(result, dict):
                continue
            compact[step_name] = {
                "success": bool(result.get("success", False)),
                "structured_output": result.get("structured_output"),
                "error": result.get("error"),
            }
        return compact

    def _append_snapshot(self, documents: List[Dict[str, str]], path: Path, label: str, max_chars: int) -> None:
        if not path.is_file():
            return
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return
        documents.append({"path": label, "content": content[:max_chars]})

    def _append_glob_snapshot(self, documents: List[Dict[str, str]], base_dir: Path, patterns: List[str], max_chars: int) -> None:
        if not base_dir.is_dir():
            return
        for pattern in patterns:
            for candidate in sorted(base_dir.glob(pattern)):
                self._append_snapshot(documents, candidate, f"{BODY_DIR_NAME}/{candidate.name}", max_chars)
                return

    def _apply_step_side_effects(self, task_id: str, step: Dict[str, Any], payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
        task = self.store.get_task(task_id)
        if task is None:
            return {"code": "TASK_NOT_FOUND", "message": f"未找到任务：{task_id}"}
        if task.get("task_type") != "write":
            return None
        step_name = step.get("name", "unknown")
        try:
            if step_name == "data-sync":
                self._apply_write_data_sync(task_id, task, payload)
        except (ValueError, KeyError) as exc:
            error_msg = f"步骤 {step_name} 校验失败：{exc}"
            logger.error("Task %s step %s validation failed: %s", task_id, step_name, exc, exc_info=True)
            return {"code": "VALIDATION_ERROR", "message": error_msg}
        except (IOError, OSError) as exc:
            error_msg = f"步骤 {step_name} 文件操作失败：{exc}"
            logger.error("Task %s step %s file operation failed: %s", task_id, step_name, exc, exc_info=True)
            return {"code": "IO_ERROR", "message": error_msg}
        except Exception as exc:
            error_msg = f"步骤 {step_name} 回写失败：{exc}"
            logger.critical("Task %s step %s raised an unexpected error: %s", task_id, step_name, exc, exc_info=True)
            return {"code": "WRITEBACK_FAILED", "message": error_msg}
        return None
    def _write_polished_chapter(self, task_id: str, payload: Dict[str, Any]) -> Path:
        chapter_file = str(payload.get("chapter_file") or "").strip()
        content = payload.get("content")
        if not chapter_file or not isinstance(content, str) or not content.strip():
            raise ValueError("polish 步骤缺少有效的 chapter_file 或 content")
        written_path = self._write_project_text(chapter_file, content)
        self.store.append_event(
            task_id,
            "info",
            "Chapter body written",
            step_name="polish",
            payload={"path": self._relative_project_path(written_path)},
        )
        return written_path

    def _apply_write_data_sync(self, task_id: str, task: Dict[str, Any], payload: Dict[str, Any]) -> None:
        request = task.get("request") or {}
        chapter = int(request.get("chapter") or 0)
        if chapter <= 0:
            raise ValueError("data-sync 缺少有效的 chapter")

        artifacts = task.get("artifacts") or {}
        step_results = artifacts.get("step_results") or {}
        draft_output = (step_results.get("draft") or {}).get("structured_output") or {}
        polish_output = (step_results.get("polish") or {}).get("structured_output") or {}
        review_summary = artifacts.get("review_summary") or {}

        chapter_file = str(
            payload.get("chapter_file")
            or polish_output.get("chapter_file")
            or draft_output.get("chapter_file")
            or self._default_chapter_file(chapter)
        )
        content = payload.get("content") or polish_output.get("content") or draft_output.get("content") or ""
        if not isinstance(content, str) or not content.strip():
            raise ValueError("data-sync 无法确定章节正文内容")

        chapter_path = self._write_project_text(chapter_file, content)

        summary_file = str(payload.get("summary_file") or f".webnovel/summaries/ch{chapter:04d}.md")
        summary_content = payload.get("summary_content") or payload.get("summary_text")
        if not isinstance(summary_content, str) or not summary_content.strip():
            summary_content = self._build_summary_markdown(chapter, content, review_summary)
        summary_path = self._write_project_text(summary_file, summary_content)

        state_payload = {
            "entities_appeared": payload.get("entities_appeared", []),
            "entities_new": payload.get("entities_new", []),
            "state_changes": payload.get("state_changes", []),
            "relationships_new": payload.get("relationships_new", []),
            "uncertain": payload.get("uncertain", []),
            "chapter_meta": payload.get("chapter_meta") or {},
        }
        state_manager = StateManager(get_config(project_root=self.project_root))
        state_manager.process_chapter_result(chapter, state_payload)
        word_count = self._derive_word_count(payload, polish_output, draft_output, content)
        state_manager.update_progress(chapter, words=word_count)
        state_manager.save_state()

        latest_task = self.store.get_task(task_id) or task
        latest_artifacts = dict(latest_task.get("artifacts") or {})
        writeback = dict(latest_artifacts.get("writeback") or {})
        writeback.update(
            {
                "chapter_file": self._relative_project_path(chapter_path),
                "summary_file": self._relative_project_path(summary_path),
                "state_file": ".webnovel/state.json",
                "word_count": word_count,
            }
        )
        latest_artifacts["writeback"] = writeback
        self.store.update_task(task_id, artifacts=latest_artifacts)
        self.store.append_event(
            task_id,
            "info",
            "Data sync completed",
            step_name="data-sync",
            payload=writeback,
        )

    def _build_summary_markdown(self, chapter: int, content: str, review_summary: Dict[str, Any]) -> str:
        snippet = " ".join(line.strip() for line in content.splitlines() if line.strip())
        snippet = snippet[:300] + ("..." if len(snippet) > 300 else "")
        issues = review_summary.get("issues") or []
        reviewers = review_summary.get("reviewers") or []
        lines = [
            f"# 第{chapter:04d}章摘要",
            "",
            SUMMARY_SECTION_PLOT,
            snippet or "暂无摘要。",
            "",
            SUMMARY_SECTION_REVIEW,
            f"- overall_score: {review_summary.get('overall_score', 0)}",
            f"- blocking: {str(bool(review_summary.get('blocking'))).lower()}",
            f"- reviewer_count: {len(reviewers)}",
            f"- issue_count: {len(issues)}",
        ]
        if issues:
            lines.extend(["", SUMMARY_SECTION_ISSUES])
            for issue in issues[:5]:
                title = issue.get("title") or issue.get("message") or "未命名问题"
                severity = issue.get("severity") or "medium"
                lines.append(f"- [{severity}] {title}")
        return "\n".join(lines).strip() + "\n"

    def _derive_word_count(
        self,
        payload: Dict[str, Any],
        polish_output: Dict[str, Any],
        draft_output: Dict[str, Any],
        content: str,
    ) -> int:
        for candidate in (payload.get("word_count"), polish_output.get("word_count"), draft_output.get("word_count")):
            if isinstance(candidate, int) and candidate > 0:
                return candidate
            if isinstance(candidate, str) and candidate.isdigit():
                return int(candidate)
        return len("".join(content.split()))

    def _default_chapter_file(self, chapter: int) -> str:
        return f"正文/第{chapter:04d}章.md"

    def _resolve_project_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = self.project_root / candidate
        candidate = candidate.resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise ValueError(f"路径超出项目根目录: {raw_path}") from exc
        return candidate

    def _relative_project_path(self, path: Path) -> str:
        return str(path.relative_to(self.project_root)).replace('\\', '/')

    def _write_project_text(self, raw_path: str, content: str) -> Path:
        target = self._resolve_project_path(raw_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def _validate_output(self, step: Dict[str, Any], payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
        required = step.get("required_output_keys", [])
        missing = [key for key in required if key not in payload]
        if missing:
            return {
                "code": "INVALID_STEP_OUTPUT",
                "message": f"缺少必要字段：{', '.join(missing)}",
            }
        if step["name"] == "polish" and payload.get("anti_ai_force_check") != "pass":
            return {"code": "ANTI_AI_GATE_FAILED", "message": "anti_ai_force_check 必须为 pass 才能执行回写。"}
        return None

    def _collect_hard_blocking_issues(self, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        blocked: List[Dict[str, Any]] = []
        for issue in issues:
            severity = str(issue.get("severity", "")).lower()
            issue_type = str(issue.get("type", "")).upper()
            if severity == "critical":
                blocked.append(issue)
                continue
            if issue_type == "TIMELINE_ISSUE" and severity in {"critical", "high"}:
                blocked.append(issue)
        return blocked

    def _build_review_gate_error(self, task: Dict[str, Any], summary: Dict[str, Any]) -> Optional[Dict[str, str]]:
        if task.get("task_type") != "write":
            return None
        hard_blocking_issues = summary.get("hard_blocking_issues") or []
        if not hard_blocking_issues:
            return None
        first_issue = hard_blocking_issues[0]
        severity = str(first_issue.get("severity", "critical")).lower()
        title = first_issue.get("title") or first_issue.get("description") or first_issue.get("message") or "审查关卡已拦截当前任务"
        return {
            "code": "REVIEW_GATE_BLOCKED",
            "message": f"审查关卡阻止继续执行：[{severity}] {title}",
        }
    def _aggregate_review(self, task: Dict[str, Any]) -> Dict[str, Any]:
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        reviewers = []
        issues: List[Dict[str, Any]] = []
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        scores: List[float] = []

        for step_name, result in step_results.items():
            if "review" not in step_name or step_name == "review-summary":
                continue
            payload = result.get("structured_output") or {}
            score_value = payload.get("overall_score", payload.get("score", 0))
            reviewers.append(
                {
                    "step_name": step_name,
                    "score": score_value,
                    "pass": payload.get("pass"),
                    "summary": payload.get("summary"),
                }
            )
            if isinstance(score_value, (int, float)):
                scores.append(float(score_value))
            for issue in payload.get("issues", []):
                issue_copy = dict(issue)
                issue_copy.setdefault("source", step_name)
                issues.append(issue_copy)
                severity = str(issue_copy.get("severity", "medium")).lower()
                if severity in severity_counts:
                    severity_counts[severity] += 1

        hard_blocking_issues = self._collect_hard_blocking_issues(issues)
        blocking = bool(hard_blocking_issues or severity_counts["critical"] > 0)
        overall_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        return {
            "overall_score": overall_score,
            "reviewers": reviewers,
            "issues": issues,
            "severity_counts": severity_counts,
            "hard_blocking_issues": hard_blocking_issues,
            "blocking": blocking,
            "can_proceed": not blocking,
        }

    def _persist_review_summary(self, task: Dict[str, Any], summary: Dict[str, Any]) -> None:
        request = task.get("request") or {}
        chapter = int(request.get("chapter") or 0)
        if chapter <= 0:
            return
        metrics = ReviewMetrics(
            start_chapter=chapter,
            end_chapter=chapter,
            overall_score=float(summary.get("overall_score") or 0.0),
            severity_counts=summary.get("severity_counts") or {},
            critical_issues=[issue.get("title", issue.get("message", "")) for issue in summary.get("issues", []) if str(issue.get("severity", "")).lower() == "critical"],
            notes=json.dumps(summary, ensure_ascii=False),
        )
        self.index_manager.save_review_metrics(metrics)

    def _load_workflow(self, task_type: str) -> Dict[str, Any]:
        path = self.spec_dir / f"{task_type}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Workflow spec not found: {path}")
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def _load_template(self, template_name: Optional[str]) -> str:
        if not template_name:
            return ""
        path = self.template_dir / template_name
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8")

    def _next_step_name(self, workflow: Dict[str, Any], index: int) -> Optional[str]:
        steps = workflow.get("steps", [])
        if index + 1 >= len(steps):
            return None
        return steps[index + 1]["name"]













