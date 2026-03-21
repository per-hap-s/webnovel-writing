from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from scripts.init_project import (
    build_planning_fill_template,
    evaluate_planning_readiness,
    load_planning_profile,
    normalize_planning_profile,
)
from scripts.data_modules.api_client import get_client
from scripts.data_modules.config import get_config
from scripts.data_modules.index_manager import ChapterMeta, EntityMeta, IndexManager, RelationshipMeta, ReviewMetrics
from scripts.data_modules.narrative_graph import NarrativeGraph
from scripts.data_modules.state_manager import StateManager
from scripts.data_modules.state_file import (
    read_project_state,
    update_project_state,
)
from scripts.data_modules.state_validator import get_chapter_meta_entry
from scripts.data_modules.story_plan_locator import load_story_plan_for_chapter

from .llm_runner import LLMRunner, StepResult, create_default_runner
from .task_store import TaskStore

SETTINGS_DIR_NAME = "\u8bbe\u5b9a\u96c6"
REVIEW_REPORT_DIR_NAME = "\u5ba1\u67e5\u62a5\u544a"

BODY_DIR_NAME = "正文"
OUTLINE_DIR_NAME = "大纲"
OUTLINE_SUMMARY_FILE = "总纲.md"
DIRECTOR_DIR_NAME = ".webnovel/director"
STORY_DIRECTOR_DIR_NAME = ".webnovel/story-director"
SUPERVISOR_DIR_NAME = ".webnovel/supervisor"
SUPERVISOR_CHECKLISTS_DIR_NAME = f"{SUPERVISOR_DIR_NAME}/checklists"
SUPERVISOR_AUDIT_LOG_NAME = f"{SUPERVISOR_DIR_NAME}/audit-log.jsonl"
SUPERVISOR_AUDIT_REPAIR_REPORTS_DIR_NAME = f"{SUPERVISOR_DIR_NAME}/audit-repair-reports"
SUPERVISOR_AUDIT_SCHEMA_VERSION = 1
SUPERVISOR_AUDIT_MAX_SUPPORTED_SCHEMA_VERSION = 2
SUMMARY_SECTION_PLOT = "## 剧情摘要"
SUMMARY_SECTION_REVIEW = "## 审查结果"
SUMMARY_SECTION_ISSUES = "## 主要问题"
REPAIR_BACKUPS_DIR_NAME = ".webnovel/repair-backups"
REPAIR_REPORTS_DIR_NAME = ".webnovel/repair-reports"
REPAIR_NOT_ELIGIBLE_CODE = "REPAIR_NOT_ELIGIBLE"
REPAIR_REVIEW_BLOCKED_CODE = "REPAIR_REVIEW_BLOCKED"
REPAIR_INPUT_INVALID_CODE = "REPAIR_INPUT_INVALID"
AUTO_REPAIR_ISSUE_TYPES = {
    "AMBIGUOUS_WARNING_SOURCE",
    "RULE_SCOPE_CONFUSION",
    "TRANSITION_CLARITY",
    "HOOK_BRIDGE_GAP",
    "PLOT_THREAD_CONTINUITY",
    "MEMORY_LOSS_OBJECTIVITY",
}


MIN_WRITEBACK_WORD_COUNT = 200
MAX_WORD_COUNT_DRIFT = 200
MAX_WORD_COUNT_DRIFT_RATIO = 0.5
MIN_PLAN_OUTLINE_CHARS = 120
PLAN_OUTLINE_SIGNAL_PHRASES = (
    "故事前提",
    "核心设定",
    "能力代价",
    "核心冲突",
    "关键爽点",
    "卷末高潮",
    "主要角色",
    "关键伏笔",
)
PLAN_INPUT_BLOCKED_CODE = "PLAN_INPUT_BLOCKED"
PLAN_INPUT_BLOCKED_MESSAGE = "规划输入不完整，无法生成可执行卷规划。"

SETTING_DOC_PATHS = {
    "worldview": f"{SETTINGS_DIR_NAME}/世界观.md",
    "power_system": f"{SETTINGS_DIR_NAME}/力量体系.md",
    "protagonist": f"{SETTINGS_DIR_NAME}/主角卡.md",
    "golden_finger": f"{SETTINGS_DIR_NAME}/金手指设计.md",
}


RUNTIME_PHASE_LABELS = {
    "init": "初始化分析",
    "plan": "卷规划",
    "repair": "自动修稿",
    "resume": "流程恢复",
    "guarded-chapter-runner": "护栏推进一章",
    "guarded-batch-runner": "护栏批量推进",
    "story-director": "多章叙事规划",
    "chapter-director": "单章导演决策",
    "repair-plan": "修稿规划",
    "repair-draft": "修稿改写",
    "context": "上下文准备",
    "draft": "草稿生成",
    "consistency-review": "一致性审查",
    "continuity-review": "连续性审查",
    "ooc-review": "角色一致性审查",
    "review-summary": "审查汇总",
    "polish": "正文润色",
    "approval-gate": "回写审批",
    "repair-writeback": "修稿回写",
    "data-sync": "写回同步",
}

RUNTIME_EVENT_LABELS = {
    "llm_request_started": "模型请求已发出",
    "llm_request_finished": "模型请求已完成",
    "llm_request_timed_out": "模型请求已超时",
    "llm_request_failed": "模型请求失败",
    "prompt_compiled": "提示词已组装完成",
    "request_dispatched": "已向上游发出请求",
    "awaiting_model_response": "正在等待模型响应",
    "response_received": "已收到模型响应",
    "parsing_output": "正在解析输出",
    "step_heartbeat": "任务仍在运行",
    "step_retry_scheduled": "已安排步骤重试",
    "step_retry_started": "步骤重试开始",
    "step_waiting_approval": "等待人工批准回写",
    "Waiting for writeback approval": "等待人工批准回写",
    "Retry requested": "已请求重试",
    "Writeback approved": "已批准回写",
    "Writeback rejected": "已拒绝回写",
    "Task completed": "任务已完成",
    "plan_blocked": "规划待补信息",
    "writeback_rollback_started": "开始回滚失败写回",
    "writeback_rollback_finished": "失败写回已回滚",
}

ACTIVE_RUNTIME_STATES = {"running", "retrying", "resuming_writeback"}
LLM_STATUS_SUCCESS_FRESH_SECONDS = int(os.environ.get("WEBNOVEL_LLM_STATUS_SUCCESS_FRESH_SECONDS", "1800"))
EXTERNAL_WORKFLOW_STEPS = {
    "init",
    "plan",
    "resume",
    "context",
    "draft",
    "consistency-review",
    "continuity-review",
    "ooc-review",
    "polish",
    "data-sync",
}
INVALID_OUTPUT_AUTO_RETRY_STEPS = {
    ("plan", "plan"),
    ("review", "consistency-review"),
    ("review", "continuity-review"),
    ("review", "ooc-review"),
    ("repair", "repair-draft"),
    ("repair", "consistency-review"),
    ("repair", "continuity-review"),
    ("write", "context"),
    ("write", "draft"),
    ("write", "polish"),
    ("write", "consistency-review"),
    ("write", "continuity-review"),
    ("write", "ooc-review"),
}
INVALID_OUTPUT_RECOVERABLE_PARSE_STAGES = {
    "json_invalid",
    "json_truncated",
    "json_truncated_repaired",
    "missing_required_keys",
}


class WritebackConsistencyError(ValueError):
    """Raised when writeback artifacts do not match the requested chapter target."""


class RepairTaskError(ValueError):
    """Raised when repair validation or repair review prevents progress."""

    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


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
        self.narrative_graph = NarrativeGraph(config=self.config, manager=self.index_manager)
        self._jobs: dict[str, asyncio.Task] = {}
        self._repair_project_layout()
        self._recover_or_mark_stale_running_tasks()

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        return [self._with_runtime_status(task) for task in self.store.list_tasks(limit=limit)]

    def list_task_summaries(self, limit: int = 50) -> List[Dict[str, Any]]:
        tasks = [self._with_runtime_status_summary(task) for task in self.store.list_tasks(limit=limit)]
        tasks.sort(
            key=lambda item: (
                int(item.get("list_priority") or 99),
                -(
                    (self._parse_iso_datetime(item.get("updated_at") or item.get("created_at")) or datetime.fromtimestamp(0, tz=timezone.utc)).timestamp()
                ),
            ),
        )
        return tasks

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        task = self.store.get_task(task_id)
        if task is None:
            return None
        return self._with_runtime_status(task)

    def get_task_detail(self, task_id: str, *, event_limit: int = 200) -> Optional[Dict[str, Any]]:
        task = self.get_task(task_id)
        if task is None:
            return None
        return {
            "task": task,
            "events": self.get_events(task_id, limit=event_limit),
        }

    def get_events(self, task_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        return self.store.get_events(task_id, limit=limit)

    def list_supervisor_recommendations(self, limit: int = 4, include_dismissed: bool = False) -> List[Dict[str, Any]]:
        tasks = [self._with_runtime_status(task) for task in self.store.list_tasks(limit=200)]
        tasks.sort(
            key=lambda item: self._parse_iso_datetime(item.get("updated_at") or item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        progress = (self._read_state_data().get("progress") or {})
        try:
            current_chapter = max(0, int(progress.get("current_chapter") or 0))
        except (TypeError, ValueError):
            current_chapter = 0

        items: List[Dict[str, Any]] = []

        pending_approval = next(
            (
                task
                for task in tasks
                if task.get("task_type") in {"write", "repair"} and task.get("status") == "awaiting_writeback_approval"
            ),
            None,
        )
        if pending_approval is not None:
            chapter = int((pending_approval.get("request") or {}).get("chapter") or 0)
            action = {"type": "open-task", "taskId": pending_approval["id"]}
            task_type = str(pending_approval.get("task_type") or "")
            detail = "不先处理这个审批，护栏推进无法安全往后继续。" if task_type == "write" else "修稿结果还未获批准，不会自动覆盖当前正文。"
            rationale = "人工审批是硬阻断，优先级高于继续创建任何新章节任务。" if task_type == "write" else "这是显式要求的人工确认步骤，处理后修稿任务才能继续落盘。"
            items.append(
                self._build_supervisor_item(
                    stable_key=f"approval:{pending_approval['id']}",
                    category="approval",
                    category_label="审批",
                    priority=10,
                    tone="warning",
                    badge="先处理",
                    title=f"第 {chapter or '-'} 章待回写审批",
                    summary="当前任务已经停在 approval-gate。",
                    detail=detail,
                    rationale=rationale,
                    source_task=pending_approval,
                    action=action,
                    action_label="打开待审批任务",
                    operator_actions=self._build_supervisor_operator_actions(
                        pending_approval,
                        action,
                        "打开待审批任务",
                    ),
                )
            )

        review_blocked = next(
            (
                task
                for task in tasks
                if task.get("task_type") == "write"
                and task.get("status") == "failed"
                and str((task.get("error") or {}).get("code") or "") == "REVIEW_GATE_BLOCKED"
            ),
            None,
        )
        if review_blocked is not None:
            chapter = int((review_blocked.get("request") or {}).get("chapter") or 0)
            action = {"type": "open-task", "taskId": review_blocked["id"]}
            items.append(
                self._build_supervisor_item(
                    stable_key=f"review:{review_blocked['id']}",
                    category="review_block",
                    category_label="审查阻断",
                    priority=20,
                    tone="danger",
                    badge="已阻断",
                    title=f"第 {chapter or '-'} 章被审查关卡拦截",
                    summary="当前章节存在 hard blocking issue。",
                    detail="先修复审查问题，再考虑继续下一章。",
                    rationale="审查硬阻断说明本章还不满足安全推进条件。",
                    source_task=review_blocked,
                    action=action,
                    action_label="打开阻断任务",
                    operator_actions=self._build_supervisor_operator_actions(
                        review_blocked,
                        action,
                        "打开阻断任务",
                    ),
                )
            )

        story_refresh_task = next(
            (
                task
                for task in tasks
                if task.get("task_type") == "write"
                and bool((((task.get("artifacts") or {}).get("writeback") or {}).get("story_refresh") or (task.get("artifacts") or {}).get("story_refresh") or {}).get("should_refresh"))
                and task.get("status") not in {"queued", "running", "awaiting_writeback_approval"}
            ),
            None,
        )
        if story_refresh_task is not None:
            chapter = int((story_refresh_task.get("request") or {}).get("chapter") or (current_chapter + 1) or 1)
            story_refresh_artifacts = story_refresh_task.get("artifacts") or {}
            story_refresh = (((story_refresh_artifacts.get("writeback") or {}).get("story_refresh") or story_refresh_artifacts.get("story_refresh") or {}))
            recommended_resume_from = str(story_refresh.get("recommended_resume_from") or "story-director")
            primary_action = {"type": "retry-story", "taskId": story_refresh_task["id"], "resumeFromStep": recommended_resume_from}
            secondary_action = {
                "type": "create-task",
                "taskType": "write",
                "payload": self._build_supervisor_task_payload(story_refresh_task, chapter),
            }
            items.append(
                self._build_supervisor_item(
                    stable_key=f"refresh:chapter:{chapter}",
                    category="story_refresh",
                    category_label="重规划",
                    priority=30,
                    tone="warning",
                    badge="建议重规划",
                    title=f"第 {chapter} 章前建议刷新 Story Plan",
                    summary="最近一章的 writeback 已明确建议从 story-director 重新规划。",
                    detail="先刷新多章滚动规划，再决定是否继续当前或下一章。",
                    rationale="这是叙事状态主动给出的刷新建议，优先级高于继续盲推章节。",
                    source_task=story_refresh_task,
                    action=primary_action,
                    action_label="从 Story Director 重试",
                    secondary_action=secondary_action,
                    secondary_label="创建当前章常规写作",
                    operator_actions=self._build_supervisor_operator_actions(
                        story_refresh_task,
                        primary_action,
                        "从 Story Director 重试",
                        secondary_action,
                        "创建当前章常规写作",
                    ),
                )
            )

        guarded_continue = next(
            (
                task
                for task in tasks
                if task.get("task_type") == "guarded-write"
                and self._is_supervisor_guarded_continue_candidate(task)
            ),
            None,
        )
        if guarded_continue is not None:
            guarded_result = self._get_supervisor_guarded_result(guarded_continue)
            next_chapter = int((guarded_result.get("next_action") or {}).get("next_chapter") or (current_chapter + 1) or 1)
            primary_action = {
                "type": "create-task",
                "taskType": "guarded-write",
                "payload": self._build_supervisor_task_payload(guarded_continue, next_chapter),
            }
            secondary_action = {"type": "open-task", "taskId": guarded_continue["id"]}
            items.append(
                self._build_supervisor_item(
                    stable_key=f"guarded-next:chapter:{next_chapter}",
                    category="guarded_continue",
                    category_label="继续推进",
                    priority=40,
                    tone="success",
                    badge="可继续",
                    title=f"第 {next_chapter} 章可以继续护栏推进",
                    summary=f"上一条护栏任务已安全完成第 {int(guarded_result.get('chapter') or 0) or '-'} 章。",
                    detail=str((guarded_result.get("next_action") or {}).get("suggested_action") or "可以继续一次只推进一章的护栏写作。"),
                    rationale="上一章没有触发新的 refresh 或审批阻断，当前是最安全的继续窗口。",
                    source_task=guarded_continue,
                    action=primary_action,
                    action_label="继续护栏推进下一章",
                    secondary_action=secondary_action,
                    secondary_label="打开护栏任务",
                    operator_actions=self._build_supervisor_operator_actions(
                        guarded_continue,
                        primary_action,
                        "继续护栏推进下一章",
                        secondary_action,
                        "打开护栏任务",
                    ),
                )
            )

        guarded_refresh = next(
            (
                task
                for task in tasks
                if task.get("task_type") in {"guarded-write", "guarded-batch-write"}
                and str((self._get_guarded_task_result(task).get("outcome") or "")) == "blocked_story_refresh"
            ),
            None,
        )
        if guarded_refresh is not None:
            guarded_result = self._get_guarded_task_result(guarded_refresh)
            operator_actions = list(guarded_result.get("operator_actions") or [])
            primary_action, primary_label, secondary_action, secondary_label = self._build_supervisor_action_contract_from_operator_actions(operator_actions)
            chapter = int((guarded_result.get("chapter") or guarded_result.get("start_chapter") or 0) or 0)
            is_batch = str(guarded_refresh.get("task_type") or "") == "guarded-batch-write"
            items.append(
                self._build_supervisor_item(
                    stable_key=f"guarded-refresh:{guarded_refresh['id']}",
                    category="guarded_story_refresh",
                    category_label="护栏重规划",
                    priority=35,
                    tone="warning",
                    badge="先重规划",
                    title=(f"第 {chapter or '-'} 章护栏推进建议先重规划" if not is_batch else f"护栏批量推进在第 {chapter or '-'} 章前建议先重规划"),
                    summary="护栏推进已经因为 story refresh 建议停止。",
                    detail=str((guarded_result.get("next_action") or {}).get("suggested_action") or "先重规划，再决定是否继续推进。"),
                    rationale="护栏流程已经显式给出 refresh 结论，恢复动作应以该结论为准。",
                    source_task=guarded_refresh,
                    action=primary_action,
                    action_label=primary_label or "从推荐步骤恢复",
                    secondary_action=secondary_action,
                    secondary_label=secondary_label,
                    operator_actions=operator_actions,
                )
            )

        guarded_batch_continue = next(
            (
                task
                for task in tasks
                if task.get("task_type") == "guarded-batch-write"
                and str((self._get_guarded_task_result(task).get("outcome") or "")) == "completed_requested_batch"
            ),
            None,
        )
        if guarded_batch_continue is not None:
            guarded_result = self._get_guarded_task_result(guarded_batch_continue)
            operator_actions = list(guarded_result.get("operator_actions") or [])
            primary_action, primary_label, secondary_action, secondary_label = self._build_supervisor_action_contract_from_operator_actions(operator_actions)
            next_chapter = int(((guarded_result.get("next_action") or {}).get("next_chapter") or 0) or 0)
            items.append(
                self._build_supervisor_item(
                    stable_key=f"guarded-batch-next:{guarded_batch_continue['id']}",
                    category="guarded_batch_continue",
                    category_label="继续批次",
                    priority=45,
                    tone="success",
                    badge="可继续",
                    title=f"护栏批量推进可从第 {next_chapter or '-'} 章继续下一批",
                    summary=f"上一批已完成 {int(guarded_result.get('completed_chapters') or 0)} 章。",
                    detail=str((guarded_result.get("next_action") or {}).get("suggested_action") or "可以继续下一批护栏推进。"),
                    rationale="当前批次已安全完成请求上限，适合显式发起下一批。",
                    source_task=guarded_batch_continue,
                    action=primary_action,
                    action_label=primary_label or "继续下一批护栏推进",
                    secondary_action=secondary_action,
                    secondary_label=secondary_label,
                    operator_actions=operator_actions,
                )
            )

        visible_items = self._apply_supervisor_dismissals(self._dedupe_supervisor_items(items), include_dismissed=include_dismissed)
        return visible_items[: max(1, int(limit or 4))]

    def dismiss_supervisor_recommendation(self, stable_key: str, fingerprint: str = "", *, reason: str = "", note: str = "") -> Dict[str, Any]:
        normalized_key = str(stable_key or "").strip()
        if not normalized_key:
            raise ValueError("stable_key is required")
        current_item = self._find_supervisor_item_by_key(normalized_key)
        normalized_fingerprint = str(fingerprint or normalized_key).strip() or normalized_key
        normalized_reason = str(reason or "").strip()
        normalized_note = str(note or "").strip()
        state = self._read_supervisor_state()
        dismissals = state.setdefault("dismissals", {})
        dismissed_at = datetime.now(timezone.utc).isoformat()
        dismissals[normalized_key] = {
            "fingerprint": normalized_fingerprint,
            "dismissed_at": dismissed_at,
            "reason": normalized_reason,
            "note": normalized_note,
        }
        self._write_supervisor_state(state)
        self._append_supervisor_audit_event(
            action="dismissed",
            stable_key=normalized_key,
            fingerprint=normalized_fingerprint,
            item=current_item,
            payload={
                "status_snapshot": "dismissed",
                "dismissal_reason": normalized_reason,
                "dismissal_note": normalized_note,
            },
        )
        return {
            "stableKey": normalized_key,
            "fingerprint": normalized_fingerprint,
            "dismissedAt": dismissed_at,
            "dismissalReason": normalized_reason,
            "dismissalNote": normalized_note,
            "dismissed": True,
        }

    def dismiss_supervisor_recommendations_batch(
        self,
        items: List[Dict[str, Any]],
        *,
        reason: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        updated: List[Dict[str, Any]] = []
        for item in items or []:
            stable_key = str((item or {}).get("stable_key") or "").strip()
            if not stable_key:
                continue
            updated.append(
                self.dismiss_supervisor_recommendation(
                    stable_key,
                    str((item or {}).get("fingerprint") or ""),
                    reason=reason,
                    note=note,
                )
            )
        return {"updated": updated, "count": len(updated)}

    def undismiss_supervisor_recommendation(self, stable_key: str) -> Dict[str, Any]:
        normalized_key = str(stable_key or "").strip()
        if not normalized_key:
            raise ValueError("stable_key is required")
        current_item = self._find_supervisor_item_by_key(normalized_key, include_dismissed=True)
        state = self._read_supervisor_state()
        dismissals = state.setdefault("dismissals", {})
        dismissals.pop(normalized_key, None)
        self._write_supervisor_state(state)
        self._append_supervisor_audit_event(
            action="undismissed",
            stable_key=normalized_key,
            fingerprint=str((current_item or {}).get("fingerprint") or normalized_key),
            item=current_item,
            payload={"status_snapshot": "open"},
        )
        return {
            "stableKey": normalized_key,
            "dismissed": False,
        }

    def undismiss_supervisor_recommendations_batch(self, stable_keys: List[str]) -> Dict[str, Any]:
        updated: List[Dict[str, Any]] = []
        for stable_key in stable_keys or []:
            normalized_key = str(stable_key or "").strip()
            if not normalized_key:
                continue
            updated.append(self.undismiss_supervisor_recommendation(normalized_key))
        return {"updated": updated, "count": len(updated)}

    def set_supervisor_recommendation_tracking(
        self,
        stable_key: str,
        fingerprint: str = "",
        *,
        status: str = "",
        note: str = "",
        linked_task_id: str = "",
        linked_checklist_path: str = "",
    ) -> Dict[str, Any]:
        normalized_key = str(stable_key or "").strip()
        if not normalized_key:
            raise ValueError("stable_key is required")
        normalized_status = self._normalize_supervisor_tracking_status(status)
        if not normalized_status:
            raise ValueError("status is required")
        normalized_fingerprint = str(fingerprint or normalized_key).strip() or normalized_key
        normalized_note = str(note or "").strip()
        normalized_linked_task_id = str(linked_task_id or "").strip()
        normalized_linked_checklist_path = str(linked_checklist_path or "").strip()
        updated_at = datetime.now(timezone.utc).isoformat()
        current_item = self._find_supervisor_item_by_key(normalized_key, include_dismissed=True)
        state = self._read_supervisor_state()
        tracking = state.setdefault("tracking", {})
        tracking[normalized_key] = {
            "fingerprint": normalized_fingerprint,
            "status": normalized_status,
            "note": normalized_note,
            "linked_task_id": normalized_linked_task_id,
            "linked_checklist_path": normalized_linked_checklist_path,
            "updated_at": updated_at,
        }
        self._write_supervisor_state(state)
        self._append_supervisor_audit_event(
            action="tracking_updated",
            stable_key=normalized_key,
            fingerprint=normalized_fingerprint,
            item=current_item,
            payload={
                "status_snapshot": normalized_status,
                "tracking_status": normalized_status,
                "tracking_note": normalized_note,
                "linked_task_id": normalized_linked_task_id,
                "linked_checklist_path": normalized_linked_checklist_path,
            },
            timestamp=updated_at,
        )
        return {
            "stableKey": normalized_key,
            "fingerprint": normalized_fingerprint,
            "trackingStatus": normalized_status,
            "trackingLabel": self._format_supervisor_tracking_label(normalized_status),
            "trackingNote": normalized_note,
            "linkedTaskId": normalized_linked_task_id,
            "linkedChecklistPath": normalized_linked_checklist_path,
            "trackingUpdatedAt": updated_at,
        }

    def clear_supervisor_recommendation_tracking(self, stable_key: str) -> Dict[str, Any]:
        normalized_key = str(stable_key or "").strip()
        if not normalized_key:
            raise ValueError("stable_key is required")
        current_item = self._find_supervisor_item_by_key(normalized_key, include_dismissed=True)
        state = self._read_supervisor_state()
        tracking = state.setdefault("tracking", {})
        tracking.pop(normalized_key, None)
        self._write_supervisor_state(state)
        self._append_supervisor_audit_event(
            action="tracking_cleared",
            stable_key=normalized_key,
            fingerprint=str((current_item or {}).get("fingerprint") or normalized_key),
            item=current_item,
            payload={"status_snapshot": "open"},
        )
        return {
            "stableKey": normalized_key,
            "trackingStatus": "",
            "trackingLabel": "",
            "trackingNote": "",
            "linkedTaskId": "",
            "linkedChecklistPath": "",
            "trackingUpdatedAt": None,
        }

    def save_supervisor_checklist(
        self,
        content: str,
        *,
        chapter: int = 0,
        selected_keys: Optional[List[str]] = None,
        category_filter: str = "all",
        sort_mode: str = "priority",
        title: str = "",
        note: str = "",
    ) -> Dict[str, Any]:
        normalized_content = str(content or "").strip()
        if not normalized_content:
            raise ValueError("content is required")
        try:
            normalized_chapter = max(0, int(chapter or 0))
        except (TypeError, ValueError):
            normalized_chapter = 0
        if normalized_chapter <= 0:
            progress = (self._read_state_data().get("progress") or {})
            try:
                normalized_chapter = max(0, int(progress.get("current_chapter") or 0))
            except (TypeError, ValueError):
                normalized_chapter = 0
        normalized_selected_keys = [str(item or "").strip() for item in (selected_keys or []) if str(item or "").strip()]
        saved_at = datetime.now(timezone.utc)
        path = self._supervisor_checklist_path(normalized_chapter, saved_at)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = self._build_supervisor_checklist_document(
            normalized_content,
            saved_at=saved_at,
            chapter=normalized_chapter,
            selected_keys=normalized_selected_keys,
            category_filter=str(category_filter or "all").strip() or "all",
            sort_mode=str(sort_mode or "priority").strip() or "priority",
            title=str(title or "").strip(),
            note=str(note or "").strip(),
        )
        path.write_text(document, encoding="utf-8")
        relative_path = path.relative_to(self.project_root).as_posix()
        self._append_supervisor_audit_event(
            action="checklist_saved",
            payload={
                "checklist_path": relative_path,
                "chapter": normalized_chapter,
                "title": str(title or "").strip(),
                "note": str(note or "").strip(),
                "selected_count": len(normalized_selected_keys),
            },
            timestamp=saved_at.isoformat(),
        )
        return {
            "savedAt": saved_at.isoformat(),
            "chapter": normalized_chapter,
            "filename": path.name,
            "path": str(path),
            "relativePath": relative_path,
            "selectedCount": len(normalized_selected_keys),
            "title": str(title or "").strip(),
            "note": str(note or "").strip(),
        }

    def list_supervisor_checklists(self, limit: int = 10) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for path in sorted(
            self._supervisor_checklists_dir().glob("checklist-ch*.md"),
            key=lambda candidate: candidate.stat().st_mtime if candidate.exists() else 0,
            reverse=True,
        )[: max(1, int(limit or 10))]:
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue
            parsed = self._parse_supervisor_checklist_document(content)
            stat = path.stat()
            saved_at = str(parsed.get("saved_at") or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat())
            items.append(
                {
                    "filename": path.name,
                    "path": str(path),
                    "relativePath": path.relative_to(self.project_root).as_posix(),
                    "chapter": int(parsed.get("chapter") or 0),
                    "savedAt": saved_at,
                    "categoryFilter": str(parsed.get("category_filter") or "all"),
                    "sortMode": str(parsed.get("sort_mode") or "priority"),
                    "selectedCount": int(parsed.get("selected_count") or 0),
                    "title": str(parsed.get("title") or "").strip(),
                    "note": str(parsed.get("note") or "").strip(),
                    "selectedKeys": parsed.get("selected_keys") or [],
                    "content": str(parsed.get("content") or ""),
                    "summary": self._build_supervisor_checklist_summary(str(parsed.get("content") or "")),
                }
            )
        return items

    def list_supervisor_audit_repair_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for path in sorted(
            self._supervisor_audit_repair_reports_dir().glob("repair-report-*.json"),
            key=lambda candidate: candidate.stat().st_mtime if candidate.exists() else 0,
            reverse=True,
        )[: max(1, int(limit or 10))]:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            summary = payload.get("summary") or {}
            items.append(
                {
                    "filename": path.name,
                    "path": str(path),
                    "relativePath": path.relative_to(self.project_root).as_posix(),
                    "generatedAt": str(payload.get("generatedAt") or "").strip(),
                    "changed": bool(payload.get("changed")),
                    "backupCreated": bool(payload.get("backupCreated")),
                    "backupPath": str(payload.get("backupPath") or "").strip(),
                    "auditLogPath": str(payload.get("auditLogPath") or SUPERVISOR_AUDIT_LOG_NAME).strip(),
                    "droppedCount": int(summary.get("dropped_count") or 0),
                    "rewrittenCount": int(summary.get("rewritten_count") or 0),
                    "manualReviewCount": int(summary.get("manual_review_count") or 0),
                    "keptCount": int(summary.get("kept_count") or 0),
                    "appliedCount": len(payload.get("appliedProposals") or []),
                    "skippedCount": len(payload.get("skippedManualReview") or []),
                    "content": payload,
                }
            )
        return items

    def list_supervisor_audit_log(self, limit: int = 200) -> List[Dict[str, Any]]:
        path = self._supervisor_audit_log_path()
        if not path.exists():
            return []
        items: List[Dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            normalized = self._normalize_supervisor_audit_event(payload)
            if normalized is not None:
                items.append(normalized)
            if len(items) >= max(1, int(limit or 200)):
                break
        return items

    def get_supervisor_audit_health(self, issue_limit: int = 20) -> Dict[str, Any]:
        path = self._supervisor_audit_log_path()
        if not path.exists():
            return {
                "healthy": True,
                "exists": False,
                "path": str(path),
                "relativePath": SUPERVISOR_AUDIT_LOG_NAME,
                "total_lines": 0,
                "nonempty_lines": 0,
                "valid_entries": 0,
                "issue_count": 0,
                "issueCounts": {},
                "schemaStateCounts": {},
                "schemaVersionCounts": {},
                "issues": [],
                "latestTimestamp": "",
                "earliestTimestamp": "",
            }

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return {
                "healthy": False,
                "exists": True,
                "path": str(path),
                "relativePath": SUPERVISOR_AUDIT_LOG_NAME,
                "total_lines": 0,
                "nonempty_lines": 0,
                "valid_entries": 0,
                "issue_count": 1,
                "issueCounts": {"read_error": 1},
                "schemaStateCounts": {},
                "schemaVersionCounts": {},
                "issues": [
                    {
                        "code": "read_error",
                        "severity": "danger",
                        "message": f"Failed to read audit log: {exc}",
                    }
                ],
                "latestTimestamp": "",
                "earliestTimestamp": "",
            }

        issue_cap = max(1, int(issue_limit or 20))
        issue_counts: Dict[str, int] = {}
        issues: List[Dict[str, Any]] = []
        schema_state_counts: Dict[str, int] = {}
        schema_version_counts: Dict[str, int] = {}
        valid_entries = 0
        nonempty_lines = 0
        earliest_dt: Optional[datetime] = None
        latest_dt: Optional[datetime] = None

        def _record_issue(code: str, severity: str, message: str, *, line_number: Optional[int] = None, preview: str = "") -> None:
            issue_counts[code] = int(issue_counts.get(code) or 0) + 1
            if len(issues) >= issue_cap:
                return
            item: Dict[str, Any] = {
                "code": code,
                "severity": severity,
                "message": message,
            }
            if line_number is not None:
                item["line"] = line_number
            if preview:
                item["preview"] = preview
            issues.append(item)

        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue
            nonempty_lines += 1
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                _record_issue(
                    "invalid_json",
                    "danger",
                    "Audit log line is not valid JSON.",
                    line_number=line_number,
                    preview=line[:200],
                )
                continue

            normalized = self._normalize_supervisor_audit_event(payload)
            if normalized is None:
                _record_issue(
                    "invalid_payload",
                    "danger",
                    "Audit log line is not a JSON object.",
                    line_number=line_number,
                    preview=line[:200],
                )
                continue

            valid_entries += 1
            schema_state = str(normalized.get("schemaState") or normalized.get("schema_state") or "").strip() or "unknown"
            schema_state_counts[schema_state] = int(schema_state_counts.get(schema_state) or 0) + 1
            schema_version = str(normalized.get("schemaVersion") or normalized.get("schema_version") or "").strip() or "unknown"
            schema_version_counts[schema_version] = int(schema_version_counts.get(schema_version) or 0) + 1

            timestamp = str(normalized.get("timestamp") or "").strip()
            parsed_timestamp = self._parse_iso_datetime(timestamp)
            if not timestamp:
                _record_issue("missing_timestamp", "warning", "Audit event is missing timestamp.", line_number=line_number)
            elif parsed_timestamp is None:
                _record_issue("invalid_timestamp", "warning", "Audit event timestamp is not a valid ISO datetime.", line_number=line_number, preview=timestamp)
            else:
                earliest_dt = parsed_timestamp if earliest_dt is None else min(earliest_dt, parsed_timestamp)
                latest_dt = parsed_timestamp if latest_dt is None else max(latest_dt, parsed_timestamp)

            if not str(normalized.get("action") or "").strip():
                _record_issue("missing_action", "warning", "Audit event is missing action.", line_number=line_number)
            if not str(normalized.get("stableKey") or normalized.get("stable_key") or "").strip():
                _record_issue("missing_stable_key", "warning", "Audit event is missing stableKey.", line_number=line_number)
            if schema_state == "future":
                _record_issue(
                    "future_schema",
                    "warning",
                    str(normalized.get("schemaWarning") or normalized.get("schema_warning") or "Audit event uses a future schema version."),
                    line_number=line_number,
                )

        return {
            "healthy": not issue_counts,
            "exists": True,
            "path": str(path),
            "relativePath": SUPERVISOR_AUDIT_LOG_NAME,
            "total_lines": len(lines),
            "nonempty_lines": nonempty_lines,
            "valid_entries": valid_entries,
            "issue_count": sum(issue_counts.values()),
            "issueCounts": issue_counts,
            "schemaStateCounts": schema_state_counts,
            "schemaVersionCounts": schema_version_counts,
            "issues": issues,
            "latestTimestamp": latest_dt.isoformat() if latest_dt else "",
            "earliestTimestamp": earliest_dt.isoformat() if earliest_dt else "",
        }

    def get_supervisor_audit_repair_preview(self, proposal_limit: int = 20) -> Dict[str, Any]:
        path = self._supervisor_audit_log_path()
        if not path.exists():
            return {
                "exists": False,
                "path": str(path),
                "relativePath": SUPERVISOR_AUDIT_LOG_NAME,
                "total_lines": 0,
                "nonempty_lines": 0,
                "repairable_count": 0,
                "manual_review_count": 0,
                "actionCounts": {},
                "proposals": [],
            }

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            return {
                "exists": True,
                "path": str(path),
                "relativePath": SUPERVISOR_AUDIT_LOG_NAME,
                "total_lines": 0,
                "nonempty_lines": 0,
                "repairable_count": 0,
                "manual_review_count": 1,
                "actionCounts": {"read_error": 1},
                "proposals": [
                    {
                        "line": None,
                        "action": "manual_review",
                        "severity": "danger",
                        "reason": f"Failed to read audit log: {exc}",
                        "issueCodes": ["read_error"],
                    }
                ],
            }

        proposal_cap = max(1, int(proposal_limit or 20))
        proposals: List[Dict[str, Any]] = []
        action_counts: Dict[str, int] = {}
        nonempty_lines = 0
        repairable_count = 0
        manual_review_count = 0

        def _push_proposal(item: Dict[str, Any]) -> None:
            nonlocal repairable_count, manual_review_count
            action = str(item.get("action") or "").strip() or "manual_review"
            action_counts[action] = int(action_counts.get(action) or 0) + 1
            if action in {"drop_line", "rewrite_normalized_event"}:
                repairable_count += 1
            else:
                manual_review_count += 1
            if len(proposals) < proposal_cap:
                proposals.append(item)

        for line_number, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue
            nonempty_lines += 1
            proposal = self._build_supervisor_audit_repair_proposal(raw_line, line_number)
            if proposal is not None:
                _push_proposal(proposal)

        return {
            "exists": True,
            "path": str(path),
            "relativePath": SUPERVISOR_AUDIT_LOG_NAME,
            "total_lines": len(lines),
            "nonempty_lines": nonempty_lines,
            "repairable_count": repairable_count,
            "manual_review_count": manual_review_count,
            "actionCounts": action_counts,
            "proposals": proposals,
        }

    def apply_supervisor_audit_repair(self, *, create_backup: bool = True) -> Dict[str, Any]:
        path = self._supervisor_audit_log_path()
        if not path.exists():
            return {
                "exists": False,
                "changed": False,
                "path": str(path),
                "relativePath": SUPERVISOR_AUDIT_LOG_NAME,
                "backupCreated": False,
                "backupPath": "",
                "reportCreated": False,
                "reportPath": "",
                "reportRelativePath": "",
                "total_lines": 0,
                "nonempty_lines": 0,
                "dropped_count": 0,
                "rewritten_count": 0,
                "manual_review_count": 0,
                "kept_count": 0,
            }

        lines = path.read_text(encoding="utf-8").splitlines()
        repaired_lines: List[str] = []
        applied_proposals: List[Dict[str, Any]] = []
        skipped_manual_review: List[Dict[str, Any]] = []
        nonempty_lines = 0
        dropped_count = 0
        rewritten_count = 0
        manual_review_count = 0
        kept_count = 0
        changed = False

        for line_number, raw_line in enumerate(lines, start=1):
            if not raw_line.strip():
                repaired_lines.append(raw_line)
                continue
            nonempty_lines += 1
            proposal = self._build_supervisor_audit_repair_proposal(raw_line, line_number)
            if proposal is None:
                kept_count += 1
                repaired_lines.append(raw_line)
                continue

            action = str(proposal.get("action") or "").strip()
            if action == "drop_line":
                dropped_count += 1
                changed = True
                applied_proposals.append(dict(proposal))
                continue
            if action == "rewrite_normalized_event":
                rewritten_count += 1
                changed = True
                applied_proposals.append(dict(proposal))
                repaired_lines.append(str(proposal.get("outputLine") or raw_line))
                continue

            manual_review_count += 1
            kept_count += 1
            skipped_manual_review.append(dict(proposal))
            repaired_lines.append(raw_line)

        backup_path = ""
        report_path = ""
        if changed:
            original_content = "\n".join(lines)
            if create_backup:
                backup_target = self._supervisor_audit_repair_backup_path()
                self._write_text_atomically(backup_target, original_content)
                backup_path = str(backup_target)
            self._write_text_atomically(path, "\n".join(repaired_lines))
        report_target = self._supervisor_audit_repair_report_path()
        report_payload = {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "auditLogPath": SUPERVISOR_AUDIT_LOG_NAME,
            "changed": changed,
            "backupCreated": bool(changed and create_backup and backup_path),
            "backupPath": backup_path,
            "summary": {
                "total_lines": len(lines),
                "nonempty_lines": nonempty_lines,
                "dropped_count": dropped_count,
                "rewritten_count": rewritten_count,
                "manual_review_count": manual_review_count,
                "kept_count": kept_count,
            },
            "appliedProposals": applied_proposals,
            "skippedManualReview": skipped_manual_review,
        }
        self._write_json_atomically(report_target, report_payload)
        report_path = str(report_target)

        return {
            "exists": True,
            "changed": changed,
            "path": str(path),
            "relativePath": SUPERVISOR_AUDIT_LOG_NAME,
            "backupCreated": bool(changed and create_backup and backup_path),
            "backupPath": backup_path,
            "reportCreated": True,
            "reportPath": report_path,
            "reportRelativePath": self._relative_project_path(report_target),
            "total_lines": len(lines),
            "nonempty_lines": nonempty_lines,
            "dropped_count": dropped_count,
            "rewritten_count": rewritten_count,
            "manual_review_count": manual_review_count,
            "kept_count": kept_count,
        }

    def _build_supervisor_audit_repair_proposal(self, raw_line: str, line_number: int) -> Optional[Dict[str, Any]]:
        line = str(raw_line or "").strip()
        if not line:
            return None
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return {
                "line": line_number,
                "action": "drop_line",
                "severity": "danger",
                "reason": "Line is not valid JSON and cannot be normalized.",
                "issueCodes": ["invalid_json"],
                "preview": line[:200],
            }

        normalized = self._normalize_supervisor_audit_event(payload)
        if normalized is None:
            return {
                "line": line_number,
                "action": "drop_line",
                "severity": "danger",
                "reason": "Line is not a JSON object and cannot be normalized.",
                "issueCodes": ["invalid_payload"],
                "preview": line[:200],
            }

        issue_codes: List[str] = []
        timestamp = str(normalized.get("timestamp") or "").strip()
        if not timestamp:
            issue_codes.append("missing_timestamp")
        elif self._parse_iso_datetime(timestamp) is None:
            issue_codes.append("invalid_timestamp")
        if not str(normalized.get("action") or "").strip():
            issue_codes.append("missing_action")
        if not str(normalized.get("stableKey") or normalized.get("stable_key") or "").strip():
            issue_codes.append("missing_stable_key")

        schema_state = str(normalized.get("schemaState") or normalized.get("schema_state") or "").strip()
        if schema_state == "future":
            issue_codes.append("future_schema")

        if issue_codes:
            return {
                "line": line_number,
                "action": "manual_review",
                "severity": "warning" if "future_schema" in issue_codes else "danger",
                "reason": "Event has fields that require manual review before any repair.",
                "issueCodes": issue_codes,
                "stableKey": str(normalized.get("stableKey") or ""),
                "schemaVersion": normalized.get("schemaVersion"),
            }

        if schema_state == "legacy":
            proposed_event = self._build_supervisor_audit_canonical_event(normalized)
            return {
                "line": line_number,
                "action": "rewrite_normalized_event",
                "severity": "warning",
                "reason": "Legacy aliases or missing schema declaration would be rewritten to canonical fields.",
                "issueCodes": ["legacy_schema"],
                "stableKey": str(normalized.get("stableKey") or ""),
                "schemaVersion": normalized.get("schemaVersion"),
                "proposedEvent": proposed_event,
                "outputLine": json.dumps(proposed_event, ensure_ascii=False),
            }
        return None

    def _build_supervisor_audit_canonical_event(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        canonical_rewrite_keys = [
            "schema_version",
            "timestamp",
            "action",
            "stableKey",
            "fingerprint",
            "chapter",
            "category",
            "categoryLabel",
            "priority",
            "tone",
            "badge",
            "title",
            "summary",
            "detail",
            "rationale",
            "actionLabel",
            "secondaryLabel",
            "sourceTaskId",
            "linkedTaskId",
            "linkedChecklistPath",
            "checklist_path",
            "status_snapshot",
            "dismissal_reason",
            "dismissal_note",
            "tracking_note",
            "selected_count",
            "note",
        ]
        return {
            key: normalized[key]
            for key in canonical_rewrite_keys
            if key in normalized and normalized.get(key) not in (None, "")
        }

    def _supervisor_audit_repair_backup_path(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        return self._supervisor_audit_log_path().with_name(f"audit-log-repair-{timestamp}.jsonl.bak")

    def _supervisor_audit_repair_reports_dir(self) -> Path:
        return self.project_root / SUPERVISOR_AUDIT_REPAIR_REPORTS_DIR_NAME

    def _supervisor_audit_repair_report_path(self) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        return self._supervisor_audit_repair_reports_dir() / f"repair-report-{timestamp}.json"

    def _write_text_atomically(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            os.replace(str(tmp_path), str(path))
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def _write_json_atomically(self, path: Path, payload: Dict[str, Any]) -> None:
        self._write_text_atomically(path, json.dumps(payload, ensure_ascii=False, indent=2))

    def _build_supervisor_item(
        self,
        *,
        stable_key: str,
        category: str,
        category_label: str,
        priority: int,
        tone: str,
        badge: str,
        title: str,
        summary: str,
        detail: str,
        rationale: str,
        source_task: Dict[str, Any],
        action: Dict[str, Any],
        action_label: str,
        secondary_action: Optional[Dict[str, Any]] = None,
        secondary_label: Optional[str] = None,
        operator_actions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        item = {
            "stableKey": stable_key,
            "category": category,
            "categoryLabel": category_label,
            "priority": priority,
            "tone": tone,
            "badge": badge,
            "title": title,
            "summary": summary,
            "detail": detail,
            "rationale": rationale,
            "sourceTaskId": source_task.get("id"),
            "sourceUpdatedAt": source_task.get("updated_at") or source_task.get("created_at"),
            "fingerprint": self._build_supervisor_fingerprint(stable_key, source_task),
            "action": action,
            "actionLabel": action_label,
            "secondaryAction": secondary_action,
            "secondaryLabel": secondary_label,
        }
        if operator_actions is not None:
            item["operator_actions"] = operator_actions
        return item

    def _build_supervisor_fingerprint(self, stable_key: str, task: Dict[str, Any]) -> str:
        error = task.get("error") or {}
        return "|".join(
            [
                stable_key,
                str(task.get("id") or ""),
                str(task.get("status") or ""),
                str(task.get("updated_at") or ""),
                str(error.get("code") or ""),
                str(task.get("approval_status") or ""),
            ]
        )

    def _dedupe_supervisor_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        deduped: Dict[str, Dict[str, Any]] = {}
        for item in items:
            stable_key = str(item.get("stableKey") or "")
            if not stable_key:
                continue
            existing = deduped.get(stable_key)
            if existing is None:
                deduped[stable_key] = item
                continue
            existing_priority = int(existing.get("priority") or 999)
            current_priority = int(item.get("priority") or 999)
            if current_priority < existing_priority:
                deduped[stable_key] = item
                continue
            existing_ts = self._parse_iso_datetime(existing.get("sourceUpdatedAt")) or datetime.min.replace(tzinfo=timezone.utc)
            current_ts = self._parse_iso_datetime(item.get("sourceUpdatedAt")) or datetime.min.replace(tzinfo=timezone.utc)
            if current_priority == existing_priority and current_ts > existing_ts:
                deduped[stable_key] = item
        values = list(deduped.values())
        values.sort(
            key=lambda item: (
                int(item.get("priority") or 999),
                -int((self._parse_iso_datetime(item.get("sourceUpdatedAt")) or datetime.min.replace(tzinfo=timezone.utc)).timestamp()),
            )
        )
        return values

    def _supervisor_state_path(self) -> Path:
        return self.project_root / SUPERVISOR_DIR_NAME / "state.json"

    def _supervisor_checklists_dir(self) -> Path:
        return self.project_root / SUPERVISOR_CHECKLISTS_DIR_NAME

    def _supervisor_audit_log_path(self) -> Path:
        return self.project_root / SUPERVISOR_AUDIT_LOG_NAME

    def _supervisor_checklist_path(self, chapter: int, saved_at: datetime) -> Path:
        return self._supervisor_checklists_dir() / f"checklist-ch{max(0, int(chapter or 0)):04d}-{saved_at.strftime('%Y%m%d-%H%M%S-%f')}.md"

    def _find_supervisor_item_by_key(self, stable_key: str, *, include_dismissed: bool = True) -> Optional[Dict[str, Any]]:
        normalized_key = str(stable_key or "").strip()
        if not normalized_key:
            return None
        items = self.list_supervisor_recommendations(limit=200, include_dismissed=include_dismissed)
        return next((item for item in items if str(item.get("stableKey") or "").strip() == normalized_key), None)

    def _append_supervisor_audit_event(
        self,
        *,
        action: str,
        stable_key: str = "",
        fingerprint: str = "",
        item: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> None:
        event = {
            "schema_version": SUPERVISOR_AUDIT_SCHEMA_VERSION,
            "timestamp": str(timestamp or datetime.now(timezone.utc).isoformat()),
            "action": str(action or "").strip(),
            "stableKey": str(stable_key or "").strip(),
            "fingerprint": str(fingerprint or "").strip(),
        }
        if isinstance(item, dict) and item:
            event.update(
                {
                    "chapter": self._extract_supervisor_chapter_number(item),
                    "category": str(item.get("category") or "").strip(),
                    "categoryLabel": str(item.get("categoryLabel") or "").strip(),
                    "priority": int(item.get("priority") or 0),
                    "tone": str(item.get("tone") or "").strip(),
                    "badge": str(item.get("badge") or "").strip(),
                    "title": str(item.get("title") or "").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                    "detail": str(item.get("detail") or "").strip(),
                    "rationale": str(item.get("rationale") or "").strip(),
                    "actionLabel": str(item.get("actionLabel") or "").strip(),
                    "secondaryLabel": str(item.get("secondaryLabel") or "").strip(),
                    "sourceTaskId": str(item.get("sourceTaskId") or "").strip(),
                    "linkedTaskId": str(item.get("linkedTaskId") or "").strip(),
                    "linkedChecklistPath": str(item.get("linkedChecklistPath") or "").strip(),
                }
            )
        if isinstance(payload, dict) and payload:
            event.update(payload)
        path = self._supervisor_audit_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _normalize_supervisor_audit_event(self, payload: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        normalized = dict(payload)
        try:
            schema_version = int(payload.get("schema_version") or payload.get("schemaVersion") or 1)
        except (TypeError, ValueError):
            schema_version = 1
        declared_schema = "schema_version" in payload or "schemaVersion" in payload
        uses_legacy_aliases = any(
            key in payload
            for key in (
                "stable_key",
                "source_task_id",
                "linked_task_id",
                "linked_checklist_path",
                "category_label",
            )
        )
        schema_state = "supported"
        schema_warning = ""
        if schema_version > SUPERVISOR_AUDIT_MAX_SUPPORTED_SCHEMA_VERSION:
            schema_state = "future"
            schema_warning = (
                f"Detected audit schema v{schema_version}; current compatibility is only verified "
                f"through v{SUPERVISOR_AUDIT_MAX_SUPPORTED_SCHEMA_VERSION}."
            )
        elif uses_legacy_aliases or not declared_schema:
            schema_state = "legacy"
        normalized["schema_version"] = schema_version
        normalized["schemaVersion"] = schema_version
        normalized["schema_state"] = schema_state
        normalized["schemaState"] = schema_state
        normalized["schema_supported"] = schema_state != "future"
        normalized["schemaSupported"] = schema_state != "future"
        normalized["schema_warning"] = schema_warning
        normalized["schemaWarning"] = schema_warning

        def _mirror_text_field(camel_key: str, snake_key: str) -> None:
            value = str(payload.get(camel_key) or payload.get(snake_key) or "").strip()
            if not value:
                return
            normalized[camel_key] = value
            normalized[snake_key] = value

        _mirror_text_field("stableKey", "stable_key")
        _mirror_text_field("sourceTaskId", "source_task_id")
        _mirror_text_field("linkedTaskId", "linked_task_id")
        _mirror_text_field("linkedChecklistPath", "linked_checklist_path")
        _mirror_text_field("categoryLabel", "category_label")

        if normalized.get("linkedChecklistPath"):
            normalized["checklist_path"] = normalized["linkedChecklistPath"]
        elif payload.get("checklist_path"):
            normalized["checklist_path"] = str(payload.get("checklist_path") or "").strip()
            if normalized["checklist_path"]:
                normalized["linkedChecklistPath"] = normalized["checklist_path"]
                normalized["linked_checklist_path"] = normalized["checklist_path"]

        normalized["timestamp"] = str(payload.get("timestamp") or "").strip()
        normalized["action"] = str(payload.get("action") or "").strip()
        normalized["fingerprint"] = str(payload.get("fingerprint") or "").strip()
        normalized["category"] = str(payload.get("category") or "").strip()
        normalized["categoryLabel"] = str(payload.get("categoryLabel") or payload.get("category_label") or "").strip()
        normalized["status_snapshot"] = str(payload.get("status_snapshot") or "").strip()
        return normalized

    def _extract_supervisor_chapter_number(self, item: Dict[str, Any]) -> int:
        title = str((item or {}).get("title") or "")
        matched = re.search(r"第\s*(\d+)\s*章", title)
        if matched:
            try:
                return int(matched.group(1))
            except (TypeError, ValueError):
                return 0
        return 0

    def _build_supervisor_checklist_document(
        self,
        content: str,
        *,
        saved_at: datetime,
        chapter: int,
        selected_keys: List[str],
        category_filter: str,
        sort_mode: str,
        title: str,
        note: str,
    ) -> str:
        lines = [
            "---",
            f"saved_at: {saved_at.isoformat()}",
            f"chapter: {max(0, int(chapter or 0))}",
            f"category_filter: {category_filter}",
            f"sort_mode: {sort_mode}",
            f"selected_count: {len(selected_keys)}",
            f"title: {json.dumps(str(title or '').strip(), ensure_ascii=False)}",
            f"note: {json.dumps(str(note or '').strip(), ensure_ascii=False)}",
        ]
        if selected_keys:
            lines.append("selected_keys:")
            for key in selected_keys:
                lines.append(f"  - {json.dumps(key, ensure_ascii=False)}")
        else:
            lines.append("selected_keys: []")
        lines.extend(["---", "", str(content or "").strip(), ""])
        return "\n".join(lines)

    def _parse_supervisor_checklist_document(self, content: str) -> Dict[str, Any]:
        text = str(content or "")
        if not text.startswith("---\n"):
            return {"content": text.strip()}
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {"content": text.strip()}
        metadata: Dict[str, Any] = {}
        body_start = 0
        index = 1
        while index < len(lines):
            raw_line = lines[index]
            stripped = raw_line.strip()
            if stripped == "---":
                body_start = index + 1
                break
            if raw_line.startswith("selected_keys:"):
                values: List[str] = []
                index += 1
                while index < len(lines):
                    entry = lines[index]
                    if not entry.startswith("  - "):
                        index -= 1
                        break
                    payload = entry[4:].strip()
                    try:
                        values.append(json.loads(payload))
                    except json.JSONDecodeError:
                        values.append(payload.strip('"'))
                    index += 1
                metadata["selected_keys"] = values
            elif ":" in raw_line:
                key, value = raw_line.split(":", 1)
                normalized_key = key.strip()
                normalized_value = value.strip()
                if normalized_key in {"title", "note"}:
                    try:
                        metadata[normalized_key] = json.loads(normalized_value)
                    except json.JSONDecodeError:
                        metadata[normalized_key] = normalized_value.strip('"')
                else:
                    metadata[normalized_key] = normalized_value
            index += 1
        else:
            body_start = len(lines)

        metadata["content"] = "\n".join(lines[body_start:]).strip()
        return metadata

    def _build_supervisor_checklist_summary(self, content: str) -> str:
        for line in str(content or "").splitlines():
            normalized = line.strip()
            if normalized and not normalized.startswith("#"):
                return normalized[:140]
        return "已保存的 Supervisor 清单"

    def _read_supervisor_state(self) -> Dict[str, Any]:
        path = self._supervisor_state_path()
        if not path.exists():
            return {"dismissals": {}, "tracking": {}}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {"dismissals": {}, "tracking": {}}
        dismissals = payload.get("dismissals") if isinstance(payload, dict) else {}
        tracking = payload.get("tracking") if isinstance(payload, dict) else {}
        return {
            "dismissals": dismissals if isinstance(dismissals, dict) else {},
            "tracking": tracking if isinstance(tracking, dict) else {},
        }

    def _write_supervisor_state(self, state: Dict[str, Any]) -> None:
        path = self._supervisor_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "dismissals": state.get("dismissals") if isinstance(state.get("dismissals"), dict) else {},
            "tracking": state.get("tracking") if isinstance(state.get("tracking"), dict) else {},
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _apply_supervisor_dismissals(self, items: List[Dict[str, Any]], *, include_dismissed: bool = False) -> List[Dict[str, Any]]:
        state = self._read_supervisor_state()
        dismissals = state.get("dismissals") or {}
        tracking = state.get("tracking") or {}
        next_dismissals = dict(dismissals) if isinstance(dismissals, dict) else {}
        next_tracking = dict(tracking) if isinstance(tracking, dict) else {}
        state_changed = False
        visible_items: List[Dict[str, Any]] = []

        for item in items:
            stable_key = str(item.get("stableKey") or "").strip()
            fingerprint = str(item.get("fingerprint") or stable_key).strip() or stable_key
            dismissal = dismissals.get(stable_key) if stable_key else None
            dismissed = False
            dismissed_at = None
            dismissed_reason = ""
            dismissed_note = ""
            tracking_status = ""
            tracking_label = ""
            tracking_note = ""
            linked_task_id = ""
            linked_checklist_path = ""
            tracking_updated_at = None
            if isinstance(dismissal, dict):
                dismissed = str(dismissal.get("fingerprint") or "").strip() == fingerprint
                dismissed_at = dismissal.get("dismissed_at") if dismissed else None
                dismissed_reason = str(dismissal.get("reason") or "").strip() if dismissed else ""
                dismissed_note = str(dismissal.get("note") or "").strip() if dismissed else ""
                if dismissal.get("fingerprint") and not dismissed:
                    next_dismissals.pop(stable_key, None)
                    state_changed = True
            elif stable_key and stable_key in next_dismissals:
                next_dismissals.pop(stable_key, None)
                state_changed = True

            tracking_entry = tracking.get(stable_key) if stable_key else None
            if isinstance(tracking_entry, dict):
                entry_matches = str(tracking_entry.get("fingerprint") or "").strip() == fingerprint
                normalized_status = self._normalize_supervisor_tracking_status(tracking_entry.get("status"))
                if entry_matches and normalized_status:
                    tracking_status = normalized_status
                    tracking_label = self._format_supervisor_tracking_label(normalized_status)
                    tracking_note = str(tracking_entry.get("note") or "").strip()
                    linked_task_id = str(tracking_entry.get("linked_task_id") or "").strip()
                    linked_checklist_path = str(tracking_entry.get("linked_checklist_path") or "").strip()
                    tracking_updated_at = tracking_entry.get("updated_at")
                elif tracking_entry.get("fingerprint") and not entry_matches:
                    next_tracking.pop(stable_key, None)
                    state_changed = True
            elif stable_key and stable_key in next_tracking:
                next_tracking.pop(stable_key, None)
                state_changed = True

            enriched = dict(item)
            enriched["dismissed"] = dismissed
            enriched["dismissedAt"] = dismissed_at
            enriched["dismissalReason"] = dismissed_reason
            enriched["dismissalNote"] = dismissed_note
            enriched["trackingStatus"] = tracking_status
            enriched["trackingLabel"] = tracking_label
            enriched["trackingNote"] = tracking_note
            enriched["linkedTaskId"] = linked_task_id
            enriched["linkedChecklistPath"] = linked_checklist_path
            enriched["trackingUpdatedAt"] = tracking_updated_at
            if include_dismissed or not dismissed:
                visible_items.append(enriched)

        if state_changed:
            self._write_supervisor_state({"dismissals": next_dismissals, "tracking": next_tracking})

        return visible_items

    def _normalize_supervisor_tracking_status(self, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        return normalized if normalized in {"in_progress", "completed"} else ""

    def _format_supervisor_tracking_label(self, status: str) -> str:
        return {
            "in_progress": "处理中",
            "completed": "已处理",
        }.get(str(status or "").strip(), "")

    def _get_supervisor_guarded_result(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return self._get_guarded_task_result(task)

    def _is_supervisor_guarded_continue_candidate(self, task: Dict[str, Any]) -> bool:
        guarded_result = self._get_supervisor_guarded_result(task)
        if not guarded_result:
            return False
        if str(guarded_result.get("outcome") or "") != "completed_one_chapter":
            return False
        next_action = guarded_result.get("next_action") or {}
        return bool(next_action.get("can_enqueue_next"))

    def _build_supervisor_task_payload(self, task: Dict[str, Any], chapter: int) -> Dict[str, Any]:
        request = task.get("request") or {}
        return {
            "chapter": max(1, int(chapter or 1)),
            "mode": str(request.get("mode") or "standard"),
            "require_manual_approval": bool(request.get("require_manual_approval", True)),
            "project_root": str(request.get("project_root") or self.project_root),
            "options": request.get("options") if isinstance(request.get("options"), dict) else {},
        }

    def _build_guarded_batch_task_payload(self, task: Dict[str, Any], start_chapter: int) -> Dict[str, Any]:
        request = task.get("request") or {}
        return {
            "start_chapter": max(1, int(start_chapter or 1)),
            "max_chapters": max(1, int(request.get("max_chapters") or 1)),
            "mode": str(request.get("mode") or "standard"),
            "require_manual_approval": bool(request.get("require_manual_approval", True)),
            "project_root": str(request.get("project_root") or self.project_root),
            "options": request.get("options") if isinstance(request.get("options"), dict) else {},
        }

    def _get_guarded_task_result(self, task: Dict[str, Any]) -> Dict[str, Any]:
        artifacts = task.get("artifacts") or {}
        if str(task.get("task_type") or "") == "guarded-batch-write":
            guarded = artifacts.get("guarded_batch_runner")
            if isinstance(guarded, dict) and guarded:
                return guarded
            step_results = artifacts.get("step_results") or {}
            step_payload = ((step_results.get("guarded-batch-runner") or {}).get("structured_output") or {})
            return step_payload if isinstance(step_payload, dict) else {}
        guarded = artifacts.get("guarded_runner")
        if isinstance(guarded, dict) and guarded:
            return guarded
        step_results = artifacts.get("step_results") or {}
        step_payload = ((step_results.get("guarded-chapter-runner") or {}).get("structured_output") or {})
        return step_payload if isinstance(step_payload, dict) else {}

    def _build_legacy_action_from_operator_action(self, action: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        kind = str(action.get("kind") or "").strip()
        if kind in {"open-task", "open-blocked-task"} and action.get("task_id"):
            return {"type": "open-task", "taskId": str(action["task_id"])}
        if kind == "retry-task" and action.get("task_id"):
            payload = {"type": "retry-story", "taskId": str(action["task_id"])}
            if action.get("resume_from_step"):
                payload["resumeFromStep"] = str(action["resume_from_step"])
            return payload
        if kind == "launch-task" and action.get("task_type") and isinstance(action.get("payload"), dict):
            return {
                "type": "create-task",
                "taskType": str(action["task_type"]),
                "payload": action["payload"],
            }
        return None

    def _build_supervisor_action_contract_from_operator_actions(
        self,
        operator_actions: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, Any], str, Optional[Dict[str, Any]], Optional[str]]:
        primary_action: Dict[str, Any] = {}
        primary_label = ""
        secondary_action: Optional[Dict[str, Any]] = None
        secondary_label: Optional[str] = None
        valid_actions = [item for item in operator_actions if isinstance(item, dict)]
        if valid_actions:
            first_legacy = self._build_legacy_action_from_operator_action(valid_actions[0]) or {}
            primary_action = first_legacy
            primary_label = str(valid_actions[0].get("label") or "")
        if len(valid_actions) > 1:
            second_legacy = self._build_legacy_action_from_operator_action(valid_actions[1])
            if second_legacy is not None:
                secondary_action = second_legacy
                secondary_label = str(valid_actions[1].get("label") or "")
        return primary_action, primary_label, secondary_action, secondary_label

    def _build_operator_action(
        self,
        action_id: str,
        kind: str,
        label: str,
        *,
        variant: str = "secondary",
        task_id: Optional[str] = None,
        task_type: Optional[str] = None,
        resume_from_step: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        disabled: bool = False,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        action = {
            "id": str(action_id or kind or "operator-action"),
            "kind": str(kind or "").strip(),
            "label": str(label or "").strip(),
            "variant": str(variant or "secondary").strip() or "secondary",
        }
        if task_id:
            action["task_id"] = str(task_id)
        if task_type:
            action["task_type"] = str(task_type)
        if resume_from_step:
            action["resume_from_step"] = str(resume_from_step)
        if isinstance(payload, dict) and payload:
            action["payload"] = payload
        if disabled:
            action["disabled"] = True
        if reason:
            action["reason"] = str(reason)
        return action

    def _build_operator_action_from_task_action(
        self,
        *,
        action: Dict[str, Any],
        label: str,
        variant: str,
        source_task: Dict[str, Any],
        suffix: str,
    ) -> Optional[Dict[str, Any]]:
        action_type = str(action.get("type") or "").strip()
        source_task_id = str(source_task.get("id") or "")
        if action_type == "open-task":
            return self._build_operator_action(
                f"{action_type}:{source_task_id}:{suffix}",
                "open-task",
                label,
                variant=variant,
                task_id=str(action.get("taskId") or ""),
            )
        if action_type == "retry-story":
            return self._build_operator_action(
                f"{action_type}:{source_task_id}:{suffix}",
                "retry-task",
                label,
                variant=variant,
                task_id=str(action.get("taskId") or ""),
                resume_from_step=str(action.get("resumeFromStep") or action.get("resume_from_step") or "story-director"),
            )
        if action_type == "create-task":
            payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
            return self._build_operator_action(
                f"{action_type}:{source_task_id}:{suffix}",
                "launch-task",
                label,
                variant=variant,
                task_type=str(action.get("taskType") or ""),
                payload=payload,
            )
        return None

    def _build_supervisor_operator_actions(
        self,
        source_task: Dict[str, Any],
        primary_action: Dict[str, Any],
        primary_label: str,
        secondary_action: Optional[Dict[str, Any]] = None,
        secondary_label: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        primary = self._build_operator_action_from_task_action(
            action=primary_action,
            label=primary_label,
            variant="primary",
            source_task=source_task,
            suffix="primary",
        )
        if primary is not None:
            actions.append(primary)
        if secondary_action and secondary_label:
            secondary = self._build_operator_action_from_task_action(
                action=secondary_action,
                label=secondary_label,
                variant="secondary",
                source_task=source_task,
                suffix="secondary",
            )
            if secondary is not None:
                actions.append(secondary)
        return actions

    def _build_guarded_runner_operator_actions(
        self,
        *,
        task_id: str,
        chapter: int,
        outcome: str,
        child_task_id: Optional[str],
        next_action: Dict[str, Any],
        request: Dict[str, Any],
        child_task_status: Optional[str] = None,
        blocking_reason: str = "",
        resume_from_step: str = "story-director",
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        next_chapter = int(next_action.get("next_chapter") or (chapter + 1))
        followup_request = {
            "chapter": next_chapter,
            "mode": str(request.get("mode") or "standard"),
            "require_manual_approval": bool(request.get("require_manual_approval", True)),
            "project_root": str(request.get("project_root") or self.project_root),
            "options": request.get("options") if isinstance(request.get("options"), dict) else {},
        }
        current_request = {
            "chapter": chapter,
            "mode": str(request.get("mode") or "standard"),
            "require_manual_approval": bool(request.get("require_manual_approval", True)),
            "project_root": str(request.get("project_root") or self.project_root),
            "options": request.get("options") if isinstance(request.get("options"), dict) else {},
        }

        if outcome == "completed_one_chapter" and bool(next_action.get("can_enqueue_next")):
            actions.append(
                self._build_operator_action(
                    f"guarded:{task_id}:continue-guarded",
                    "launch-task",
                    "继续下一章护栏推进",
                    variant="primary",
                    task_type="guarded-write",
                    payload=followup_request,
                )
            )
            actions.append(
                self._build_operator_action(
                    f"guarded:{task_id}:create-write",
                    "launch-task",
                    "创建下一章常规写作",
                    variant="secondary",
                    task_type="write",
                    payload=followup_request,
                )
            )
            if child_task_id:
                actions.append(self._build_operator_action(f"guarded:{task_id}:open-child", "open-task", "查看子任务", variant="secondary", task_id=child_task_id, reason=blocking_reason or None))
            return actions

        if outcome == "blocked_story_refresh":
            actions.append(
                self._build_operator_action(
                    f"guarded:{task_id}:retry-story",
                    "retry-task",
                    "从 Story Director 重试当前任务",
                    variant="primary",
                    task_id=child_task_id or task_id,
                    resume_from_step=resume_from_step,
                    reason=blocking_reason or None,
                )
            )
            actions.append(
                self._build_operator_action(
                    f"guarded:{task_id}:create-write",
                    "launch-task",
                    "创建当前章常规写作",
                    variant="secondary",
                    task_type="write",
                    payload=current_request,
                )
            )
            if child_task_id:
                actions.append(self._build_operator_action(f"guarded:{task_id}:open-child", "open-task", "查看子任务", variant="secondary", task_id=child_task_id, reason=blocking_reason or None))
            return actions

        if outcome in {"blocked_by_review", "stopped_for_approval", "child_task_failed"}:
            if child_task_id:
                actions.append(self._build_operator_action(f"guarded:{task_id}:open-child", "open-task", "查看子任务", variant="secondary", task_id=child_task_id, reason=blocking_reason or None))
            return actions

        if blocking_reason:
            actions.append(
                self._build_operator_action(
                    f"guarded:{task_id}:continue",
                    "launch-task",
                    "继续推进",
                    variant="secondary",
                    disabled=True,
                    reason=blocking_reason,
                )
            )
        return actions

    def _build_guarded_batch_operator_actions(
        self,
        *,
        task_id: str,
        start_chapter: int,
        completed_chapters: int,
        requested_max_chapters: int,
        outcome: str,
        last_child_task_id: Optional[str],
        next_action: Dict[str, Any],
        request: Dict[str, Any],
        blocking_reason: str = "",
        resume_from_step: str = "story-director",
    ) -> List[Dict[str, Any]]:
        actions: List[Dict[str, Any]] = []
        next_chapter = int(next_action.get("next_chapter") or (start_chapter + completed_chapters))
        followup_batch_request = {
            "start_chapter": next_chapter,
            "max_chapters": max(1, int(request.get("max_chapters") or requested_max_chapters or 1)),
            "mode": str(request.get("mode") or "standard"),
            "require_manual_approval": bool(request.get("require_manual_approval", True)),
            "project_root": str(request.get("project_root") or self.project_root),
            "options": request.get("options") if isinstance(request.get("options"), dict) else {},
        }

        if outcome == "completed_requested_batch":
            actions.insert(
                0,
                self._build_operator_action(
                    f"guarded-batch:{task_id}:continue-batch",
                    "launch-task",
                    "继续下一批护栏推进",
                    variant="primary",
                    task_type="guarded-batch-write",
                    payload=followup_batch_request,
                ),
            )
            if last_child_task_id:
                actions.append(self._build_operator_action(f"guarded-batch:{task_id}:open-last-child", "open-task", "查看最后子任务", variant="secondary", task_id=last_child_task_id, reason=blocking_reason or None))
            return actions

        if outcome == "blocked_story_refresh":
            actions.insert(
                0,
                self._build_operator_action(
                    f"guarded-batch:{task_id}:retry-story",
                    "retry-task",
                    "从 Story Director 重试最后子任务",
                    variant="primary",
                    task_id=last_child_task_id,
                    resume_from_step=resume_from_step,
                    reason=blocking_reason or None,
                ),
            )
            if last_child_task_id:
                actions.append(self._build_operator_action(f"guarded-batch:{task_id}:open-last-child", "open-task", "查看最后子任务", variant="secondary", task_id=last_child_task_id, reason=blocking_reason or None))
            return actions

        if outcome in {"blocked_by_review", "stopped_for_approval", "child_task_failed"}:
            if last_child_task_id:
                actions.append(self._build_operator_action(f"guarded-batch:{task_id}:open-last-child", "open-task", "查看最后子任务", variant="secondary", task_id=last_child_task_id, reason=blocking_reason or None))
            return actions

        return actions

    def _with_runtime_status(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_copy = dict(self._maybe_self_heal_completed_task(task))
        events = self.store.get_events(task["id"], limit=80)
        task_copy["runtime_status"] = self._build_runtime_status(task_copy, events)
        task_copy["list_priority"] = self._build_task_list_priority(task_copy)
        return task_copy

    def _with_runtime_status_summary(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task_copy = dict(self._maybe_self_heal_completed_task(task))
        task_copy["runtime_status"] = self._build_runtime_status_summary(task_copy)
        task_copy["list_priority"] = self._build_task_list_priority(task_copy)
        return task_copy

    def _maybe_self_heal_completed_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        status = str(task.get("status") or "")
        if status not in {"running", "resuming_writeback"}:
            return task
        if task.get("error"):
            return task

        task_type = str(task.get("task_type") or "")
        should_complete = False
        try:
            if task_type == "write":
                should_complete = self._write_task_terminal_state_missing(task)
            elif task_type == "plan":
                should_complete = self._plan_task_terminal_state_missing(task)
        except Exception:
            logger.warning("Failed to self-heal terminal task state for %s", task.get("id"), exc_info=True)
            return task

        if not should_complete:
            return task
        return self.store.mark_completed(task["id"])

    def _write_task_terminal_state_missing(self, task: Dict[str, Any]) -> bool:
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        if "data-sync" not in step_results:
            return False
        writeback = ((task.get("artifacts") or {}).get("writeback") or {})
        if not str(writeback.get("chapter_file") or "").strip():
            return False
        if not str(writeback.get("state_file") or "").strip():
            return False
        return self._writeback_is_complete(task)

    def _plan_task_terminal_state_missing(self, task: Dict[str, Any]) -> bool:
        if str(task.get("current_step") or "") != "plan":
            return False
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        if "plan" not in step_results:
            return False
        writeback = ((task.get("artifacts") or {}).get("writeback") or {})
        if not str(writeback.get("outline_file") or "").strip():
            return False
        if not str(writeback.get("state_file") or "").strip():
            return False
        events = self.store.get_events(task.get("id"), limit=50)
        return any(str(event.get("message") or "") == "Plan writeback completed" for event in events)

    def _build_runtime_status(self, task: Dict[str, Any], events: List[Dict[str, Any]]) -> Dict[str, Any]:
        step_key = self._resolve_runtime_step_key(task, events)
        runtime_events = self._slice_runtime_events(task, events, step_key)
        step_result = ((task.get("artifacts") or {}).get("step_results") or {}).get(step_key or "", {})
        last_event = runtime_events[-1] if runtime_events else (events[-1] if events else None)
        attempt = self._resolve_runtime_value(
            task,
            step_key,
            runtime_events,
            "attempt",
            fallback=((step_result.get("metadata") or {}).get("attempt") or (step_result.get("error") or {}).get("attempt") or 1),
        )
        retry_count = self._resolve_runtime_value(
            task,
            step_key,
            runtime_events,
            "retry_count",
            fallback=max(0, int(attempt or 1) - 1),
        )
        timeout_seconds = self._resolve_runtime_value(
            task,
            step_key,
            runtime_events,
            "timeout_seconds",
            fallback=self._runner_timeout_seconds(step_key) if step_key else None,
        )
        retryable = self._resolve_runtime_value(
            task,
            step_key,
            runtime_events,
            "retryable",
            fallback=(task.get("error") or {}).get("retryable", (step_result.get("error") or {}).get("retryable")),
        )
        error_code = self._resolve_runtime_value(
            task,
            step_key,
            runtime_events,
            "error_code",
            fallback=(task.get("error") or {}).get("code") or (step_result.get("error") or {}).get("code"),
        )
        http_status = self._resolve_runtime_value(
            task,
            step_key,
            runtime_events,
            "http_status",
            fallback=(task.get("error") or {}).get("http_status") or (step_result.get("error") or {}).get("http_status"),
        )
        step_state = self._resolve_runtime_step_state(task, last_event, attempt=attempt)
        if task.get("task_type") == "plan" and (task.get("artifacts") or {}).get("plan_blocked"):
            step_state = "failed"
        step_started_at = self._resolve_step_started_at(task, runtime_events, step_key)
        waiting_since = self._resolve_waiting_since(task, runtime_events, step_key, step_state)
        last_non_heartbeat_activity_at = self._resolve_last_non_heartbeat_activity_at(task, runtime_events, step_key)
        running_seconds = self._resolve_runtime_seconds(task, runtime_events, step_key, step_state)
        waiting_seconds = self._resolve_waiting_seconds(task, runtime_events, step_key, step_state)
        phase_label = self._resolve_phase_label(task, step_key)
        last_event_label = self._translate_runtime_event(last_event)
        last_activity_at = self._resolve_last_activity_at(task, last_event, last_non_heartbeat_activity_at)
        error_code, http_status, retryable = self._resolve_runtime_error_fields(
            task,
            step_state,
            error_code=error_code,
            http_status=http_status,
            retryable=retryable,
        )
        task_error_details = task.get("error", {}).get("details") if isinstance(task.get("error"), dict) else {}
        return {
            "phase_label": phase_label,
            "target_label": self._build_runtime_target_label(task),
            "phase_detail": self._resolve_phase_detail(task, step_key, step_state, last_event, running_seconds, waiting_seconds),
            "step_key": step_key,
            "step_state": step_state,
            "running_seconds": running_seconds,
            "waiting_seconds": waiting_seconds,
            "attempt": attempt,
            "retry_count": retry_count,
            "timeout_seconds": timeout_seconds,
            "retryable": retryable,
            "last_event_label": last_event_label,
            "last_event_message": last_event.get("message") if last_event else None,
            "last_event_at": last_event.get("timestamp") if last_event else task.get("updated_at"),
            "last_activity_at": last_activity_at,
            "last_non_heartbeat_activity_at": last_non_heartbeat_activity_at,
            "step_started_at": self._format_runtime_datetime(step_started_at),
            "waiting_since": self._format_runtime_datetime(waiting_since),
            "error_code": error_code,
            "http_status": http_status,
            "recoverability": task_error_details.get("recoverability") if isinstance(task_error_details, dict) else None,
            "suggested_resume_step": task_error_details.get("suggested_resume_step") if isinstance(task_error_details, dict) else None,
        }

    def _build_runtime_status_summary(self, task: Dict[str, Any]) -> Dict[str, Any]:
        runtime_meta = task.get("runtime_meta") or {}
        last_event = runtime_meta.get("last_event") if isinstance(runtime_meta, dict) else None
        last_non_heartbeat_event = runtime_meta.get("last_non_heartbeat_event") if isinstance(runtime_meta, dict) else None
        step_key = self._resolve_runtime_step_key(task, [event for event in (last_non_heartbeat_event, last_event) if isinstance(event, dict)])
        step_result = ((task.get("artifacts") or {}).get("step_results") or {}).get(step_key or "", {})
        payload = (last_event or {}).get("payload") or {}
        attempt = payload.get("attempt") or ((step_result.get("metadata") or {}).get("attempt") or (step_result.get("error") or {}).get("attempt") or 1)
        try:
            retry_count = int(payload.get("retry_count") if payload.get("retry_count") is not None else max(0, int(attempt or 1) - 1))
        except (TypeError, ValueError):
            retry_count = 0
        timeout_seconds = payload.get("timeout_seconds")
        if timeout_seconds is None and step_key:
            timeout_seconds = self._runner_timeout_seconds(step_key)
        retryable = payload.get("retryable")
        if retryable is None:
            retryable = (task.get("error") or {}).get("retryable", (step_result.get("error") or {}).get("retryable"))
        error_code = payload.get("error_code") or (task.get("error") or {}).get("code") or (step_result.get("error") or {}).get("code")
        http_status = payload.get("http_status") or (task.get("error") or {}).get("http_status")
        step_state = self._resolve_runtime_step_state(task, last_event if isinstance(last_event, dict) else None, attempt=attempt)
        step_started_at = self._resolve_summary_step_started_at(task, step_key, last_event if isinstance(last_event, dict) else None)
        waiting_since = self._resolve_summary_waiting_since(task, step_state, last_event if isinstance(last_event, dict) else None)
        last_activity_at = self._resolve_last_activity_at(
            task,
            last_event if isinstance(last_event, dict) else None,
            str((last_non_heartbeat_event or {}).get("timestamp") or "") or None,
        )
        running_seconds = self._resolve_summary_runtime_seconds(task, step_state, step_started_at)
        waiting_seconds = self._resolve_summary_waiting_seconds(task, step_state, waiting_since)
        phase_label = self._resolve_phase_label(task, step_key)
        last_event_label = self._translate_runtime_event(last_event if isinstance(last_event, dict) else None)
        error_code, http_status, retryable = self._resolve_runtime_error_fields(
            task,
            step_state,
            error_code=error_code,
            http_status=http_status,
            retryable=retryable,
        )
        task_error_details = task.get("error", {}).get("details") if isinstance(task.get("error"), dict) else {}
        return {
            "phase_label": phase_label,
            "target_label": self._build_runtime_target_label(task),
            "phase_detail": self._resolve_phase_detail(task, step_key, step_state, last_event if isinstance(last_event, dict) else None, running_seconds, waiting_seconds),
            "step_key": step_key,
            "step_state": step_state,
            "running_seconds": running_seconds,
            "waiting_seconds": waiting_seconds,
            "attempt": attempt,
            "retry_count": retry_count,
            "timeout_seconds": timeout_seconds,
            "retryable": retryable,
            "last_event_label": last_event_label,
            "last_event_message": (last_event or {}).get("message"),
            "last_event_at": (last_event or {}).get("timestamp") or task.get("updated_at"),
            "last_activity_at": last_activity_at,
            "last_non_heartbeat_activity_at": (last_non_heartbeat_event or {}).get("timestamp") or task.get("updated_at"),
            "step_started_at": self._format_runtime_datetime(step_started_at),
            "waiting_since": self._format_runtime_datetime(waiting_since),
            "error_code": error_code,
            "http_status": http_status,
            "recoverability": task_error_details.get("recoverability") if isinstance(task_error_details, dict) else None,
            "suggested_resume_step": task_error_details.get("suggested_resume_step") if isinstance(task_error_details, dict) else None,
        }

    def _resolve_summary_step_started_at(
        self,
        task: Dict[str, Any],
        step_key: Optional[str],
        last_event: Optional[Dict[str, Any]],
    ) -> Optional[datetime]:
        timestamp = None
        if isinstance(last_event, dict):
            timestamp = self._parse_iso_datetime(last_event.get("timestamp"))
        if str(task.get("status") or "") in {"running", "retrying", "resuming_writeback"}:
            return timestamp or self._parse_iso_datetime(task.get("updated_at")) or self._parse_iso_datetime(task.get("started_at"))
        return timestamp or self._parse_iso_datetime(task.get("started_at"))

    def _resolve_summary_waiting_since(
        self,
        task: Dict[str, Any],
        step_state: str,
        last_event: Optional[Dict[str, Any]],
    ) -> Optional[datetime]:
        if step_state not in ACTIVE_RUNTIME_STATES:
            return None
        message = str((last_event or {}).get("message") or "")
        if message in {"llm_request_started", "request_dispatched", "awaiting_model_response", "step_heartbeat"}:
            return self._parse_iso_datetime((last_event or {}).get("timestamp")) or self._parse_iso_datetime(task.get("updated_at"))
        return None

    def _resolve_summary_runtime_seconds(
        self,
        task: Dict[str, Any],
        step_state: str,
        step_started_at: Optional[datetime],
    ) -> int:
        if step_state in {"completed", "failed", "interrupted", "cancelled", "rejected", "waiting_approval"}:
            end_dt = self._parse_iso_datetime(task.get("finished_at") or task.get("interrupted_at") or task.get("updated_at"))
            return self._seconds_between(step_started_at, end_dt)
        return self._seconds_between(step_started_at, datetime.now(timezone.utc))

    def _resolve_summary_waiting_seconds(
        self,
        task: Dict[str, Any],
        step_state: str,
        waiting_since: Optional[datetime],
    ) -> int:
        if waiting_since is None:
            return 0
        if step_state == "waiting_approval":
            end_dt = self._parse_iso_datetime(task.get("updated_at")) or datetime.now(timezone.utc)
            return self._seconds_between(waiting_since, end_dt)
        return self._seconds_between(waiting_since, datetime.now(timezone.utc))

    def _build_task_list_priority(self, task: Dict[str, Any]) -> int:
        status = str(task.get("status") or "")
        if status == "awaiting_writeback_approval":
            return 0
        if status in {"running", "retrying", "resuming_writeback"}:
            return 1
        if status in {"failed", "interrupted"}:
            return 3 if (task.get("runtime_status") or {}).get("retryable") is False else 2
        if status == "rejected":
            return 4
        if status == "completed":
            return 5
        return 2

    def _build_runtime_target_label(self, task: Dict[str, Any]) -> Optional[str]:
        request = task.get("request") or {}
        task_type = str(task.get("task_type") or "")
        if task_type == "plan":
            volume = str(request.get("volume") or "1").strip() or "1"
            return f"第 {volume} 卷"
        if task_type == "write":
            chapter = int(request.get("chapter") or 0)
            if chapter > 0:
                volume = self._resolve_volume_for_chapter(chapter)
                return f"第 {volume} 卷 · 第 {chapter} 章"
            return "目标章节未指定"
        if task_type == "repair":
            chapter = int(request.get("chapter") or 0)
            if chapter > 0:
                volume = self._resolve_volume_for_chapter(chapter)
                return f"第 {volume} 卷 · 第 {chapter} 章修稿"
            return "目标修稿章节未指定"
        if task_type == "guarded-write":
            chapter = int(request.get("chapter") or 0)
            return f"护栏推进 · 第 {chapter} 章" if chapter > 0 else "护栏推进下一章"
        if task_type == "guarded-batch-write":
            start_chapter = int(request.get("start_chapter") or request.get("chapter") or 0)
            max_chapters = max(1, int(request.get("max_chapters") or 1))
            if start_chapter > 0:
                end_chapter = start_chapter + max_chapters - 1
                if end_chapter > start_chapter:
                    return f"护栏批量推进 · 第 {start_chapter}-{end_chapter} 章"
                return f"护栏批量推进 · 第 {start_chapter} 章"
            return f"护栏批量推进 · 最多 {max_chapters} 章"
        if task_type == "review":
            chapter_range = str(request.get("chapter_range") or "").strip()
            if chapter_range:
                return f"第 {chapter_range} 章"
            chapter = int(request.get("chapter") or 0)
            return f"第 {chapter} 章" if chapter > 0 else "目标范围未指定"
        if task_type == "resume":
            chapter = int(request.get("chapter") or 0)
            return f"恢复第 {chapter} 章" if chapter > 0 else "恢复最近中断任务"
        if task_type == "init":
            return "补种当前项目骨架"
        return None

    def _resolve_runtime_step_key(self, task: Dict[str, Any], events: List[Dict[str, Any]]) -> Optional[str]:
        current_step = task.get("current_step")
        if current_step:
            return str(current_step)
        if task.get("task_type") == "plan" and (task.get("artifacts") or {}).get("plan_blocked"):
            return "plan"
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        for step_name in reversed(task.get("step_order") or []):
            if step_name in step_results:
                return step_name
        for event in reversed(events):
            step_name = event.get("step_name")
            if step_name:
                return str(step_name)
        return None

    def _resolve_phase_label(self, task: Dict[str, Any], step_key: Optional[str]) -> str:
        if task.get("task_type") == "plan" and (task.get("artifacts") or {}).get("plan_blocked"):
            return "待补信息"
        if task.get("status") == "completed" and step_key and step_key in RUNTIME_PHASE_LABELS:
            return f"{RUNTIME_PHASE_LABELS[step_key]}已完成"
        if step_key and step_key in RUNTIME_PHASE_LABELS:
            return RUNTIME_PHASE_LABELS[step_key]
        if task.get("status") == "completed":
            return "流程已完成"
        if task.get("status") == "failed":
            return "执行失败"
        if task.get("status") == "awaiting_writeback_approval":
            return "回写审批"
        if task.get("status") == "resuming_writeback":
            return "回写同步"
        if task.get("status") == "retrying":
            return "准备重试"
        return "等待执行"

    def _resolve_runtime_step_state(
        self,
        task: Dict[str, Any],
        last_event: Optional[Dict[str, Any]],
        *,
        attempt: Any,
    ) -> str:
        status = str(task.get("status") or "")
        if status == "awaiting_writeback_approval" or task.get("approval_status") == "pending":
            return "waiting_approval"
        if status == "interrupted":
            return "cancelled" if str((task.get("error") or {}).get("code") or "") == "TASK_CANCELLED" else "interrupted"
        if status == "rejected":
            return "rejected"
        if status == "failed":
            return "failed"
        if status == "completed":
            return "completed"
        if status == "retrying":
            return "retrying"
        if status == "resuming_writeback":
            return "resuming_writeback"
        if status != "running":
            return "idle"
        if last_event and str(last_event.get("message") or "") in {"step_retry_scheduled", "step_retry_started"}:
            return "retrying"
        try:
            return "retrying" if int(attempt or 1) > 1 else "running"
        except (TypeError, ValueError):
            return "running"

    def _slice_runtime_events(
        self,
        task: Dict[str, Any],
        events: List[Dict[str, Any]],
        step_key: Optional[str],
    ) -> List[Dict[str, Any]]:
        if not events or not step_key:
            return events
        boundary_messages = {f"Step started: {step_key}", "step_retry_started"}
        if str(task.get("status") or "") == "awaiting_writeback_approval" or task.get("approval_status") == "pending":
            boundary_messages.update({"step_waiting_approval", "Waiting for writeback approval"})

        start_index = 0
        for index, event in enumerate(events):
            if str(event.get("step_name") or "") != str(step_key):
                continue
            if str(event.get("message") or "") in boundary_messages:
                start_index = index
        return events[start_index:]

    def _resolve_runtime_value(
        self,
        task: Dict[str, Any],
        step_key: Optional[str],
        events: List[Dict[str, Any]],
        field_name: str,
        *,
        fallback: Any = None,
    ) -> Any:
        for event in reversed(events):
            event_step = event.get("step_name")
            if step_key and event_step and str(event_step) != str(step_key):
                continue
            payload = event.get("payload") or {}
            if field_name in payload and payload.get(field_name) is not None:
                return payload.get(field_name)
        if field_name == "error_code":
            return (task.get("error") or {}).get("code", fallback)
        if field_name == "http_status":
            return (task.get("error") or {}).get("http_status", fallback)
        return fallback

    def _resolve_last_activity_at(
        self,
        task: Dict[str, Any],
        last_event: Optional[Dict[str, Any]],
        last_non_heartbeat_activity_at: Optional[str] = None,
    ) -> Optional[str]:
        if last_event and last_event.get("timestamp"):
            return str(last_event.get("timestamp"))
        if last_non_heartbeat_activity_at:
            return last_non_heartbeat_activity_at
        return task.get("updated_at")

    def _resolve_last_non_heartbeat_activity_at(
        self,
        task: Dict[str, Any],
        events: List[Dict[str, Any]],
        step_key: Optional[str],
    ) -> Optional[str]:
        for event in reversed(events):
            if step_key and str(event.get("step_name") or "") != str(step_key):
                continue
            if str(event.get("message") or "") == "step_heartbeat":
                continue
            if event.get("timestamp"):
                return str(event.get("timestamp"))
        return task.get("updated_at")

    def _resolve_runtime_seconds(
        self,
        task: Dict[str, Any],
        events: List[Dict[str, Any]],
        step_key: Optional[str],
        step_state: str,
    ) -> int:
        if step_state in {"completed", "failed", "interrupted", "cancelled", "rejected"}:
            start_dt = self._resolve_step_started_at(task, events, step_key)
            end_dt = self._resolve_latest_step_event_time(
                events,
                step_key,
                {
                    "llm_request_finished",
                    "llm_request_failed",
                    "llm_request_timed_out",
                    "step_waiting_approval",
                    "Waiting for writeback approval",
                    f"Step completed: {step_key}",
                    f"Step failed: {step_key}",
                },
            )
            if end_dt is None:
                end_dt = self._parse_iso_datetime(task.get("finished_at") or task.get("interrupted_at") or task.get("updated_at"))
            return self._seconds_between(start_dt, end_dt)

        start_dt = self._resolve_step_started_at(task, events, step_key)
        if step_state == "waiting_approval":
            end_dt = self._resolve_latest_step_event_time(events, step_key, {"step_waiting_approval", "Waiting for writeback approval"})
            if end_dt is None:
                end_dt = self._parse_iso_datetime(task.get("updated_at"))
            return self._seconds_between(start_dt, end_dt)

        end_dt = datetime.now(timezone.utc)
        return self._seconds_between(start_dt, end_dt)

    def _resolve_waiting_seconds(
        self,
        task: Dict[str, Any],
        events: List[Dict[str, Any]],
        step_key: Optional[str],
        step_state: str,
    ) -> int:
        waiting_since = self._resolve_waiting_since(task, events, step_key, step_state)
        if waiting_since is None:
            return 0
        end_dt = datetime.now(timezone.utc)
        if step_state == "waiting_approval":
            end_dt = self._parse_iso_datetime(task.get("updated_at")) or end_dt
        return self._seconds_between(waiting_since, end_dt)

    def _resolve_waiting_since(
        self,
        task: Dict[str, Any],
        events: List[Dict[str, Any]],
        step_key: Optional[str],
        step_state: str,
    ) -> Optional[datetime]:
        if step_state not in ACTIVE_RUNTIME_STATES:
            return None
        wait_start_messages = {"llm_request_started", "request_dispatched", "awaiting_model_response"}
        wait_end_messages = {"response_received", "parsing_output", "llm_request_finished", "llm_request_failed", "llm_request_timed_out"}
        waiting_since: Optional[datetime] = None
        for event in events:
            if step_key and str(event.get("step_name") or "") != str(step_key):
                continue
            message = str(event.get("message") or "")
            timestamp = self._parse_iso_datetime(event.get("timestamp"))
            if timestamp is None:
                continue
            if message in wait_end_messages:
                waiting_since = None
                continue
            if message in wait_start_messages and waiting_since is None:
                waiting_since = timestamp
        return waiting_since

    def _resolve_runtime_error_fields(
        self,
        task: Dict[str, Any],
        step_state: str,
        *,
        error_code: Any,
        http_status: Any,
        retryable: Any,
    ) -> tuple[Any, Any, Any]:
        if step_state in {"completed", "waiting_approval", "running", "retrying", "resuming_writeback", "idle"}:
            return None, None, None
        task_error = task.get("error") or {}
        return (
            task_error.get("code", error_code),
            task_error.get("http_status", http_status),
            task_error.get("retryable", retryable),
        )

    def _recover_or_mark_stale_running_tasks(self) -> int:
        updated = 0
        for task in self.store.list_tasks(limit=1000):
            task_id = task.get("id")
            if not task_id or task.get("status") != "running":
                continue
            current_step = task.get("current_step")
            if self._should_complete_stale_task_after_restart(task):
                self.store.mark_completed(task_id)
                self.store.append_event(
                    task_id,
                    "warning",
                    "服务重启后检测到写回已完成，任务已自动收口",
                    step_name=current_step,
                    payload={"recovered": True, "resume_hint": current_step},
                )
            else:
                self.store.mark_interrupted(
                    task_id,
                    current_step,
                    "服务重启前任务未完成，已中断，可从当前步骤继续处理。",
                )
                self.store.append_event(
                    task_id,
                    "warning",
                    "服务重启后检测到未完成任务，已标记为中断",
                    step_name=current_step,
                    payload={"recovered": False, "resume_hint": current_step},
                )
            updated += 1
        return updated

    def _should_complete_stale_task_after_restart(self, task: Dict[str, Any]) -> bool:
        current_step = str(task.get("current_step") or "")
        if task.get("task_type") == "write" and current_step == "data-sync":
            try:
                return self._writeback_is_complete(task)
            except Exception:
                return False
        if task.get("task_type") == "plan" and current_step == "plan":
            events = self.store.get_events(task.get("id"), limit=50)
            return any(str(event.get("message") or "") == "Plan writeback completed" for event in events)
        return False

    def _resolve_phase_detail(
        self,
        task: Dict[str, Any],
        step_key: Optional[str],
        step_state: str,
        last_event: Optional[Dict[str, Any]],
        running_seconds: int,
        waiting_seconds: int,
    ) -> Optional[str]:
        if task.get("task_type") == "plan" and (task.get("artifacts") or {}).get("plan_blocked"):
            return "当前规划信息不足，需要先回总览页补录后再运行 plan。"
        if step_state == "waiting_approval":
            return "已进入回写审批点，等待人工确认。"
        if step_state == "resuming_writeback":
            return "你已批准回写，系统正在继续执行写回与项目同步。"
        if step_state == "interrupted":
            return "任务在服务重启或执行中断后暂停，可重试或恢复。"
        if step_state == "cancelled":
            return "任务已被手动停止。"
        if step_state == "rejected":
            return "任务已被拒绝，不会继续执行回写。"
        if step_state == "failed":
            error_code = (task.get("error") or {}).get("code")
            if error_code == PLAN_INPUT_BLOCKED_CODE:
                return "当前规划信息不足，需要先回总览页补录后再运行 plan。"
            if error_code == "INVALID_STEP_OUTPUT":
                details = (task.get("error") or {}).get("details") or {}
                recoverability = str(details.get("recoverability") or "").strip()
                parse_stage = str(details.get("parse_stage") or "").strip()
                resume_step = str(details.get("suggested_resume_step") or step_key or "").strip()
                resume_label = RUNTIME_PHASE_LABELS.get(resume_step, resume_step)
                if recoverability and recoverability != "terminal":
                    base = "系统波动导致步骤结构化输出无效，可直接重试。"
                    if resume_label:
                        base = f"系统波动导致步骤结构化输出无效，建议从{resume_label}重试。"
                    if parse_stage:
                        return f"{base} 当前解析阶段：{parse_stage}。"
                    return base
                if parse_stage:
                    return f"步骤结构化输出无效，当前解析阶段：{parse_stage}。"
            return f"当前步骤执行失败{f'：{error_code}' if error_code else ''}"
        if step_state == "completed":
            if step_key and step_key in RUNTIME_PHASE_LABELS:
                return f"{RUNTIME_PHASE_LABELS[step_key]}已完成。"
            return "当前步骤已完成。"
        if not last_event:
            return f"正在执行{self._resolve_phase_label(task, step_key)}"

        message = str(last_event.get("message") or "")
        payload = last_event.get("payload") or {}
        if message == "prompt_compiled":
            return "已完成提示词和上下文组装，准备发起模型请求。"
        if message == "request_dispatched":
            return "请求已发出，正在等待上游模型受理。"
        if message == "awaiting_model_response":
            if waiting_seconds >= 900:
                return "等待上游模型响应时间过长，可能已卡住，可稍后重试或停止任务。"
            if waiting_seconds >= 180:
                return "仍在等待上游模型响应。"
            return "已连接上游模型，正在等待返回结果。"
        if message == "step_heartbeat":
            if waiting_seconds > 0:
                if waiting_seconds >= 900:
                    return "当前等待上游响应时间过长，可能已卡住，可稍后重试或停止任务。"
                return "当前仍在等待上游响应。"
            return f"{self._resolve_phase_label(task, step_key)}仍在执行。"
        if message == "response_received":
            return "已收到模型响应，正在处理结果。"
        if message == "parsing_output":
            if step_key == "data-sync":
                return "正在校验写回结果并同步项目数据。"
            return "正在校验并解析结构化输出。"
        if message == "step_retry_scheduled":
            return "已安排步骤重试。"
        if message == "step_retry_started":
            attempt = payload.get("attempt")
            if attempt:
                return f"正在进行第 {attempt} 次尝试。"
            return "步骤重试已开始。"
        if message == "Writeback approved":
            return "你已批准回写，系统正在继续执行后续写回步骤。"
        if message == "Resume target scheduled":
            return "已提交恢复执行，目标任务正在继续推进。"
        if message == "Resume target already running":
            return "恢复目标仍在运行，不能重复恢复。"
        if message == "Resume schedule failed":
            return "恢复任务调度失败。"
        return f"正在执行{self._resolve_phase_label(task, step_key)}"

    def _resolve_step_started_at(
        self,
        task: Dict[str, Any],
        events: List[Dict[str, Any]],
        step_key: Optional[str],
    ) -> Optional[datetime]:
        if step_key:
            for event in reversed(events):
                message = str(event.get("message") or "")
                if str(event.get("step_name") or "") != str(step_key):
                    continue
                if message in {
                    "llm_request_started",
                    "step_retry_started",
                    "step_waiting_approval",
                    "Waiting for writeback approval",
                    f"Step started: {step_key}",
                }:
                    return self._parse_iso_datetime(event.get("timestamp"))
        return self._parse_iso_datetime(task.get("started_at"))

    def _format_runtime_datetime(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return value.astimezone(timezone.utc).isoformat()

    def _resolve_latest_step_event_time(
        self,
        events: List[Dict[str, Any]],
        step_key: Optional[str],
        messages: set[str],
    ) -> Optional[datetime]:
        for event in reversed(events):
            if step_key and str(event.get("step_name") or "") != str(step_key):
                continue
            if str(event.get("message") or "") in messages:
                return self._parse_iso_datetime(event.get("timestamp"))
        return None

    def _resolve_latest_matching_step_event(
        self,
        events: List[Dict[str, Any]],
        step_key: Optional[str],
        messages: set[str],
    ) -> Optional[Dict[str, Any]]:
        for event in reversed(events):
            if step_key and str(event.get("step_name") or "") != str(step_key):
                continue
            if str(event.get("message") or "") in messages:
                return event
        return None

    def _translate_runtime_event(self, event: Optional[Dict[str, Any]]) -> Optional[str]:
        if not event:
            return None
        message = str(event.get("message") or "")
        if message in RUNTIME_EVENT_LABELS:
            return RUNTIME_EVENT_LABELS[message]
        match = re.match(r"^Step started:\s*(.+)$", message)
        if match:
            return f"步骤开始：{RUNTIME_PHASE_LABELS.get(match.group(1), match.group(1))}"
        match = re.match(r"^Step completed:\s*(.+)$", message)
        if match:
            return f"步骤完成：{RUNTIME_PHASE_LABELS.get(match.group(1), match.group(1))}"
        match = re.match(r"^Step failed:\s*(.+)$", message)
        if match:
            return f"步骤失败：{RUNTIME_PHASE_LABELS.get(match.group(1), match.group(1))}"
        return message or None

    def _parse_iso_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            local_tz = datetime.now().astimezone().tzinfo or timezone.utc
            return parsed.replace(tzinfo=local_tz).astimezone(timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _seconds_between(self, start_dt: Optional[datetime], end_dt: Optional[datetime]) -> int:
        if start_dt is None or end_dt is None:
            return 0
        return max(0, int((end_dt - start_dt).total_seconds()))

    def probe_llm(self) -> Dict[str, Any]:
        probe = dict(self.runner.probe())
        probe_status = str(probe.get("connection_status") or "not_checked")
        probe_error = probe.get("connection_error")
        current_signature = self._current_llm_config_signature()
        last_success = self._find_recent_llm_success(current_signature)
        last_failure = self._find_recent_llm_failure(current_signature)
        effective_status = probe_status
        status_source = "probe"
        if probe_status == "failed" and self._is_recent_execution_success_fresh(last_success):
            effective_status = "degraded"
            status_source = "recent_task_success"
        elif probe_status == "connected":
            status_source = "probe"
        elif probe_status == "not_configured":
            status_source = "configuration"
        elif last_failure:
            status_source = "recent_task_failure"

        probe["probe_status"] = probe_status
        probe["effective_status"] = effective_status
        probe["status_source"] = status_source
        probe["last_probe_at"] = probe.get("connection_checked_at")
        probe["last_probe_error"] = probe_error
        probe["last_successful_request_at"] = last_success.get("timestamp") if last_success else None
        probe["last_successful_task_type"] = last_success.get("task_type") if last_success else None
        probe["last_failed_request_at"] = last_failure.get("timestamp") if last_failure else None
        probe["last_failed_task_type"] = last_failure.get("task_type") if last_failure else None
        probe["config_signature"] = current_signature
        probe["connection_status"] = effective_status
        if effective_status == "failed" or probe_status == "failed":
            probe["connection_error"] = probe_error
        return probe

    def _find_recent_llm_success(self, config_signature: Optional[str] = None) -> Optional[Dict[str, Any]]:
        latest: Optional[Dict[str, Any]] = None
        for task in self.store.list_tasks(limit=200):
            task_type = str(task.get("task_type") or "")
            step_results = ((task.get("artifacts") or {}).get("step_results") or {})
            if not any(step_name in EXTERNAL_WORKFLOW_STEPS and bool((result or {}).get("success")) for step_name, result in step_results.items()):
                continue
            task_signature = self._task_step_config_signature(task, success=True)
            if config_signature and task_signature != config_signature:
                continue
            timestamp = str(task.get("finished_at") or task.get("updated_at") or "")
            if not timestamp:
                continue
            candidate = {"timestamp": timestamp, "task_type": task_type, "config_signature": task_signature}
            if latest is None or candidate["timestamp"] > latest["timestamp"]:
                latest = candidate
        return latest

    def _find_recent_llm_failure(self, config_signature: Optional[str] = None) -> Optional[Dict[str, Any]]:
        latest: Optional[Dict[str, Any]] = None
        for task in self.store.list_tasks(limit=200):
            error = task.get("error") or {}
            code = str(error.get("code") or "")
            if not code.startswith("LLM_"):
                continue
            task_signature = self._task_step_config_signature(task, success=False)
            if config_signature and task_signature != config_signature:
                continue
            timestamp = str(task.get("finished_at") or task.get("updated_at") or "")
            if not timestamp:
                continue
            candidate = {
                "timestamp": timestamp,
                "task_type": str(task.get("task_type") or ""),
                "error_code": code,
                "config_signature": task_signature,
            }
            if latest is None or candidate["timestamp"] > latest["timestamp"]:
                latest = candidate
        return latest

    def _is_recent_execution_success_fresh(self, success: Optional[Dict[str, Any]]) -> bool:
        if not success:
            return False
        success_dt = self._parse_iso_datetime(success.get("timestamp"))
        if success_dt is None:
            return False
        age_seconds = self._seconds_between(success_dt, datetime.now(timezone.utc))
        return age_seconds <= LLM_STATUS_SUCCESS_FRESH_SECONDS

    def probe_codex(self) -> Dict[str, Any]:
        return self.probe_llm()

    def probe_rag(self) -> Dict[str, Any]:
        return self.rag_client.probe()

    def create_task(self, task_type: str, request: Dict[str, Any]) -> Dict[str, Any]:
        task = self._create_task_record(task_type, request)
        self._schedule(task["id"])
        return task

    def run_task_sync(self, task_type: str, request: Dict[str, Any], *, resume_from_step: Optional[str] = None) -> Dict[str, Any]:
        task = self._create_task_record(task_type, request)
        asyncio.run(self._run_task(task["id"], resume_from_step=resume_from_step))
        refreshed = self.store.get_task(task["id"])
        if refreshed is None:
            raise KeyError(task["id"])
        return refreshed

    def _create_task_record(self, task_type: str, request: Dict[str, Any]) -> Dict[str, Any]:
        workflow = self._load_workflow(task_type)
        task = self.store.create_task(task_type, request, workflow)
        return self.store.update_task(task["id"], workflow_spec=workflow)

    def retry_task(self, task_id: str, resume_from_step: Optional[str] = None) -> Dict[str, Any]:
        current_task = self.store.get_task(task_id)
        if current_task is None:
            raise KeyError(task_id)
        target_step = resume_from_step or self._determine_resume_from_step(current_task)
        preserve_approval = bool(
            current_task.get("approval_status") == "approved" and target_step in {"approval-gate", "data-sync", "repair-writeback"}
        )
        self.store.reset_for_retry(task_id, preserve_approval=preserve_approval)
        self.store.append_event(
            task_id,
            "info",
            "Retry requested",
            step_name=target_step,
            payload={"resume_from_step": target_step, "preserve_approval": preserve_approval, "attempt": 1},
        )
        self._schedule(task_id, resume_from_step=target_step)
        return self.store.get_task(task_id)

    def cancel_task(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        if str(task.get("status") or "") in {"completed", "failed", "rejected", "interrupted"}:
            return task
        current_step = task.get("current_step")
        message = str(reason or "").strip() or "任务已由用户停止。"
        self.store.mark_cancelled(task_id, current_step, message)
        self.store.append_event(
            task_id,
            "warning",
            "任务已手动停止",
            step_name=current_step,
            payload={"reason": message},
        )
        job = self._jobs.get(task_id)
        if job and not job.done():
            job.cancel()
        return self.store.get_task(task_id)

    def approve_writeback(self, task_id: str, reason: str = "") -> Dict[str, Any]:
        task = self.store.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        resume_step = task.get("current_step") or "approval-gate"
        self.store.update_task(task_id, approval_status="approved", status="resuming_writeback")
        self.store.append_event(
            task_id,
            "info",
            "Writeback approved",
            step_name=resume_step,
            payload={"reason": reason, "resume_from_step": resume_step},
        )
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
            if task.get("task_type") == "resume":
                await self._run_resume_task(task_id, task)
                return

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

                result = await self._run_external_step(task_id, current_task, step)
                if result is None:
                    return

                if not result.success:
                    failure_error = result.error or {"code": "STEP_FAILED", "message": "步骤执行失败。"}
                    failure_error = self._normalize_invalid_output_error(
                        task=current_task,
                        step=step,
                        error_info=failure_error,
                        result=result,
                    )
                    self.store.mark_failed(
                        task_id,
                        current_step_name,
                        failure_error,
                    )
                    return

                blocked_handled = self._maybe_complete_plan_as_blocked(
                    task_id,
                    current_task,
                    step,
                    result.structured_output or {},
                )
                if blocked_handled:
                    return

                validation_error = self._validate_output(step, result.structured_output or {})
                if validation_error:
                    retried_result = await self._maybe_retry_invalid_output_step(task_id, current_task, step, validation_error, result=result)
                    if retried_result is not None:
                        if not retried_result.success:
                            retry_failure = self._normalize_invalid_output_error(
                                task=current_task,
                                step=step,
                                error_info=retried_result.error or validation_error,
                                result=retried_result,
                            )
                            self.store.mark_failed(task_id, current_step_name, retry_failure)
                            return
                        result = retried_result
                        blocked_handled = self._maybe_complete_plan_as_blocked(
                            task_id,
                            current_task,
                            step,
                            result.structured_output or {},
                        )
                        if blocked_handled:
                            return
                        validation_error = self._validate_output(step, result.structured_output or {})
                if validation_error:
                    normalized_validation_error = self._normalize_invalid_output_error(
                        task=current_task,
                        step=step,
                        error_info=validation_error,
                        result=result,
                    )
                    self.store.mark_failed(task_id, current_step_name, normalized_validation_error)
                    self.store.append_event(
                        task_id,
                        "error",
                        "Schema validation failed",
                        step_name=current_step_name,
                        payload=normalized_validation_error,
                    )
                    return

                apply_error = await self._apply_step_side_effects(task_id, step, result.structured_output or {})
                if apply_error:
                    self.store.mark_failed(task_id, current_step_name, apply_error)
                    self.store.append_event(task_id, "error", "Step writeback failed", step_name=current_step_name, payload=apply_error)
                    return

            self.store.mark_completed(task_id)
            self.store.append_event(task_id, "info", "Task completed")
        except asyncio.CancelledError:
            cancelled = self.store.get_task(task_id)
            if cancelled and str((cancelled.get("error") or {}).get("code") or "") == "TASK_CANCELLED":
                return
            self.store.mark_interrupted(
                task_id,
                current_step_name or (task.get("current_step") if task else None),
                "任务在执行过程中被中止，可从当前步骤继续处理。",
            )
            self.store.append_event(
                task_id,
                "warning",
                "任务执行被中止",
                step_name=current_step_name,
                payload={"resume_hint": current_step_name},
            )
            raise
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
        finally:
            self._jobs.pop(task_id, None)

    async def _run_resume_task(self, task_id: str, task: Dict[str, Any]) -> None:
        step_name = "resume"
        self.store.mark_running(task_id, step_name)
        target = self._resolve_resume_target_task(task)
        if target is None:
            error_info = {"code": "NO_RESUMABLE_TASK", "message": "No interrupted task is available for resume"}
            contract = self._build_resume_result_contract(
                task_id=task_id,
                target=None,
                decision={"action": "complete", "reason": error_info["message"], "resume_from_step": None, "target_task_id": None},
                outcome="blocked",
                blocking_reason=error_info["message"],
            )
            self.store.save_step_result(task_id, step_name, {"success": False, "structured_output": contract})
            self.store.mark_failed(task_id, step_name, error_info)
            self.store.append_event(task_id, "error", "Resume target not found", step_name=step_name, payload=error_info)
            return

        decision = self._build_resume_decision(target)
        self.store.update_task(
            task_id,
            resume_target_task_id=target["id"],
            resume_from_step=decision.get("resume_from_step"),
            resume_reason=decision.get("reason"),
        )
        contract = self._build_resume_result_contract(
            task_id=task_id,
            target=target,
            decision=decision,
            outcome=str(decision.get("action") or "blocked"),
            blocking_reason=str(decision.get("reason") or ""),
        )
        self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": contract})
        self.store.append_event(task_id, "info", "Resume target resolved", step_name=step_name, payload=contract)

        if decision["action"] == "complete":
            self.store.mark_completed(target["id"])
            self.store.append_event(
                target["id"],
                "info",
                "Task auto-completed during resume recovery",
                step_name=target.get("current_step"),
                payload={"reason": decision.get("reason")},
            )
            self.store.mark_completed(task_id)
            self.store.append_event(task_id, "info", "Task completed")
            return

        resume_step = decision.get("resume_from_step")
        active_target_job = self._jobs.get(target["id"])
        if active_target_job and not active_target_job.done():
            error_info = {
                "code": "RESUME_TARGET_ALREADY_RUNNING",
                "message": "Resume target task is still running",
            }
            failure_contract = self._build_resume_result_contract(
                task_id=task_id,
                target=target,
                decision=decision,
                outcome="blocked",
                blocking_reason=error_info["message"],
            )
            self.store.save_step_result(task_id, step_name, {"success": False, "structured_output": failure_contract})
            self.store.mark_failed(task_id, step_name, error_info)
            self.store.append_event(task_id, "error", "Resume target already running", step_name=step_name, payload={"target_task_id": target["id"]})
            return
        self.store.prepare_for_resume(target["id"], resume_from_step=resume_step, reason=decision["reason"])
        self.store.append_event(
            target["id"],
            "info",
            "Task scheduled for resume",
            step_name=resume_step,
            payload={"trigger_task_id": task_id},
        )
        if task_id in self._jobs:
            if not self._schedule(target["id"], resume_from_step=resume_step):
                error_info = {
                    "code": "RESUME_SCHEDULE_FAILED",
                    "message": "Resume target could not be scheduled",
                }
                failure_contract = self._build_resume_result_contract(
                    task_id=task_id,
                    target=target,
                    decision=decision,
                    outcome="blocked",
                    blocking_reason=error_info["message"],
                )
                self.store.save_step_result(task_id, step_name, {"success": False, "structured_output": failure_contract})
                self.store.mark_failed(task_id, step_name, error_info)
                self.store.append_event(task_id, "error", "Resume schedule failed", step_name=step_name, payload={"target_task_id": target["id"]})
                return
            self.store.mark_completed(task_id)
            self.store.append_event(
                task_id,
                "info",
                "Resume target scheduled",
                step_name=step_name,
                payload={"target_task_id": target["id"], "resume_from_step": resume_step},
            )
            return

        await self._run_task(target["id"], resume_from_step=resume_step)
        refreshed_target = self.store.get_task(target["id"]) or {}
        if refreshed_target.get("status") == "completed":
            self.store.mark_completed(task_id)
            self.store.append_event(task_id, "info", "Task completed", step_name=step_name, payload={"target_task_id": target["id"]})
            return

        error_info = {
            "code": "RESUME_TARGET_FAILED",
            "message": f"Resume target task did not complete successfully: {refreshed_target.get('status')}",
        }
        failure_contract = self._build_resume_result_contract(
            task_id=task_id,
            target=target,
            decision=decision,
            outcome="blocked",
            blocking_reason=error_info["message"],
        )
        self.store.save_step_result(task_id, step_name, {"success": False, "structured_output": failure_contract})
        self.store.mark_failed(task_id, step_name, error_info)
        self.store.append_event(task_id, "error", "Resume target failed", step_name=step_name, payload={"target_task_id": target["id"]})

    async def _run_internal_step(
        self,
        task_id: str,
        task: Dict[str, Any],
        workflow: Dict[str, Any],
        step: Dict[str, Any],
        index: int,
    ) -> str:
        step_name = step["name"]
        if step_name == "guarded-chapter-runner":
            return await self._run_guarded_chapter_runner(task_id, task)
        if step_name == "guarded-batch-runner":
            return await self._run_guarded_batch_runner(task_id, task)

        if step_name == "story-director":
            plan = self._build_story_plan(task)
            self._write_story_plan(int(plan.get("anchor_chapter") or 0), plan)
            self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": plan})
            self.store.append_event(
                task_id,
                "info",
                "Story director prepared",
                step_name=step_name,
                payload={"anchor_chapter": plan.get("anchor_chapter"), "planning_horizon": plan.get("planning_horizon")},
            )
            return "ok"

        if step_name == "chapter-director":
            brief = self._build_chapter_director_brief(task)
            self._write_director_brief(int(brief.get("chapter") or 0), brief)
            self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": brief})
            self.store.append_event(task_id, "info", "Chapter director prepared", step_name=step_name, payload={"chapter": brief.get("chapter")})
            return "ok"

        if step_name == "repair-plan":
            try:
                repair_plan = self._build_repair_plan(task)
            except RepairTaskError as exc:
                error_info = {"code": exc.code, "message": exc.message, "details": exc.details}
                self.store.save_step_result(task_id, step_name, {"success": False, "structured_output": {}, "error": error_info})
                self.store.mark_failed(task_id, step_name, error_info)
                self.store.append_event(task_id, "error", "Repair plan blocked", step_name=step_name, payload=error_info)
                return "failed"
            self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": repair_plan})
            self.store.append_event(
                task_id,
                "info",
                "Repair plan prepared",
                step_name=step_name,
                payload={
                    "chapter": repair_plan.get("chapter"),
                    "issue_type": repair_plan.get("issue_type"),
                    "source_task_id": repair_plan.get("source_task_id"),
                },
            )
            return "ok"

        if step_name == "review-summary":
            summary = self._aggregate_review(task)
            self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": summary})
            artifacts = dict(task.get("artifacts") or {})
            artifacts["review_summary"] = summary
            self.store.update_task(task_id, artifacts=artifacts)
            if task.get("task_type") in {"write", "repair"}:
                self.store.append_event(task_id, "info", "Review summary prepared", step_name=step_name, payload=summary)
            else:
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
            if task["task_type"] in {"write", "repair"} and require_manual_approval:
                approval = {
                    "status": "pending",
                    "requested_at": task.get("updated_at"),
                    "summary": summary,
                    "next_step": self._next_step_name(workflow, index),
                }
                self.store.mark_waiting_for_approval(task_id, step_name, approval)
                self.store.append_event(
                    task_id,
                    "warning",
                    "step_waiting_approval",
                    step_name=step_name,
                    payload={
                        "attempt": 1,
                        "retry_count": 0,
                        "retryable": True,
                        "next_step": approval.get("next_step"),
                    },
                )
                self.store.append_event(task_id, "warning", "Waiting for writeback approval", step_name=step_name)
                return "paused"
            self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": {"approval_required": False}})
            return "ok"

        if step_name == "repair-writeback":
            try:
                result = self._apply_repair_writeback(task_id, task)
            except RepairTaskError as exc:
                error_info = {"code": exc.code, "message": exc.message, "details": exc.details}
                self.store.save_step_result(task_id, step_name, {"success": False, "structured_output": {}, "error": error_info})
                self.store.mark_failed(task_id, step_name, error_info)
                self.store.append_event(task_id, "error", "Repair writeback blocked", step_name=step_name, payload=error_info)
                return "failed"
            self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": result})
            self.store.append_event(
                task_id,
                "info",
                "Repair writeback completed",
                step_name=step_name,
                payload=result,
            )
            return "ok"

        self.store.save_step_result(task_id, step_name, {"success": True, "structured_output": {"skipped": True}})
        return "ok"

    async def _run_guarded_chapter_runner(self, task_id: str, task: Dict[str, Any]) -> str:
        step_name = "guarded-chapter-runner"
        request = dict(task.get("request") or {})
        chapter = self._resolve_guarded_runner_chapter(request)
        request["chapter"] = chapter
        self.store.update_task(task_id, request=request, root_task_id=str(task.get("root_task_id") or task_id), trigger_source=str(task.get("trigger_source") or "manual"))

        previous_refresh = self._load_previous_story_refresh(chapter)
        if previous_refresh.get("should_refresh"):
            result = {
                "chapter": chapter,
                "outcome": "blocked_story_refresh",
                "stop_step": "story-director",
                "parent_task_id": task_id,
                "trigger_source": "guarded-chapter-runner",
                "child_task_id": None,
                "child_task_status": None,
                "safe_to_continue": False,
                "story_refresh": previous_refresh,
                "next_action": {
                    "can_enqueue_next": False,
                    "next_chapter": chapter,
                    "next_recommended_chapter": chapter,
                    "reason": "上一章已建议先刷新 story plan，本次护栏推进停止。",
                    "suggested_action": previous_refresh.get("suggested_action") or "先从 Story Director 重新规划，再决定是否继续下一章。",
                },
            }
            result["operator_actions"] = self._build_guarded_runner_operator_actions(
                task_id=task_id,
                chapter=chapter,
                outcome="blocked_story_refresh",
                child_task_id=None,
                next_action=result["next_action"],
                request=request,
                blocking_reason=str(previous_refresh.get("suggested_action") or "先从 Story Director 重新规划，再决定是否继续下一章。"),
                resume_from_step=str(previous_refresh.get("recommended_resume_from") or "story-director"),
            )
            self._persist_guarded_runner_result(task_id, result)
            self.store.append_event(
                task_id,
                "warning",
                "Guarded runner blocked by story refresh",
                step_name=step_name,
                payload={"chapter": chapter, "recommended_resume_from": previous_refresh.get("recommended_resume_from")},
            )
            return "ok"

        root_task_id = str(task.get("root_task_id") or task_id)
        child_task = self._create_task_record("write", request)
        child_task = self.store.update_task(
            child_task["id"],
            parent_task_id=task_id,
            parent_step_name=step_name,
            root_task_id=root_task_id,
            trigger_source="guarded-write",
        )
        self.store.append_event(
            task_id,
            "info",
            "Guarded runner child task created",
            step_name=step_name,
            payload={"chapter": chapter, "child_task_id": child_task["id"]},
        )
        await self._run_task(child_task["id"])
        child = self.store.get_task(child_task["id"]) or child_task
        child_status = str(child.get("status") or "")
        child_error = child.get("error") or {}
        child_artifacts = child.get("artifacts") or {}
        child_writeback = child_artifacts.get("writeback") or {}
        child_review_summary = child_artifacts.get("review_summary") or {}
        child_story_refresh = child_writeback.get("story_refresh") or {}

        if child_status == "awaiting_writeback_approval":
            result = {
                "chapter": chapter,
                "outcome": "stopped_for_approval",
                "stop_step": "approval-gate",
                "parent_task_id": task_id,
                "trigger_source": "guarded-chapter-runner",
                "child_task_id": child_task["id"],
                "child_task_status": child_status,
                "safe_to_continue": False,
                "story_refresh": child_story_refresh,
                "review_summary": child_review_summary,
                "next_action": {
                    "can_enqueue_next": False,
                    "next_chapter": chapter + 1,
                    "next_recommended_chapter": chapter + 1,
                    "reason": "当前章节已进入人工审批关卡，护栏推进停止。",
                    "suggested_action": "先批准或拒绝当前 write 子任务的回写，再决定是否继续。",
                },
            }
            result["operator_actions"] = self._build_guarded_runner_operator_actions(
                task_id=task_id,
                chapter=chapter,
                outcome="stopped_for_approval",
                child_task_id=child_task["id"],
                next_action=result["next_action"],
                request=request,
                child_task_status=child_status,
                blocking_reason=str(result["next_action"]["reason"]),
            )
            self._persist_guarded_runner_result(task_id, result)
            self.store.append_event(
                task_id,
                "warning",
                "Guarded runner stopped at approval gate",
                step_name=step_name,
                payload={"chapter": chapter, "child_task_id": child_task["id"]},
            )
            return "ok"

        if child_status == "failed" and str(child_error.get("code") or "") == "REVIEW_GATE_BLOCKED":
            result = {
                "chapter": chapter,
                "outcome": "blocked_by_review",
                "stop_step": "review-summary",
                "parent_task_id": task_id,
                "trigger_source": "guarded-chapter-runner",
                "child_task_id": child_task["id"],
                "child_task_status": child_status,
                "safe_to_continue": False,
                "story_refresh": child_story_refresh,
                "review_summary": child_review_summary,
                "next_action": {
                    "can_enqueue_next": False,
                    "next_chapter": chapter + 1,
                    "next_recommended_chapter": chapter + 1,
                    "reason": str(child_error.get("message") or "审查关卡阻止继续执行。"),
                    "suggested_action": "先修复子任务中的审查问题，再决定是否继续下一章。",
                },
            }
            result["operator_actions"] = self._build_guarded_runner_operator_actions(
                task_id=task_id,
                chapter=chapter,
                outcome="blocked_by_review",
                child_task_id=child_task["id"],
                next_action=result["next_action"],
                request=request,
                child_task_status=child_status,
                blocking_reason=str(result["next_action"]["reason"]),
            )
            self._persist_guarded_runner_result(task_id, result)
            self.store.append_event(
                task_id,
                "warning",
                "Guarded runner blocked by review gate",
                step_name=step_name,
                payload={"chapter": chapter, "child_task_id": child_task["id"], "error_code": child_error.get("code")},
            )
            return "ok"

        if child_status != "completed":
            error_info = {
                "code": str(child_error.get("code") or "GUARDED_CHILD_TASK_FAILED"),
                "message": str(child_error.get("message") or f"护栏推进子任务未成功完成：{child_status or 'unknown'}"),
            }
            failure_reason = str(error_info.get("message") or "")
            result = {
                "chapter": chapter,
                "outcome": "child_task_failed",
                "stop_step": str(child.get("current_step") or "guarded-chapter-runner"),
                "parent_task_id": task_id,
                "trigger_source": "guarded-chapter-runner",
                "child_task_id": child_task["id"],
                "child_task_status": child_status,
                "safe_to_continue": False,
                "story_refresh": child_story_refresh,
                "review_summary": child_review_summary,
                "next_action": {
                    "can_enqueue_next": False,
                    "next_chapter": chapter + 1,
                    "next_recommended_chapter": chapter + 1,
                    "reason": failure_reason,
                    "suggested_action": "先修复子任务中的失败问题，再决定是否继续下一章。",
                },
            }
            result["operator_actions"] = self._build_guarded_runner_operator_actions(
                task_id=task_id,
                chapter=chapter,
                outcome="child_task_failed",
                child_task_id=child_task["id"],
                next_action=result["next_action"],
                request=request,
                child_task_status=child_status,
                blocking_reason=failure_reason,
            )
            self.store.mark_failed(task_id, step_name, error_info)
            self.store.append_event(
                task_id,
                "error",
                "Guarded runner child task failed",
                step_name=step_name,
                payload={"chapter": chapter, "child_task_id": child_task["id"], "child_status": child_status, "error_code": error_info["code"]},
            )
            self._persist_guarded_runner_result(task_id, result, success=False)
            return "failed"

        next_action = self._build_guarded_runner_next_action(chapter, child_story_refresh)
        result = {
            "chapter": chapter,
            "outcome": "completed_one_chapter",
            "stop_step": "data-sync",
            "parent_task_id": task_id,
            "trigger_source": "guarded-chapter-runner",
            "child_task_id": child_task["id"],
            "child_task_status": child_status,
            "safe_to_continue": bool(next_action.get("can_enqueue_next")),
            "story_refresh": child_story_refresh,
            "director_alignment": child_writeback.get("director_alignment") or {},
            "story_alignment": child_writeback.get("story_alignment") or {},
            "review_summary": child_review_summary,
            "next_action": next_action,
        }
        result["operator_actions"] = self._build_guarded_runner_operator_actions(
            task_id=task_id,
            chapter=chapter,
            outcome="completed_one_chapter",
            child_task_id=child_task["id"],
            next_action=next_action,
            request=request,
            child_task_status=child_status,
        )
        self._persist_guarded_runner_result(task_id, result)
        self.store.append_event(
            task_id,
            "info",
            "Guarded runner completed one chapter",
            step_name=step_name,
            payload={"chapter": chapter, "child_task_id": child_task["id"], "next_chapter": next_action.get("next_chapter")},
        )
        return "ok"

    async def _run_guarded_batch_runner(self, task_id: str, task: Dict[str, Any]) -> str:
        step_name = "guarded-batch-runner"
        request = dict(task.get("request") or {})
        start_chapter = self._resolve_guarded_batch_start_chapter(request)
        requested_max_chapters = self._resolve_guarded_batch_max_chapters(request)
        request["start_chapter"] = start_chapter
        request["max_chapters"] = requested_max_chapters
        self.store.update_task(
            task_id,
            request=request,
            root_task_id=str(task.get("root_task_id") or task_id),
            trigger_source=str(task.get("trigger_source") or "manual"),
        )

        root_task_id = str(task.get("root_task_id") or task_id)
        completed_chapters = 0
        current_chapter = start_chapter
        runs: List[Dict[str, Any]] = []
        latest_result: Dict[str, Any] = {}

        while completed_chapters < requested_max_chapters:
            child_request = {
                "chapter": current_chapter,
                "mode": str(request.get("mode") or "standard"),
                "require_manual_approval": bool(request.get("require_manual_approval", True)),
                "project_root": str(request.get("project_root") or self.project_root),
                "options": request.get("options") if isinstance(request.get("options"), dict) else {},
            }
            child_task = self._create_task_record("guarded-write", child_request)
            child_task = self.store.update_task(
                child_task["id"],
                parent_task_id=task_id,
                parent_step_name=step_name,
                root_task_id=root_task_id,
                trigger_source="guarded-batch-write",
            )
            self.store.append_event(
                task_id,
                "info",
                "Guarded batch child task created",
                step_name=step_name,
                payload={"chapter": current_chapter, "child_task_id": child_task["id"], "completed_chapters": completed_chapters},
            )
            await self._run_task(child_task["id"])

            child = self.store.get_task(child_task["id"]) or child_task
            child_status = str(child.get("status") or "")
            child_error = child.get("error") or {}
            child_result = self._get_supervisor_guarded_result(child)
            child_next_action = child_result.get("next_action") or {}
            run_record = {
                "chapter": current_chapter,
                "task_id": child_task["id"],
                "task_status": child_status,
                "outcome": str(child_result.get("outcome") or ""),
                "safe_to_continue": bool(child_result.get("safe_to_continue")),
                "stop_step": str(child_result.get("stop_step") or ""),
                "next_chapter": int(child_next_action.get("next_chapter") or (current_chapter + 1)),
            }
            runs.append(run_record)

            if child_status != "completed":
                failure_reason = str(child_error.get("message") or child_status or "unknown")
                failure_detail = f"护栏子任务未成功完成：{failure_reason}"
                latest_result = self._build_guarded_batch_result(
                    start_chapter=start_chapter,
                    requested_max_chapters=requested_max_chapters,
                    completed_chapters=completed_chapters,
                    outcome="child_task_failed",
                    stop_reason="child_task_failed",
                    stop_step=str(child.get("current_step") or child_result.get("stop_step") or "guarded-chapter-runner"),
                    last_child_task_id=child_task["id"],
                    last_child_task_status=child_status,
                    safe_to_continue=False,
                    runs=runs,
                    story_refresh=(child.get("artifacts") or {}).get("writeback", {}).get("story_refresh") or {},
                    story_alignment=(child.get("artifacts") or {}).get("writeback", {}).get("story_alignment") or {},
                    director_alignment=(child.get("artifacts") or {}).get("writeback", {}).get("director_alignment") or {},
                    review_summary=(child.get("artifacts") or {}).get("review_summary") or {},
                    next_action={
                        "can_enqueue_next": False,
                        "next_chapter": current_chapter,
                        "next_recommended_chapter": current_chapter,
                        "reason": failure_detail,
                        "suggested_action": "先查看失败的护栏子任务，再决定是否继续批量推进。",
                    },
                )
                latest_result["operator_actions"] = self._build_guarded_batch_operator_actions(
                    task_id=task_id,
                    start_chapter=start_chapter,
                    completed_chapters=completed_chapters,
                    requested_max_chapters=requested_max_chapters,
                    outcome="child_task_failed",
                    last_child_task_id=child_task["id"],
                    next_action=latest_result["next_action"],
                    request=request,
                    blocking_reason=failure_detail,
                )
                self._persist_guarded_batch_runner_result(task_id, latest_result, success=False)
                error_info = {
                    "code": str(child_error.get("code") or "GUARDED_BATCH_CHILD_TASK_FAILED"),
                    "message": f"护栏批量推进在第 {current_chapter} 章停止：{failure_detail}",
                }
                self.store.mark_failed(task_id, step_name, error_info)
                self.store.append_event(
                    task_id,
                    "error",
                    "Guarded batch child task failed",
                    step_name=step_name,
                    payload={"chapter": current_chapter, "child_task_id": child_task["id"], "child_status": child_status, "error_code": child_error.get("code")},
                )
                return "failed"

            if str(child_result.get("outcome") or "") != "completed_one_chapter":
                latest_result = self._build_guarded_batch_result(
                    start_chapter=start_chapter,
                    requested_max_chapters=requested_max_chapters,
                    completed_chapters=completed_chapters,
                    outcome=str(child_result.get("outcome") or "child_task_failed"),
                    stop_reason=str(child_result.get("outcome") or "child_task_failed"),
                    stop_step=str(child_result.get("stop_step") or "guarded-chapter-runner"),
                    last_child_task_id=child_task["id"],
                    last_child_task_status=child_status,
                    safe_to_continue=False,
                    runs=runs,
                    story_refresh=child_result.get("story_refresh") or {},
                    story_alignment=child_result.get("story_alignment") or {},
                    director_alignment=child_result.get("director_alignment") or {},
                    review_summary=child_result.get("review_summary") or {},
                    next_action=child_next_action,
                )
                latest_result["operator_actions"] = self._build_guarded_batch_operator_actions(
                    task_id=task_id,
                    start_chapter=start_chapter,
                    completed_chapters=completed_chapters,
                    requested_max_chapters=requested_max_chapters,
                    outcome=str(child_result.get("outcome") or "child_task_failed"),
                    last_child_task_id=child_task["id"],
                    next_action=child_next_action,
                    request=request,
                    blocking_reason=str(child_next_action.get("reason") or child_result.get("stop_step") or ""),
                    resume_from_step=str((child_result.get("story_refresh") or {}).get("recommended_resume_from") or "story-director"),
                )
                self._persist_guarded_batch_runner_result(task_id, latest_result)
                self.store.append_event(
                    task_id,
                    "warning",
                    "Guarded batch stopped by child outcome",
                    step_name=step_name,
                    payload={"chapter": current_chapter, "child_task_id": child_task["id"], "outcome": child_result.get("outcome")},
                )
                return "ok"

            completed_chapters += 1
            latest_result = self._build_guarded_batch_result(
                start_chapter=start_chapter,
                requested_max_chapters=requested_max_chapters,
                completed_chapters=completed_chapters,
                outcome="completed_requested_batch" if completed_chapters >= requested_max_chapters else "completed_one_chapter",
                stop_reason="completed_requested_batch" if completed_chapters >= requested_max_chapters else "in_progress",
                stop_step=str(child_result.get("stop_step") or "data-sync"),
                last_child_task_id=child_task["id"],
                last_child_task_status=child_status,
                safe_to_continue=bool(child_result.get("safe_to_continue")) and completed_chapters < requested_max_chapters,
                runs=runs,
                story_refresh=child_result.get("story_refresh") or {},
                story_alignment=child_result.get("story_alignment") or {},
                director_alignment=child_result.get("director_alignment") or {},
                review_summary=child_result.get("review_summary") or {},
                next_action=child_next_action,
            )
            latest_result["operator_actions"] = self._build_guarded_batch_operator_actions(
                task_id=task_id,
                start_chapter=start_chapter,
                completed_chapters=completed_chapters,
                requested_max_chapters=requested_max_chapters,
                outcome="completed_requested_batch" if completed_chapters >= requested_max_chapters else "completed_one_chapter",
                last_child_task_id=child_task["id"],
                next_action=child_next_action,
                request=request,
            )
            self._persist_guarded_batch_runner_result(task_id, latest_result)

            if completed_chapters >= requested_max_chapters:
                latest_result["outcome"] = "completed_requested_batch"
                latest_result["stop_reason"] = "completed_requested_batch"
                latest_result["safe_to_continue"] = False
                latest_result["next_action"] = {
                    "can_enqueue_next": False,
                    "next_chapter": int(child_next_action.get("next_chapter") or (current_chapter + 1)),
                    "next_recommended_chapter": int(child_next_action.get("next_recommended_chapter") or child_next_action.get("next_chapter") or (current_chapter + 1)),
                    "reason": f"已按请求上限完成 {completed_chapters} 章护栏推进。",
                    "suggested_action": "如需继续，请根据当前结果再创建下一批护栏推进任务。",
                }
                self._persist_guarded_batch_runner_result(task_id, latest_result)
                self.store.append_event(
                    task_id,
                    "info",
                    "Guarded batch completed requested chapters",
                    step_name=step_name,
                    payload={"completed_chapters": completed_chapters, "last_child_task_id": child_task["id"]},
                )
                return "ok"

            if not child_result.get("safe_to_continue"):
                blocked_outcome = "blocked_story_refresh" if (child_result.get("story_refresh") or {}).get("should_refresh") else str(child_result.get("outcome") or "child_task_failed")
                latest_result["outcome"] = blocked_outcome
                latest_result["stop_reason"] = blocked_outcome
                latest_result["safe_to_continue"] = False
                latest_result["operator_actions"] = self._build_guarded_batch_operator_actions(
                    task_id=task_id,
                    start_chapter=start_chapter,
                    completed_chapters=completed_chapters,
                    requested_max_chapters=requested_max_chapters,
                    outcome=blocked_outcome,
                    last_child_task_id=child_task["id"],
                    next_action=child_next_action,
                    request=request,
                    blocking_reason=str((child_result.get("next_action") or {}).get("reason") or child_result.get("stop_step") or ""),
                    resume_from_step=str((child_result.get("story_refresh") or {}).get("recommended_resume_from") or "story-director"),
                )
                self._persist_guarded_batch_runner_result(task_id, latest_result)
                self.store.append_event(
                    task_id,
                    "warning",
                    "Guarded batch stopped by child outcome",
                    step_name=step_name,
                    payload={"chapter": current_chapter, "child_task_id": child_task["id"], "outcome": child_result.get("outcome")},
                )
                return "ok"

            current_chapter = int(child_next_action.get("next_chapter") or (current_chapter + 1))

        return "ok"

    def _build_guarded_batch_result(
        self,
        *,
        start_chapter: int,
        requested_max_chapters: int,
        completed_chapters: int,
        outcome: str,
        stop_reason: str,
        stop_step: str,
        last_child_task_id: str,
        last_child_task_status: str,
        safe_to_continue: bool,
        runs: List[Dict[str, Any]],
        story_refresh: Dict[str, Any],
        story_alignment: Dict[str, Any],
        director_alignment: Dict[str, Any],
        review_summary: Dict[str, Any],
        next_action: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "start_chapter": start_chapter,
            "requested_max_chapters": requested_max_chapters,
            "completed_chapters": completed_chapters,
            "outcome": outcome,
            "stop_reason": stop_reason,
            "stop_step": stop_step,
            "last_child_task_id": last_child_task_id,
            "last_child_task_status": last_child_task_status,
            "safe_to_continue": safe_to_continue,
            "story_refresh": story_refresh,
            "story_alignment": story_alignment,
            "director_alignment": director_alignment,
            "review_summary": review_summary,
            "runs": runs,
            "next_action": next_action,
        }

    def _persist_guarded_batch_runner_result(self, task_id: str, result: Dict[str, Any], *, success: bool = True) -> None:
        self.store.save_step_result(task_id, "guarded-batch-runner", {"success": success, "structured_output": result})
        latest_task = self.store.get_task(task_id) or {}
        artifacts = dict(latest_task.get("artifacts") or {})
        artifacts["guarded_batch_runner"] = result
        self.store.update_task(task_id, artifacts=artifacts)

    def _persist_guarded_runner_result(self, task_id: str, result: Dict[str, Any], *, success: bool = True) -> None:
        self.store.save_step_result(task_id, "guarded-chapter-runner", {"success": success, "structured_output": result})
        latest_task = self.store.get_task(task_id) or {}
        artifacts = dict(latest_task.get("artifacts") or {})
        artifacts["guarded_runner"] = result
        self.store.update_task(task_id, artifacts=artifacts)

    def _resolve_guarded_batch_start_chapter(self, request: Dict[str, Any]) -> int:
        try:
            requested = int(request.get("start_chapter") or request.get("chapter") or 0)
        except (TypeError, ValueError):
            requested = 0
        if requested > 0:
            return requested
        progress = self._read_state_data().get("progress") or {}
        try:
            current_chapter = max(0, int(progress.get("current_chapter") or 0))
        except (TypeError, ValueError):
            current_chapter = 0
        return max(1, current_chapter + 1)

    def _resolve_guarded_batch_max_chapters(self, request: Dict[str, Any]) -> int:
        try:
            requested = int(request.get("max_chapters") or 1)
        except (TypeError, ValueError):
            requested = 1
        return max(1, requested)

    def _resolve_guarded_runner_chapter(self, request: Dict[str, Any]) -> int:
        try:
            requested = int(request.get("chapter") or 0)
        except (TypeError, ValueError):
            requested = 0
        if requested > 0:
            return requested
        progress = self._read_state_data().get("progress") or {}
        try:
            current_chapter = max(0, int(progress.get("current_chapter") or 0))
        except (TypeError, ValueError):
            current_chapter = 0
        return max(1, current_chapter + 1)

    def _load_previous_story_refresh(self, chapter: int) -> Dict[str, Any]:
        if chapter <= 1:
            return {}
        previous_chapter = chapter - 1
        candidates: List[Dict[str, Any]] = []
        for candidate in self.store.list_tasks(limit=200):
            if candidate.get("task_type") != "write":
                continue
            if candidate.get("project_root") != str(self.project_root):
                continue
            if int((candidate.get("request") or {}).get("chapter") or 0) != previous_chapter:
                continue
            refresh = (((candidate.get("artifacts") or {}).get("writeback") or {}).get("story_refresh") or {})
            if refresh:
                candidates.append({"task": candidate, "story_refresh": refresh})
        if not candidates:
            return {}
        candidates.sort(
            key=lambda item: self._parse_iso_datetime((item["task"] or {}).get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        return candidates[0]["story_refresh"]

    def _build_guarded_runner_next_action(self, chapter: int, story_refresh: Dict[str, Any]) -> Dict[str, Any]:
        next_chapter = max(1, int(chapter) + 1)
        if story_refresh.get("should_refresh"):
            return {
                "can_enqueue_next": False,
                "next_chapter": next_chapter,
                "next_recommended_chapter": next_chapter,
                "reason": "本章 data-sync 已建议刷新 story plan，暂不继续自动推进。",
                "suggested_action": story_refresh.get("suggested_action") or "先从 Story Director 重新规划，再决定是否继续下一章。",
            }
        return {
            "can_enqueue_next": True,
            "next_chapter": next_chapter,
            "next_recommended_chapter": next_chapter,
            "reason": "本次仅成功推进一章，且未触发新的 story refresh 护栏。",
            "suggested_action": f"如需继续，可手动创建第 {next_chapter} 章的护栏推进或常规 write 任务。",
        }

    async def _run_external_step(self, task_id: str, task: Dict[str, Any], step: Dict[str, Any]) -> Optional[StepResult]:
        step_name = step["name"]
        preflight_result = self._run_plan_preflight(task_id, task, step)
        if preflight_result is not None:
            self.store.mark_failed(task_id, step_name, preflight_result)
            return None

        refreshed_task = self.store.get_task(task_id) or task
        prompt_bundle = self._build_prompt_bundle(refreshed_task, step)
        result = await self._execute_runner_step(task_id, step_name, prompt_bundle)

        if result.success:
            return result

        retried_result = await self._maybe_retry_invalid_output_step(task_id, task, step, result.error or {}, result=result)
        if retried_result is not None:
            if retried_result.success:
                return retried_result
            result = retried_result

        failure_error = self._normalize_invalid_output_error(
            task=task,
            step=step,
            error_info=result.error or {"code": "STEP_FAILED", "message": "step execution failed"},
            result=result,
        )
        self.store.mark_failed(
            task_id,
            step_name,
            failure_error,
        )
        return None

    async def _execute_runner_step(
        self,
        task_id: str,
        step_name: str,
        prompt_bundle: Dict[str, Any],
        *,
        attempt: int = 1,
    ) -> StepResult:
        request_timeout_seconds = self._runner_timeout_seconds(step_name)
        watchdog_timeout_seconds = self._watchdog_timeout_seconds(step_name)
        prompt_metrics = dict(prompt_bundle.get("context_metrics") or {})
        base_payload = {
            "attempt": attempt,
            "retry_count": max(0, attempt - 1),
            "retryable": True,
            "timeout_seconds": request_timeout_seconds,
            "watchdog_timeout_seconds": watchdog_timeout_seconds,
        }
        self.store.append_event(
            task_id,
            "info",
            "prompt_compiled",
            step_name=step_name,
            payload=base_payload | prompt_metrics,
        )
        self.store.append_event(
            task_id,
            "info",
            "llm_request_started",
            step_name=step_name,
            payload=base_payload,
        )
        loop = asyncio.get_running_loop()
        heartbeat_seconds = self._runner_heartbeat_seconds(step_name)
        started_at = loop.time()
        progress_callback = self._make_runner_progress_callback(loop, task_id, step_name, base_payload)
        runner_task = asyncio.create_task(
            asyncio.to_thread(
                self.runner.run,
                prompt_bundle["step_spec"],
                self.project_root,
                prompt_bundle,
                progress_callback,
            )
        )
        try:
            while True:
                elapsed = loop.time() - started_at
                remaining = watchdog_timeout_seconds - elapsed
                if remaining <= 0:
                    raise asyncio.TimeoutError
                try:
                    result = await asyncio.wait_for(asyncio.shield(runner_task), timeout=min(heartbeat_seconds, remaining))
                    break
                except asyncio.TimeoutError:
                    if runner_task.done():
                        result = await runner_task
                        break
                    progress_callback(
                        "step_heartbeat",
                        {
                            "elapsed_seconds": int(max(0, elapsed)),
                            "waiting_seconds": int(max(0, elapsed)),
                            "phase_detail": "request_in_flight",
                        },
                    )
        except asyncio.TimeoutError:
            runner_task.cancel()
            result = self._build_watchdog_timeout_result(
                task_id,
                step_name,
                request_timeout_seconds=request_timeout_seconds,
                watchdog_timeout_seconds=watchdog_timeout_seconds,
                attempt=attempt,
            )
        if result.metadata is None:
            result.metadata = {}
        result.metadata["attempt"] = max(int(result.metadata.get("attempt", 1)), attempt)
        config_signature = self._current_llm_config_signature()
        if config_signature:
            result.metadata["llm_config_signature"] = config_signature
        self._record_step_result(task_id, step_name, result)
        return result

    def _make_runner_progress_callback(
        self,
        loop: asyncio.AbstractEventLoop,
        task_id: str,
        step_name: str,
        base_payload: Dict[str, Any],
    ):
        def emit(event_name: str, payload: Optional[Dict[str, Any]] = None) -> None:
            merged_payload = dict(base_payload)
            if payload:
                merged_payload.update(payload)

            def _append() -> None:
                self.store.append_event(
                    task_id,
                    "info",
                    event_name,
                    step_name=step_name,
                    payload=merged_payload,
                )

            loop.call_soon_threadsafe(_append)

        return emit

    def _runner_heartbeat_seconds(self, step_name: str) -> float:
        normalized = str(step_name or "").strip().lower()
        if normalized == "plan":
            return 10.0
        if normalized in {"draft", "polish"}:
            return 8.0
        return 12.0

    def _runner_timeout_seconds(self, step_name: str) -> int:
        timeout_method = getattr(self.runner, "_timeout_seconds_for_step", None)
        if callable(timeout_method):
            try:
                return max(1, int(timeout_method(step_name)))
            except Exception:
                pass
        timeout_ms = int(getattr(self.runner, "timeout_ms", 120000) or 120000)
        return max(1, timeout_ms // 1000)

    def _watchdog_timeout_seconds(self, step_name: str) -> float:
        request_timeout_seconds = float(self._runner_timeout_seconds(step_name))
        retry_count_method = getattr(self.runner, "_max_retries_for_step", None)
        if callable(retry_count_method):
            try:
                retry_count = max(0, int(retry_count_method(step_name)))
            except Exception:
                retry_count = max(0, int(getattr(self.runner, "max_request_retries", 0) or 0))
        else:
            retry_count = max(0, int(getattr(self.runner, "max_request_retries", 0) or 0))
        retry_backoff_method = getattr(self.runner, "_retry_backoff_seconds_for_step", None)
        if callable(retry_backoff_method):
            try:
                retry_backoff_seconds = max(0.0, float(retry_backoff_method(step_name)))
            except Exception:
                retry_backoff_seconds = max(0.0, float(getattr(self.runner, "retry_backoff_seconds", 0.0) or 0.0))
        else:
            retry_backoff_seconds = max(0.0, float(getattr(self.runner, "retry_backoff_seconds", 0.0) or 0.0))
        retry_wait_budget = sum(retry_backoff_seconds * (2 ** attempt) for attempt in range(retry_count))
        grace_seconds = 15.0
        return max(request_timeout_seconds + grace_seconds, request_timeout_seconds * (retry_count + 1) + retry_wait_budget + grace_seconds)

    def _llm_run_dir(self, task_id: str, step_name: str) -> Path:
        runs_dirname = str(getattr(self.runner, "runs_dirname", "llm-runs") or "llm-runs")
        run_dir = self.project_root / ".webnovel" / "observability" / runs_dirname / f"{task_id}-{step_name}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    def _build_watchdog_timeout_result(
        self,
        task_id: str,
        step_name: str,
        *,
        request_timeout_seconds: int,
        watchdog_timeout_seconds: float,
        attempt: int,
    ) -> StepResult:
        run_dir = self._llm_run_dir(task_id, step_name)
        error_payload = {
            "success": False,
            "step_name": step_name,
            "error": {
                "code": "LLM_TIMEOUT",
                "message": "step watchdog timed out before runner returned",
                "attempt": attempt,
                "retryable": True,
                "timeout_seconds": request_timeout_seconds,
                "watchdog_timeout_seconds": watchdog_timeout_seconds,
            },
        }
        (run_dir / "error.json").write_text(json.dumps(error_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return StepResult(
            step_name=step_name,
            success=False,
            return_code=124,
            timing_ms=int(watchdog_timeout_seconds * 1000),
            stdout="",
            stderr="step watchdog timed out before runner returned",
            structured_output=None,
            prompt_file=str(run_dir / "prompt.md"),
            output_file=str(run_dir / "raw-output.txt"),
            error={
                "code": "LLM_TIMEOUT",
                "message": "step watchdog timed out before runner returned",
                "attempt": attempt,
                "retryable": True,
                "timeout_seconds": request_timeout_seconds,
                "watchdog_timeout_seconds": watchdog_timeout_seconds,
            },
            metadata={
                "attempt": attempt,
                "timeout_seconds": request_timeout_seconds,
                "watchdog_timeout_seconds": watchdog_timeout_seconds,
                "retryable": True,
            },
        )

    def _maybe_complete_plan_as_blocked(
        self,
        task_id: str,
        task: Dict[str, Any],
        step: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> bool:
        if task.get("task_type") != "plan" or step.get("name") != "plan":
            return False
        if not self._is_plan_payload_blocked(payload):
            return False

        blocking_items = self._extract_plan_blocking_items(payload)
        health = self._evaluate_plan_inputs()
        result_payload = {
            "plan_blocked": True,
            "reason": "model_blocked",
            "blocking_items": blocking_items,
            "next_step": "请先回到总览页补齐规划必填信息后再重新运行 plan。",
            "fill_template": build_planning_fill_template(),
            "readiness": health,
            "raw_payload": payload,
        }
        error_info = self._build_plan_blocked_error(result_payload)
        self.store.save_step_result(task_id, step["name"], {"success": False, "structured_output": result_payload, "error": error_info})
        self._persist_plan_blocked_state(
            task_id,
            task,
            reason="model_blocked",
            blocking_items=blocking_items,
            readiness=health,
        )
        latest_task = self.store.get_task(task_id) or task
        latest_artifacts = dict(latest_task.get("artifacts") or {})
        latest_artifacts.update(
            {
                "plan_blocked": True,
                "blocking_items": blocking_items,
                "next_step": result_payload["next_step"],
                "fill_template": result_payload["fill_template"],
                "plan_health_check": health,
            }
        )
        self.store.update_task(task_id, artifacts=latest_artifacts)
        self.store.append_event(
            task_id,
            "warning",
            "plan_blocked",
            step_name=step["name"],
            payload=result_payload,
        )
        self.store.mark_failed(task_id, step["name"], error_info)
        return True

    def _record_step_result(self, task_id: str, step_name: str, result: StepResult) -> None:
        config_signature = self._current_llm_config_signature()
        if result.metadata is None:
            result.metadata = {}
        if config_signature:
            result.metadata["llm_config_signature"] = config_signature
        result_dict = result.to_dict()
        self.store.save_step_result(task_id, step_name, result_dict)
        payload = self._build_step_event_payload(result)
        if config_signature and "llm_config_signature" not in payload:
            payload["llm_config_signature"] = config_signature
        if result.success:
            self.store.append_event(
                task_id,
                "info",
                "llm_request_finished",
                step_name=step_name,
                payload=payload,
            )
        else:
            error_code = str((result.error or {}).get("code") or "")
            self.store.append_event(
                task_id,
                "warning" if error_code == "LLM_TIMEOUT" else "error",
                "llm_request_timed_out" if error_code == "LLM_TIMEOUT" else "llm_request_failed",
                step_name=step_name,
                payload=payload,
            )
        self.store.append_event(
            task_id,
            "info" if result.success else "error",
            f"{'Step completed' if result.success else 'Step failed'}: {step_name}",
            step_name=step_name,
            payload=payload,
        )
        metadata = result.metadata or {}
        if metadata.get("json_extraction_recovered"):
            self.store.append_event(
                task_id,
                "info",
                "json_extraction_recovered",
                step_name=step_name,
                payload={
                    "attempt": metadata.get("attempt", 1),
                    "parse_stage": metadata.get("parse_stage"),
                },
            )
        if result.error and result.error.get("code") == "INVALID_STEP_OUTPUT" and result.error.get("raw_output_present"):
            self.store.append_event(
                task_id,
                "warning",
                "raw_output_parse_failed",
                step_name=step_name,
                payload={
                    "attempt": result.error.get("attempt", metadata.get("attempt", 1)),
                    "parse_stage": result.error.get("parse_stage", metadata.get("parse_stage")),
                    "error_code": result.error.get("code"),
                    "recoverability": ((result.error.get("details") or {}).get("recoverability")),
                    "suggested_resume_step": ((result.error.get("details") or {}).get("suggested_resume_step")),
                },
            )

    def _current_llm_config_signature(self) -> Optional[str]:
        fingerprint = {
            "provider": str(getattr(self.runner, "provider", None) or os.environ.get("WEBNOVEL_LLM_PROVIDER") or "").strip().lower(),
            "base_url": str(
                getattr(self.runner, "base_url", None)
                or os.environ.get("WEBNOVEL_LLM_BASE_URL")
                or os.environ.get("OPENAI_BASE_URL")
                or ""
            ).strip().rstrip("/").lower(),
            "model": str(
                getattr(self.runner, "model", None)
                or os.environ.get("WEBNOVEL_LLM_MODEL")
                or os.environ.get("OPENAI_MODEL")
                or ""
            ).strip(),
            "mode": str(getattr(self.runner, "mode", None) or os.environ.get("WEBNOVEL_LLM_MODE") or "").strip().lower(),
        }
        if not any(fingerprint.values()):
            return None
        return json.dumps(fingerprint, ensure_ascii=False, sort_keys=True)

    def _task_step_config_signature(self, task: Dict[str, Any], *, success: bool | None = None) -> Optional[str]:
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        for step_name, result in reversed(list(step_results.items())):
            if step_name not in EXTERNAL_WORKFLOW_STEPS:
                continue
            if success is not None and bool((result or {}).get("success")) is not success:
                continue
            metadata = (result or {}).get("metadata") or {}
            signature = metadata.get("llm_config_signature")
            if signature:
                return str(signature)
        return None

    def _build_step_event_payload(self, result: StepResult) -> Dict[str, Any]:
        metadata = result.metadata or {}
        error = result.error or {}
        payload: Dict[str, Any] = {
            "timing_ms": result.timing_ms,
            "attempt": metadata.get("attempt", error.get("attempt", 1)),
            "timeout_seconds": metadata.get("timeout_seconds", error.get("timeout_seconds")),
            "error": result.error,
        }
        for key in (
            "error_code",
            "retryable",
            "http_status",
            "retry_count",
            "parse_stage",
            "raw_output_present",
            "missing_required_keys",
            "watchdog_timeout_seconds",
            "llm_config_signature",
        ):
            if key == "error_code":
                value = error.get("code")
            else:
                value = error.get(key, metadata.get(key))
            if value is not None:
                payload[key] = value
        details = error.get("details") if isinstance(error.get("details"), dict) else {}
        for key in ("recoverability", "suggested_resume_step"):
            value = details.get(key)
            if value is not None:
                payload[key] = value
        return payload

    def _read_state_data(self) -> Dict[str, Any]:
        return read_project_state(self.project_root, strict=False)

    def _update_state_data(self, mutator) -> Dict[str, Any]:
        return update_project_state(self.project_root, mutator, strict=False)

    def _is_plan_payload_blocked(self, payload: Dict[str, Any]) -> bool:
        volume_plan = payload.get("volume_plan") or {}
        status = str(volume_plan.get("status") or payload.get("status") or "").strip().upper()
        return status == "BLOCKED"

    def _extract_plan_blocking_items(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        volume_plan = payload.get("volume_plan") or {}
        raw_items = payload.get("blocking_items") or volume_plan.get("blocking_items") or volume_plan.get("missing_items") or []
        items: List[Dict[str, Any]] = []
        for item in raw_items:
            if isinstance(item, dict):
                label = str(item.get("label") or item.get("field") or item.get("name") or "").strip()
                if label:
                    items.append(
                        {
                            "field": str(item.get("field") or "").strip(),
                            "label": label,
                            "reason": str(item.get("reason") or item.get("message") or "").strip(),
                        }
                    )
            elif isinstance(item, str) and item.strip():
                items.append({"field": "", "label": item.strip(), "reason": ""})
        if items:
            return items
        reason = str(volume_plan.get("reason") or payload.get("message") or "").strip()
        if reason:
            return [{"field": "", "label": reason, "reason": ""}]
        return []

    def _persist_plan_blocked_state(
        self,
        task_id: str,
        task: Dict[str, Any],
        *,
        reason: str,
        blocking_items: List[Dict[str, Any]],
        readiness: Dict[str, Any],
    ) -> None:
        latest_task = self.store.get_task(task_id) or task

        def _mutate(state_data: Dict[str, Any]) -> None:
            planning = state_data.setdefault("planning", {})
            planning["readiness"] = readiness
            planning["last_blocked"] = {
                "task_id": task_id,
                "volume": str((task.get("request") or {}).get("volume") or "1"),
                "reason": reason,
                "blocking_items": blocking_items,
                "next_step": "请在总览页补齐规划必填信息后重新运行 plan。",
                "updated_at": latest_task.get("updated_at"),
            }

        self._update_state_data(_mutate)

    async def _maybe_retry_invalid_output_step(
        self,
        task_id: str,
        task: Dict[str, Any],
        step: Dict[str, Any],
        error_info: Dict[str, Any],
        *,
        result: Optional[StepResult] = None,
    ) -> Optional[StepResult]:
        if not self._should_auto_retry_invalid_output_step(task, step, error_info, result=result):
            return None

        attempt = int(((result.metadata or {}) if result else {}).get("attempt", 1))
        normalized_error = self._normalize_invalid_output_error(
            task=task,
            step=step,
            error_info=error_info,
            result=result,
            recoverability="auto_retried",
        )
        self.store.append_event(
            task_id,
            "warning",
            "step_retry_scheduled",
            step_name=step["name"],
            payload={
                "attempt": attempt + 1,
                "previous_attempt": attempt,
                "retry_count": attempt,
                "retryable": normalized_error.get("retryable"),
                "reason": normalized_error.get("message"),
                "error_code": normalized_error.get("code"),
                "parse_stage": normalized_error.get("parse_stage"),
                "recoverability": (normalized_error.get("details") or {}).get("recoverability"),
                "suggested_resume_step": (normalized_error.get("details") or {}).get("suggested_resume_step"),
            },
        )
        self.store.append_event(
            task_id,
            "warning",
            "step_auto_retried",
            step_name=step["name"],
            payload={
                "attempt": attempt + 1,
                "previous_attempt": attempt,
                "retry_count": attempt,
                "retryable": normalized_error.get("retryable"),
                "reason": normalized_error.get("message"),
                "error_code": normalized_error.get("code"),
                "parse_stage": normalized_error.get("parse_stage"),
                "recoverability": (normalized_error.get("details") or {}).get("recoverability"),
                "suggested_resume_step": (normalized_error.get("details") or {}).get("suggested_resume_step"),
            },
        )
        refreshed_task = self.store.get_task(task_id) or task
        retry_note = self._build_invalid_output_retry_note(task=refreshed_task, step=step, error_info=normalized_error, result=result)
        prompt_bundle = self._build_prompt_bundle(refreshed_task, step, retry_note=retry_note)
        self.store.append_event(
            task_id,
            "info",
            "step_retry_started",
            step_name=step["name"],
            payload={
                "attempt": attempt + 1,
                "retry_count": attempt,
                "retryable": normalized_error.get("retryable"),
            },
        )
        retried_result = await self._execute_runner_step(task_id, step["name"], prompt_bundle, attempt=attempt + 1)
        return retried_result

    def _should_auto_retry_invalid_output_step(
        self,
        task: Dict[str, Any],
        step: Dict[str, Any],
        error_info: Dict[str, Any],
        *,
        result: Optional[StepResult] = None,
    ) -> bool:
        task_type = str(task.get("task_type") or "").strip().lower()
        step_name = str(step.get("name") or "").strip().lower()
        if (task_type, step_name) not in INVALID_OUTPUT_AUTO_RETRY_STEPS:
            return False
        if str(error_info.get("code") or "") != "INVALID_STEP_OUTPUT":
            return False
        attempt = int(((result.metadata or {}) if result else {}).get("attempt", error_info.get("attempt", 1)) or 1)
        if attempt >= 2:
            return False
        return self._supports_invalid_output_recovery(error_info, result=result)

    def _build_invalid_output_retry_note(
        self,
        *,
        task: Dict[str, Any],
        step: Dict[str, Any],
        error_info: Dict[str, Any],
        result: Optional[StepResult] = None,
    ) -> str:
        task_type = str(task.get("task_type") or "").strip().lower()
        step_name = str(step.get("name") or "").strip().lower()
        parse_stage = str(error_info.get("parse_stage") or ((result.metadata or {}) if result else {}).get("parse_stage") or "").strip()
        common = (
            "Previous attempt failed because the response was not valid JSON. "
            "Return exactly one valid JSON object with no prose, no markdown fences, and no trailing commentary."
        )
        if task_type == "write" and step_name == "context":
            return (
                f"{common}\n"
                f"Failure stage: {parse_stage or 'invalid_json'}.\n"
                "Keep `task_brief` and `contract_v2` concise and structured. "
                "`draft_prompt` must be a short plain-text string, not a full design document. "
                "Use escaped \\n inside the JSON string if line breaks are needed, and keep `draft_prompt` under 2400 characters."
            )
        return f"{common}\nFailure stage: {parse_stage or 'invalid_json'}."

    def _supports_invalid_output_recovery(
        self,
        error_info: Dict[str, Any],
        *,
        result: Optional[StepResult] = None,
    ) -> bool:
        details = error_info.get("details") if isinstance(error_info.get("details"), dict) else {}
        parse_stage = str(
            error_info.get("parse_stage")
            or details.get("parse_stage")
            or ((result.metadata or {}) if result else {}).get("parse_stage")
            or ""
        ).strip()
        missing_required_keys = list(
            error_info.get("missing_required_keys")
            or details.get("missing_required_keys")
            or ((result.metadata or {}) if result else {}).get("missing_required_keys")
            or []
        )
        if missing_required_keys:
            return True
        if parse_stage in INVALID_OUTPUT_RECOVERABLE_PARSE_STAGES:
            return True
        if result is not None and str(result.stdout or "").strip():
            return True
        return bool(error_info.get("raw_output_present") or details.get("raw_output_present"))

    def _normalize_invalid_output_error(
        self,
        *,
        task: Dict[str, Any],
        step: Dict[str, Any],
        error_info: Dict[str, Any],
        result: Optional[StepResult] = None,
        recoverability: Optional[str] = None,
    ) -> Dict[str, Any]:
        if str(error_info.get("code") or "") != "INVALID_STEP_OUTPUT":
            return error_info
        metadata = (result.metadata or {}) if result else {}
        existing_details = error_info.get("details") if isinstance(error_info.get("details"), dict) else {}
        parse_stage = str(
            error_info.get("parse_stage")
            or existing_details.get("parse_stage")
            or metadata.get("parse_stage")
            or ("missing_required_keys" if error_info.get("missing_required_keys") else "")
        ).strip()
        missing_required_keys = list(
            error_info.get("missing_required_keys")
            or existing_details.get("missing_required_keys")
            or metadata.get("missing_required_keys")
            or []
        )
        raw_output_present = bool(
            error_info.get("raw_output_present")
            if error_info.get("raw_output_present") is not None
            else existing_details.get("raw_output_present")
        )
        if result is not None and not raw_output_present:
            raw_output_present = bool(str(result.stdout or "").strip())
        attempt = int(metadata.get("attempt", error_info.get("attempt", 1)) or 1)
        retry_count = int(metadata.get("retry_count", max(0, attempt - 1)) or 0)
        recoverable = self._supports_invalid_output_recovery(
            {
                **error_info,
                "parse_stage": parse_stage,
                "missing_required_keys": missing_required_keys,
                "raw_output_present": raw_output_present,
                "details": existing_details,
            },
            result=result,
        )
        if not recoverability:
            if attempt >= 2:
                recoverability = "terminal"
            elif recoverable:
                recoverability = "retriable"
            else:
                recoverability = "terminal"
        suggested_resume_step = str(
            existing_details.get("suggested_resume_step")
            or error_info.get("suggested_resume_step")
            or step.get("name")
            or task.get("current_step")
            or ""
        ).strip()
        normalized = dict(error_info)
        normalized["attempt"] = attempt
        normalized["retry_count"] = retry_count
        normalized["parse_stage"] = parse_stage or None
        normalized["raw_output_present"] = raw_output_present
        normalized["missing_required_keys"] = missing_required_keys
        normalized["retryable"] = recoverability != "terminal"
        normalized["suggested_resume_step"] = suggested_resume_step or None
        normalized["details"] = {
            **existing_details,
            "parse_stage": parse_stage or None,
            "raw_output_present": raw_output_present,
            "missing_required_keys": missing_required_keys,
            "recoverability": recoverability,
            "suggested_resume_step": suggested_resume_step or None,
        }
        return normalized

    def _build_prompt_bundle(self, task: Dict[str, Any], step: Dict[str, Any], *, retry_note: Optional[str] = None) -> Dict[str, Any]:
        reference_paths: List[Path] = []
        for rel_path in step.get("references", []):
            reference_paths.append((Path(__file__).resolve().parent.parent / rel_path).resolve())

        instructions = self._load_template(step.get("template"))
        if retry_note:
            instructions = f"{instructions.rstrip()}\n\n# Retry Correction\n{retry_note.strip()}"
        step_spec = dict(step)
        step_spec["instructions"] = instructions
        reference_documents = self._load_reference_documents(reference_paths, step_name=step.get("name"))
        project_context = self._collect_project_context(task, step)
        self._append_context_execution_package(project_context, task, step)
        task_input = {
            "request": task.get("request", {}),
            "project_root": task.get("project_root"),
            "prior_step_results": self._compact_prior_step_results((task.get("artifacts") or {}).get("step_results", {})),
            "review_summary": (task.get("artifacts") or {}).get("review_summary"),
            "plan_health_check": (task.get("artifacts") or {}).get("plan_health_check"),
        }
        if task.get("task_type") == "plan" or str(step.get("name") or "").strip().lower() == "plan":
            task_input["planning_profile_summary"] = self._build_plan_profile_summary()
        return {
            "task_id": task["id"],
            "task_type": task["task_type"],
            "step_name": step["name"],
            "references": [str(path) for path in reference_paths],
            "reference_documents": reference_documents,
            "project_context": project_context,
            "context_metrics": self._build_prompt_metrics(task, step, instructions, task_input, reference_documents, project_context),
            "input": task_input,
            "instructions": instructions,
            "step_spec": step_spec,
        }

    def _load_reference_documents(self, paths: List[Path], *, step_name: Optional[str] = None) -> List[Dict[str, str]]:
        documents: List[Dict[str, str]] = []
        max_chars = 6000 if str(step_name or "").strip().lower() == "plan" else 12000
        for path in paths:
            if not path.is_file():
                continue
            content = path.read_text(encoding="utf-8")
            documents.append(
                {
                    "path": self._label_reference_path(path),
                    "content": self._sanitize_reference_text(content)[:max_chars],
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
        if task.get("task_type") == "plan" or str(step.get("name") or "").strip().lower() == "plan":
            return self._collect_plan_project_context()
        request = task.get("request") or {}
        task_type = str(task.get("task_type") or "").strip().lower()
        chapter = int(request.get("chapter") or 0)
        chapter_range = self._parse_chapter_range(request.get("chapter_range"))
        project_docs: List[Dict[str, str]] = []

        self._append_snapshot(project_docs, self.project_root / ".webnovel" / "state.json", ".webnovel/state.json", 12000)
        self._append_snapshot(project_docs, self.project_root / OUTLINE_DIR_NAME / OUTLINE_SUMMARY_FILE, f"{OUTLINE_DIR_NAME}/{OUTLINE_SUMMARY_FILE}", 12000)
        self._append_setting_snapshots(project_docs)
        if task_type == "write" and chapter > 0:
            self._append_context_contract_snapshot(project_docs, chapter)
            self._append_snapshot(
                project_docs,
                self._story_plan_path(chapter),
                f"{STORY_DIRECTOR_DIR_NAME}/plan-ch{chapter:04d}.json",
                12000,
            )
            self._append_snapshot(
                project_docs,
                self._director_brief_path(chapter),
                f"{DIRECTOR_DIR_NAME}/ch{chapter:04d}.json",
                12000,
            )

        outline_dir = self.project_root / OUTLINE_DIR_NAME
        if outline_dir.is_dir():
            for candidate in sorted(outline_dir.glob("*.md"))[:2]:
                if candidate.name == OUTLINE_SUMMARY_FILE:
                    continue
                self._append_snapshot(project_docs, candidate, f"{OUTLINE_DIR_NAME}/{candidate.name}", 8000)

        if chapter_range is not None:
            start_chapter, end_chapter = chapter_range
            for current in range(start_chapter, end_chapter + 1):
                self._append_chapter_context(project_docs, current, body_max_chars=None, summary_max_chars=4000)
        elif chapter > 0:
            body_max_chars = None if task.get("task_type") in {"review", "repair"} else 8000
            self._append_chapter_context(project_docs, chapter, body_max_chars=body_max_chars, summary_max_chars=4000)
            if chapter > 1:
                prev = f"{chapter - 1:04d}"
                self._append_snapshot(project_docs, self.project_root / ".webnovel" / "summaries" / f"ch{prev}.md", f".webnovel/summaries/ch{prev}.md", 4000)

        return project_docs

    def _collect_plan_project_context(self) -> List[Dict[str, str]]:
        project_docs: List[Dict[str, str]] = []
        state_path = self.project_root / ".webnovel" / "state.json"
        self._append_snapshot(project_docs, state_path, ".webnovel/state.json", 10000)
        self._append_snapshot(project_docs, self.project_root / OUTLINE_DIR_NAME / OUTLINE_SUMMARY_FILE, f"{OUTLINE_DIR_NAME}/{OUTLINE_SUMMARY_FILE}", 10000)

        state_data = self._read_state_data()
        planning = state_data.get("planning") or {}
        project_info = state_data.get("project_info") or {}
        planning_profile = normalize_planning_profile(
            {
                **dict(planning.get("profile") or {}),
                **dict(
                    load_planning_profile(
                        self.project_root,
                        title=str(project_info.get("title") or "").strip(),
                        genre=str(project_info.get("genre") or "").strip(),
                    )
                    or {}
                ),
            },
            title=str(project_info.get("title") or "").strip(),
            genre=str(project_info.get("genre") or "").strip(),
        )
        planning_project_info = planning.get("project_info") or {}
        planning_readiness = planning.get("readiness") or {}
        if planning_profile:
            project_docs.append(
                {
                    "path": ".webnovel/planning-profile.json",
                    "content": json.dumps(planning_profile, ensure_ascii=False, indent=2)[:6000],
                }
            )
        if planning_project_info:
            project_docs.append(
                {
                    "path": ".webnovel/planning-project-info.json",
                    "content": json.dumps(planning_project_info, ensure_ascii=False, indent=2)[:3000],
                }
            )
        if planning_readiness:
            project_docs.append(
                {
                    "path": ".webnovel/planning-readiness.json",
                    "content": json.dumps(planning_readiness, ensure_ascii=False, indent=2)[:3000],
                }
            )

        outline_dir = self.project_root / OUTLINE_DIR_NAME
        if outline_dir.is_dir():
            volume_plans = sorted(
                candidate
                for candidate in outline_dir.glob("volume-*.md")
                if candidate.name != OUTLINE_SUMMARY_FILE
            )
            for candidate in volume_plans[-1:]:
                self._append_snapshot(project_docs, candidate, f"{OUTLINE_DIR_NAME}/{candidate.name}", 6000)
        return project_docs

    def _build_prompt_metrics(
        self,
        task: Dict[str, Any],
        step: Dict[str, Any],
        instructions: str,
        task_input: Dict[str, Any],
        reference_documents: List[Dict[str, str]],
        project_context: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        reference_chars = sum(len(item.get("content", "")) for item in reference_documents)
        project_chars = sum(len(item.get("content", "")) for item in project_context)
        input_chars = len(json.dumps(task_input, ensure_ascii=False))
        instructions_chars = len(instructions or "")
        metrics = {
            "reference_doc_count": len(reference_documents),
            "reference_chars": reference_chars,
            "project_doc_count": len(project_context),
            "project_chars": project_chars,
            "input_chars": input_chars,
            "instructions_chars": instructions_chars,
            "estimated_prompt_chars": reference_chars + project_chars + input_chars + instructions_chars,
        }
        if task.get("task_type") == "plan" or str(step.get("name") or "").strip().lower() == "plan":
            metrics["context_profile"] = "plan_minimal"
        return metrics

    def _compact_prior_step_results(self, step_results: Dict[str, Any]) -> Dict[str, Any]:
        compact: Dict[str, Any] = {}
        for step_name, result in (step_results or {}).items():
            if not isinstance(result, dict):
                continue
            structured_output = result.get("structured_output")
            if str(step_name or "").strip().lower() == "context":
                structured_output = self._compact_context_structured_output(structured_output)
            compact[step_name] = {
                "success": bool(result.get("success", False)),
                "structured_output": structured_output,
                "error": result.get("error"),
            }
        return compact

    def _compact_context_structured_output(self, structured_output: Any) -> Any:
        if not isinstance(structured_output, dict):
            return structured_output
        compact_output = dict(structured_output)
        draft_prompt = compact_output.get("draft_prompt")
        if isinstance(draft_prompt, str) and draft_prompt.strip():
            preview = draft_prompt.strip().replace("\r\n", "\n")
            preview = preview[:400] + ("..." if len(preview) > 400 else "")
            compact_output["draft_prompt_preview"] = preview
            compact_output["draft_prompt_ref"] = ".webnovel/context/current-draft-prompt.txt"
            compact_output["draft_prompt"] = "[stored separately in project context]"
        contract_v2 = compact_output.get("contract_v2")
        if isinstance(contract_v2, dict):
            allowed_keys = (
                "目标",
                "阻力",
                "代价",
                "本章变化",
                "未闭合问题",
                "核心冲突一句话",
                "开头类型",
                "情绪节奏",
                "信息密度",
                "是否过渡章",
            )
            compact_output["contract_v2"] = {key: contract_v2.get(key) for key in allowed_keys if key in contract_v2}
        return compact_output

    def _append_context_execution_package(self, documents: List[Dict[str, str]], task: Dict[str, Any], step: Dict[str, Any]) -> None:
        task_type = str(task.get("task_type") or "").strip().lower()
        step_name = str(step.get("name") or "").strip().lower()
        if task_type != "write" or step_name not in {"draft", "consistency-review", "continuity-review", "ooc-review", "polish"}:
            return
        context_output = (((task.get("artifacts") or {}).get("step_results") or {}).get("context") or {}).get("structured_output") or {}
        if not isinstance(context_output, dict) or not context_output:
            return
        draft_prompt = str(context_output.get("draft_prompt") or "").strip()
        compact_payload = dict(context_output)
        if draft_prompt:
            compact_payload["draft_prompt"] = "[see attached draft prompt text]"
            documents.append(
                {
                    "path": ".webnovel/context/current-draft-prompt.txt",
                    "content": draft_prompt[:12000],
                }
            )
        documents.append(
            {
                "path": ".webnovel/context/current-context-package.json",
                "content": json.dumps(compact_payload, ensure_ascii=False, indent=2)[:12000],
            }
        )
        chapter = int(((task.get("request") or {}).get("chapter") or 0))
        if chapter > 0:
            self._append_snapshot(
                documents,
                self._director_brief_path(chapter),
                ".webnovel/director/current-director-brief.json",
                12000,
            )

    def _append_snapshot(self, documents: List[Dict[str, str]], path: Path, label: str, max_chars: Optional[int]) -> None:
        if not path.is_file():
            return
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return
        if max_chars is not None:
            content = content[:max_chars]
        documents.append({"path": label, "content": content})

    def _append_context_contract_snapshot(self, documents: List[Dict[str, str]], chapter: int, max_chars: int = 12000) -> None:
        try:
            from scripts.extract_chapter_context import build_chapter_context_payload

            payload = build_chapter_context_payload(self.project_root, chapter)
        except Exception as exc:
            logger.warning("Failed to build chapter context payload for chapter %s: %s", chapter, exc, exc_info=True)
            return
        documents.append(
            {
                "path": f".webnovel/context/ch{chapter:04d}.context.json",
                "content": json.dumps(payload, ensure_ascii=False, indent=2)[:max_chars],
            }
        )

    def _append_setting_snapshots(self, documents: List[Dict[str, str]], max_files: int = 8, max_chars: int = 6000) -> None:
        settings_dir = self.project_root / SETTINGS_DIR_NAME
        if not settings_dir.is_dir():
            return
        count = 0
        for candidate in sorted(settings_dir.rglob("*.md")):
            try:
                label = str(candidate.relative_to(self.project_root)).replace("\\", "/")
            except ValueError:
                label = candidate.name
            self._append_snapshot(documents, candidate, label, max_chars)
            count += 1
            if count >= max_files:
                break

    def _append_glob_snapshot(self, documents: List[Dict[str, str]], base_dir: Path, patterns: List[str], max_chars: Optional[int]) -> None:
        if not base_dir.is_dir():
            return
        for pattern in patterns:
            for candidate in sorted(base_dir.rglob(pattern)):
                label = str(candidate.relative_to(self.project_root)).replace("\\", "/")
                self._append_snapshot(documents, candidate, label, max_chars)
                return

    def _append_chapter_context(
        self,
        documents: List[Dict[str, str]],
        chapter: int,
        *,
        body_max_chars: Optional[int],
        summary_max_chars: Optional[int],
    ) -> None:
        padded = f"{chapter:04d}"
        body_dir = self.project_root / BODY_DIR_NAME
        if body_dir.is_dir():
            seen_paths: set[str] = set()
            preferred_paths = [
                self._resolve_project_path(self._default_chapter_file(chapter)),
                body_dir / f"第{padded}章.md",
            ]
            for candidate in preferred_paths:
                if candidate.is_file():
                    label = self._relative_project_path(candidate)
                    if label not in seen_paths:
                        self._append_snapshot(documents, candidate, label, body_max_chars)
                        seen_paths.add(label)
                        break
            if not seen_paths:
                for pattern in [f"*{padded}*.md", f"*{chapter}*.md"]:
                    for candidate in sorted(body_dir.rglob(pattern)):
                        if not candidate.is_file():
                            continue
                        label = self._relative_project_path(candidate)
                        if label in seen_paths:
                            continue
                        self._append_snapshot(documents, candidate, label, body_max_chars)
                        seen_paths.add(label)
                        break
                    if seen_paths:
                        break
        self._append_snapshot(
            documents,
            self.project_root / ".webnovel" / "summaries" / f"ch{padded}.md",
            f".webnovel/summaries/ch{padded}.md",
            summary_max_chars,
        )

    async def _apply_step_side_effects(self, task_id: str, step: Dict[str, Any], payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
        task = self.store.get_task(task_id)
        if task is None:
            return {"code": "TASK_NOT_FOUND", "message": f"未找到任务：{task_id}"}
        step_name = step.get("name", "unknown")
        try:
            if task.get("task_type") == "write":
                if step_name == "context":
                    self._sync_context_story_contract(task_id, task, payload)
                elif step_name == "data-sync":
                    await self._apply_write_data_sync(task_id, task, payload)
            elif task.get("task_type") == "plan" and step_name == "plan":
                await self._apply_plan_writeback(task_id, task, payload)
        except WritebackConsistencyError as exc:
            error_msg = f"步骤 {step_name} 写回一致性校验失败：{exc}"
            logger.error("Task %s step %s writeback consistency failed: %s", task_id, step_name, exc, exc_info=True)
            return {"code": "WRITEBACK_CONSISTENCY_ERROR", "message": error_msg}
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
        raise RuntimeError("旧的 polished chapter 直写入口已禁用，请统一走 data-sync 写回。")

    def _load_recent_director_briefs(self, chapter: int, window: int = 3) -> List[Dict[str, Any]]:
        briefs: List[Dict[str, Any]] = []
        for prev_chapter in range(max(1, chapter - window), chapter):
            brief = self._load_director_brief(prev_chapter)
            if brief:
                briefs.append(brief)
        return briefs

    def _load_recent_director_alignments(self, chapter: int, window: int = 3) -> List[Dict[str, Any]]:
        history: List[Dict[str, Any]] = []
        tasks = self.store.list_tasks(limit=50)
        for task in reversed(tasks):
            if str(task.get("task_type") or "").strip().lower() != "write":
                continue
            request = task.get("request") or {}
            task_chapter = int(request.get("chapter") or 0)
            if task_chapter <= 0 or task_chapter >= chapter or task_chapter < max(1, chapter - window):
                continue
            alignment = ((task.get("artifacts") or {}).get("writeback") or {}).get("director_alignment") or {}
            if isinstance(alignment, dict) and alignment:
                history.append({"chapter": task_chapter, "director_alignment": alignment})
        return history[-window:]

    def _load_recent_story_alignments(self, chapter: int, window: int = 3) -> List[Dict[str, Any]]:
        history: List[Dict[str, Any]] = []
        tasks = self.store.list_tasks(limit=50)
        for task in reversed(tasks):
            if str(task.get("task_type") or "").strip().lower() != "write":
                continue
            request = task.get("request") or {}
            task_chapter = int(request.get("chapter") or 0)
            if task_chapter <= 0 or task_chapter >= chapter or task_chapter < max(1, chapter - window):
                continue
            alignment = ((task.get("artifacts") or {}).get("writeback") or {}).get("story_alignment") or {}
            if isinstance(alignment, dict) and alignment:
                history.append({"chapter": task_chapter, "story_alignment": alignment})
        return history[-window:]

    def _get_story_plan_slot(self, story_plan: Dict[str, Any], chapter: int) -> Dict[str, Any]:
        for item in (story_plan.get("chapters") or []):
            if int((item or {}).get("chapter") or 0) == chapter:
                return item
        return self._normalize_story_plan_slot({}, chapter=chapter)

    def _build_story_plan(self, task: Dict[str, Any]) -> Dict[str, Any]:
        request = task.get("request") or {}
        chapter = int(request.get("chapter") or 0)
        fallback = self._build_fallback_story_plan(chapter)
        if chapter <= 0:
            return fallback

        try:
            from scripts.extract_chapter_context import build_chapter_context_payload

            context_payload = build_chapter_context_payload(self.project_root, chapter)
        except Exception as exc:
            logger.warning("Failed to build story director context for chapter %s: %s", chapter, exc, exc_info=True)
            return fallback

        planning_horizon = 4
        narrative_state = context_payload.get("narrative_state") or {}
        active_foreshadowing = [item for item in (narrative_state.get("active_foreshadowing") or []) if isinstance(item, dict)]
        knowledge_conflicts = [item for item in (narrative_state.get("knowledge_conflicts") or []) if isinstance(item, dict)]
        reader_signal = context_payload.get("reader_signal") or {}
        review_trend = reader_signal.get("review_trend") or {}
        outline = str(context_payload.get("outline") or "").strip()
        previous_summaries = [str(item).strip() for item in (context_payload.get("previous_summaries") or []) if str(item).strip()]
        recent_briefs = self._load_recent_director_briefs(chapter)
        recent_alignments = self._load_recent_director_alignments(chapter)

        priority_threads = self._normalize_director_text_list(
            [item.get("name") for item in active_foreshadowing]
            + [item.get("topic") for item in knowledge_conflicts]
            + [thread.split(":", 1)[-1] for row in recent_alignments for thread in ((row.get("director_alignment") or {}).get("missed") or [])]
            + [thread for brief in recent_briefs for thread in (brief.get("must_advance_threads") or [])],
            limit=6,
        )
        if not priority_threads and outline:
            priority_threads = ["推进当前卷主线", "保持章末钩子连续驱动"]

        payoff_schedule: List[Dict[str, Any]] = []
        defer_schedule: List[Dict[str, Any]] = []
        for item in active_foreshadowing:
            name = str(item.get("name") or "").strip()
            payoff_chapter = int(item.get("planned_payoff_chapter") or 0)
            if not name or payoff_chapter <= 0:
                continue
            if payoff_chapter <= chapter + planning_horizon - 1:
                payoff_schedule.append(
                    {
                        "thread": name,
                        "target_chapter": max(chapter, payoff_chapter),
                        "mode": "major" if payoff_chapter <= chapter + 1 else "partial",
                    }
                )
            else:
                defer_schedule.append(
                    {
                        "thread": name,
                        "not_before_chapter": payoff_chapter,
                        "reason": "当前滚动窗口内优先保证主冲突推进，不提前清空长期承诺。",
                    }
                )

        risk_flags = self._normalize_director_text_list(
            [flag for flag in (reader_signal.get("low_score_ranges") or []) if isinstance(flag, dict)]
            and ["最近若干章存在低分区间，需要避免继续空转铺垫。"]
            or [],
            limit=5,
        )
        overall_avg = review_trend.get("overall_avg")
        if isinstance(overall_avg, (int, float)) and float(overall_avg) < 75:
            risk_flags.append("近期审查均分偏低，当前窗口需优先保证动作推进和兑现密度。")
        if not payoff_schedule:
            risk_flags.append("当前窗口内缺少明确兑现目标，需用关系推进或压力升级补足驱动力。")
        risk_flags = self._normalize_director_text_list(risk_flags, limit=5)

        chapter_slots: List[Dict[str, Any]] = []
        for offset in range(planning_horizon):
            target_chapter = chapter + offset
            slot_payoffs = [
                str(item.get("thread") or "").strip()
                for item in payoff_schedule
                if int(item.get("target_chapter") or 0) == target_chapter and str(item.get("thread") or "").strip()
            ]
            slot_threads = priority_threads[offset : offset + 2] or priority_threads[:2] or ["推进当前主线"]
            role = "pressure-escalation"
            if offset == 0:
                role = "current-execution"
            elif slot_payoffs:
                role = "payoff-push"
            elif offset == 1:
                role = "transition"
            chapter_slots.append(
                {
                    "chapter": target_chapter,
                    "role": role,
                    "chapter_goal": (
                        f"第{target_chapter}章优先推进“{slot_threads[0]}”并抬升下一步行动压力。"
                        if not slot_payoffs
                        else f"第{target_chapter}章围绕“{slot_payoffs[0]}”给出阶段性兑现，同时保留更高一层压力。"
                    ),
                    "must_advance_threads": slot_threads,
                    "optional_payoffs": slot_payoffs[:2],
                    "forbidden_resolutions": [
                        f"不要在第{target_chapter}章彻底解决 {slot_threads[0]}"
                    ] if slot_threads else ["不要过早清空长期冲突"],
                    "ending_hook_target": (
                        "章末把行动压力切到下一章的更高风险场景。"
                        if offset < planning_horizon - 1
                        else "章末留下下一轮滚动规划所需的新任务或更高代价。"
                    ),
                }
            )

        transition_notes = []
        if previous_summaries:
            transition_notes.append("先承接最近章节遗留压力，再完成从当前冲突到下一层冲突的转场。")
        if payoff_schedule:
            transition_notes.append(f"优先把 {payoff_schedule[0]['thread']} 接到可执行行动上，而不是只做解释性推进。")
        if not transition_notes:
            transition_notes.append("当前窗口以主线推进为先，避免多章停留在说明和准备。")

        rationale = "当前 story plan 根据 active foreshadowing、knowledge conflicts、最近导演执行结果生成，用于稳定未来几章的推进顺序。"
        if outline:
            rationale += f" 本轮仍以当前大纲切片为硬约束。"

        plan = {
            "anchor_chapter": chapter,
            "planning_horizon": planning_horizon,
            "chapters": chapter_slots,
            "priority_threads": priority_threads,
            "payoff_schedule": payoff_schedule,
            "defer_schedule": defer_schedule,
            "risk_flags": risk_flags,
            "transition_notes": transition_notes,
            "rationale": rationale,
        }
        return self._normalize_story_plan(plan, chapter=chapter)

    def _build_story_refresh_assessment(
        self,
        story_plan: Dict[str, Any],
        story_alignment: Dict[str, List[str]],
        *,
        chapter: int,
    ) -> Dict[str, Any]:
        recent_history = self._load_recent_story_alignments(chapter, window=3)
        current_missed = self._normalize_director_text_list((story_alignment or {}).get("missed"), limit=20)
        current_satisfied = self._normalize_director_text_list((story_alignment or {}).get("satisfied"), limit=20)
        current_deferred = self._normalize_director_text_list((story_alignment or {}).get("deferred"), limit=20)

        consecutive_missed = 1 if current_missed else 0
        for row in reversed(recent_history):
            previous_missed = self._normalize_director_text_list(((row.get("story_alignment") or {}).get("missed") or []), limit=20)
            if not previous_missed:
                break
            consecutive_missed += 1

        reasons: List[str] = []
        reason_codes: List[str] = []
        if len(current_missed) >= 2:
            reasons.append("当前章节有多个多章目标未命中，滚动规划已明显偏离执行结果。")
            reason_codes.append("multiple_missed_targets")
        if consecutive_missed >= 2:
            reasons.append(f"连续 {consecutive_missed} 章出现 story alignment missed，建议重新规划未来章节顺序。")
            reason_codes.append("consecutive_missed_chapters")
        if current_missed and len(current_missed) > len(current_satisfied):
            reasons.append("当前章节未满足的多章目标多于已满足目标，后续排期可信度下降。")
            reason_codes.append("missed_outweighs_satisfied")

        should_refresh = bool(reasons)
        assessment = {
            "should_refresh": should_refresh,
            "recommended_resume_from": "story-director" if should_refresh else None,
            "reason_codes": self._normalize_director_text_list(reason_codes, limit=6),
            "reasons": self._normalize_director_text_list(reasons, limit=6),
            "consecutive_missed_chapters": consecutive_missed,
            "current_missed_count": len(current_missed),
            "current_satisfied_count": len(current_satisfied),
            "current_deferred_count": len(current_deferred),
            "anchor_chapter": int((story_plan or {}).get("anchor_chapter") or chapter),
            "planning_horizon": int((story_plan or {}).get("planning_horizon") or 0),
        }
        if should_refresh:
            assessment["suggested_action"] = "建议从 story-director 重新生成滚动规划，再继续后续章节。"
        else:
            assessment["suggested_action"] = "当前滚动规划仍可继续使用。"
        return assessment

    def _build_chapter_director_brief(self, task: Dict[str, Any]) -> Dict[str, Any]:
        request = task.get("request") or {}
        chapter = int(request.get("chapter") or 0)
        fallback = self._build_fallback_director_brief(chapter)
        if chapter <= 0:
            return fallback

        try:
            from scripts.extract_chapter_context import build_chapter_context_payload

            context_payload = build_chapter_context_payload(self.project_root, chapter)
        except Exception as exc:
            logger.warning("Failed to build chapter director context for chapter %s: %s", chapter, exc, exc_info=True)
            return fallback

        narrative_state = context_payload.get("narrative_state") or {}
        active_foreshadowing = narrative_state.get("active_foreshadowing") or []
        recent_timeline_events = narrative_state.get("recent_timeline_events") or []
        core_character_arcs = narrative_state.get("core_character_arcs") or []
        knowledge_conflicts = narrative_state.get("knowledge_conflicts") or []
        writing_guidance = context_payload.get("writing_guidance") or {}
        genre_profile = context_payload.get("genre_profile") or {}
        outline = str(context_payload.get("outline") or "").strip()
        previous_summaries = [str(item).strip() for item in (context_payload.get("previous_summaries") or []) if str(item).strip()]
        story_plan = self._get_task_story_plan(task, chapter)
        story_slot = self._get_story_plan_slot(story_plan, chapter)

        must_advance_threads = self._normalize_director_text_list((story_slot.get("must_advance_threads") or []), limit=4)
        must_advance_threads.extend(
            [
            str(item.get("name") or "").strip()
            for item in active_foreshadowing[:3]
            if str(item.get("name") or "").strip()
            ]
        )
        must_advance_threads = self._normalize_director_text_list(must_advance_threads, limit=4)
        if not must_advance_threads:
            must_advance_threads = [
                str(item.get("topic") or "").strip()
                for item in knowledge_conflicts[:2]
                if str(item.get("topic") or "").strip()
            ]
        if not must_advance_threads and outline:
            must_advance_threads = ["推进本章主线目标"]

        payoff_targets = self._normalize_director_text_list(story_slot.get("optional_payoffs"), limit=3)
        payoff_targets.extend(
            [
            str(item.get("name") or "").strip()
            for item in active_foreshadowing
            if str(item.get("name") or "").strip()
            and int(item.get("planned_payoff_chapter") or 0) > 0
            and int(item.get("planned_payoff_chapter") or 0) <= chapter + 1
            ][:2]
        )
        payoff_targets = self._normalize_director_text_list(payoff_targets, limit=3)

        setup_targets = [
            str(item.get("name") or "").strip()
            for item in active_foreshadowing
            if str(item.get("name") or "").strip() and str(item.get("name") or "").strip() not in payoff_targets
        ][:2]
        if not setup_targets:
            setup_targets = [
                f"为“{str(item.get('topic') or '').strip()}”补一层可回收线索"
                for item in knowledge_conflicts[:2]
                if str(item.get("topic") or "").strip()
            ]

        must_use_entities = self._derive_director_entities(core_character_arcs, recent_timeline_events)
        relationship_moves = self._derive_director_relationship_moves(core_character_arcs)
        knowledge_reveals = [
            str(item.get("topic") or "").strip()
            for item in knowledge_conflicts[:3]
            if str(item.get("topic") or "").strip()
        ]

        forbidden_resolutions = self._normalize_director_text_list(story_slot.get("forbidden_resolutions"), limit=4)
        forbidden_resolutions.extend(
            [
            f"不要在本章彻底回收 {name}"
            for name in must_advance_threads
            if name and name not in payoff_targets
            ][:3]
        )
        forbidden_resolutions = self._normalize_director_text_list(forbidden_resolutions, limit=4)
        if not forbidden_resolutions and active_foreshadowing:
            forbidden_resolutions = [
                f"不要一次性解释完 {str(active_foreshadowing[0].get('name') or '').strip()}"
            ]

        chapter_goal = str(story_slot.get("chapter_goal") or "").strip() or self._build_director_goal(
            chapter=chapter,
            payoff_targets=payoff_targets,
            setup_targets=setup_targets,
            knowledge_reveals=knowledge_reveals,
            outline=outline,
        )
        primary_conflict = self._build_director_primary_conflict(core_character_arcs, knowledge_conflicts, outline)
        ending_hook_target = str(story_slot.get("ending_hook_target") or "").strip() or self._build_director_hook_target(
            payoff_targets,
            setup_targets,
            knowledge_reveals,
            must_advance_threads,
        )
        tempo = self._build_director_tempo(writing_guidance, genre_profile)
        review_focus = self._build_director_review_focus(payoff_targets, must_use_entities, knowledge_reveals, forbidden_resolutions)
        rationale = (
            f"本章 director brief 服从 story_plan 第{chapter}章槽位：{story_slot.get('role') or 'progression'}。"
            f" {self._build_director_rationale(chapter, previous_summaries, must_advance_threads, knowledge_reveals)}"
        )

        brief = {
            "chapter": chapter,
            "chapter_goal": chapter_goal,
            "primary_conflict": primary_conflict,
            "must_advance_threads": must_advance_threads,
            "payoff_targets": payoff_targets,
            "setup_targets": setup_targets,
            "must_use_entities": must_use_entities,
            "relationship_moves": relationship_moves,
            "knowledge_reveals": knowledge_reveals,
            "forbidden_resolutions": forbidden_resolutions,
            "ending_hook_target": ending_hook_target,
            "tempo": tempo,
            "review_focus": review_focus,
            "rationale": rationale,
        }
        return self._normalize_director_brief(brief, chapter=chapter)

    def _build_fallback_director_brief(self, chapter: int) -> Dict[str, Any]:
        brief = {
            "chapter": chapter,
            "chapter_goal": "推进当前章节的核心冲突，并在章末留下明确的下一步压力。",
            "primary_conflict": "主角必须在有限信息下先行动，再承担行动代价。",
            "must_advance_threads": ["推进本章主冲突"],
            "payoff_targets": [],
            "setup_targets": ["补一条可回收的新线索"],
            "must_use_entities": [],
            "relationship_moves": [],
            "knowledge_reveals": [],
            "forbidden_resolutions": ["不要一次性解释完所有疑点"],
            "ending_hook_target": "章末留下下一步行动目标或更高代价。",
            "tempo": "中速推进，后半章抬升压力。",
            "review_focus": ["检查本章目标是否清晰推进", "检查章末钩子是否形成下一步驱动力"],
            "rationale": "当前缺少足够稳定的导演输入，使用最小保底 brief 保持写作链路继续运行。",
        }
        return self._normalize_director_brief(brief, chapter=chapter)

    def _normalize_director_brief(self, brief: Dict[str, Any], *, chapter: int) -> Dict[str, Any]:
        normalized = {
            "chapter": int(brief.get("chapter") or chapter),
            "chapter_goal": str(brief.get("chapter_goal") or "").strip() or "推进当前章节主冲突。",
            "primary_conflict": str(brief.get("primary_conflict") or "").strip() or "主角在信息不足下推进目标并承担代价。",
            "must_advance_threads": self._normalize_director_text_list(brief.get("must_advance_threads")),
            "payoff_targets": self._normalize_director_text_list(brief.get("payoff_targets")),
            "setup_targets": self._normalize_director_text_list(brief.get("setup_targets")),
            "must_use_entities": self._normalize_director_text_list(brief.get("must_use_entities")),
            "relationship_moves": self._normalize_director_text_list(brief.get("relationship_moves")),
            "knowledge_reveals": self._normalize_director_text_list(brief.get("knowledge_reveals")),
            "forbidden_resolutions": self._normalize_director_text_list(brief.get("forbidden_resolutions")),
            "ending_hook_target": str(brief.get("ending_hook_target") or "").strip() or "章末留下明确的下一步压力。",
            "tempo": str(brief.get("tempo") or "").strip() or "中速推进，章末抬升压力。",
            "review_focus": self._normalize_director_text_list(brief.get("review_focus")),
            "rationale": str(brief.get("rationale") or "").strip() or "根据当前章节上下文生成的执行简报。",
        }
        if not normalized["must_advance_threads"]:
            normalized["must_advance_threads"] = ["推进本章主冲突"]
        if not normalized["setup_targets"]:
            normalized["setup_targets"] = ["补一条可回收的新线索"]
        if not normalized["review_focus"]:
            normalized["review_focus"] = ["检查本章是否完成 director brief 的核心目标"]
        return normalized

    def _normalize_director_text_list(self, value: Any, limit: int = 5) -> List[str]:
        items: List[str] = []
        if isinstance(value, (list, tuple)):
            candidates = value
        elif value is None:
            candidates = []
        else:
            candidates = [value]
        seen: set[str] = set()
        for item in candidates:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            items.append(text)
            if len(items) >= limit:
                break
        return items

    def _derive_director_entities(self, core_character_arcs: List[Dict[str, Any]], recent_timeline_events: List[Dict[str, Any]]) -> List[str]:
        entities: List[str] = []
        for item in core_character_arcs:
            entity_id = str(item.get("entity_id") or "").strip()
            if entity_id:
                entities.append(self._resolve_director_entity_label(entity_id))
        for item in recent_timeline_events:
            for participant in item.get("participants") or []:
                participant_id = str(participant or "").strip()
                if participant_id:
                    entities.append(self._resolve_director_entity_label(participant_id))
        return self._normalize_director_text_list(entities, limit=4)

    def _derive_director_relationship_moves(self, core_character_arcs: List[Dict[str, Any]]) -> List[str]:
        moves: List[str] = []
        for item in core_character_arcs:
            source = self._resolve_director_entity_label(str(item.get("entity_id") or "").strip())
            relation_state = item.get("relationship_state") or item.get("relationship_state_json") or {}
            if not isinstance(relation_state, dict):
                continue
            for target_id, state in relation_state.items():
                target = self._resolve_director_entity_label(str(target_id or "").strip())
                state_text = str(state or "").strip()
                if source and target and state_text:
                    moves.append(f"{source} 与 {target} 的关系推进到：{state_text}")
        return self._normalize_director_text_list(moves, limit=4)

    def _resolve_director_entity_label(self, entity_id: str) -> str:
        entity_id = str(entity_id or "").strip()
        if not entity_id:
            return ""
        record = self.index_manager.get_entity(entity_id) or {}
        return str(record.get("canonical_name") or entity_id).strip()

    def _build_director_goal(
        self,
        *,
        chapter: int,
        payoff_targets: List[str],
        setup_targets: List[str],
        knowledge_reveals: List[str],
        outline: str,
    ) -> str:
        if payoff_targets:
            return f"第{chapter}章优先推进并尽量兑现：{payoff_targets[0]}，同时保留后续更大压力。"
        if knowledge_reveals:
            return f"第{chapter}章围绕“{knowledge_reveals[0]}”推进真相层级，并让角色判断产生代价。"
        if setup_targets:
            return f"第{chapter}章先把“{setup_targets[0]}”种稳，为后续回收建立清晰抓手。"
        outline_excerpt = outline[:120].strip()
        if outline_excerpt:
            return f"第{chapter}章应落地当前大纲推进点：{outline_excerpt}"
        return f"第{chapter}章推进当前主冲突，并形成明确章末驱动力。"

    def _build_director_primary_conflict(
        self,
        core_character_arcs: List[Dict[str, Any]],
        knowledge_conflicts: List[Dict[str, Any]],
        outline: str,
    ) -> str:
        if core_character_arcs:
            lead = core_character_arcs[0]
            desire = str(lead.get("desire") or "").strip()
            fear = str(lead.get("fear") or "").strip()
            if desire and fear:
                return f"{self._resolve_director_entity_label(str(lead.get('entity_id') or ''))}想要{desire}，但又害怕{fear}。"
        if knowledge_conflicts:
            topic = str(knowledge_conflicts[0].get("topic") or "").strip()
            if topic:
                return f"围绕“{topic}”的认知分歧必须升级成可行动的冲突。"
        outline_excerpt = outline[:120].strip()
        if outline_excerpt:
            return f"本章主冲突必须服务于当前大纲推进点：{outline_excerpt}"
        return "主角必须在信息不足与现实代价之间做出更危险的选择。"

    def _build_director_hook_target(
        self,
        payoff_targets: List[str],
        setup_targets: List[str],
        knowledge_reveals: List[str],
        must_advance_threads: List[str],
    ) -> str:
        if payoff_targets:
            return f"围绕 {payoff_targets[0]} 的阶段性兑现，章末抛出更高一层代价或新疑点。"
        if knowledge_reveals:
            return f"围绕 {knowledge_reveals[0]} 给出一半答案，再留下更危险的下一步。"
        if setup_targets:
            return f"让 {setup_targets[0]} 在章末产生立即可执行的后续目标。"
        if must_advance_threads:
            return f"让 {must_advance_threads[0]} 在章末形成更紧迫的行动压力。"
        return "章末留下立即可执行的下一步目标。"

    def _build_director_tempo(self, writing_guidance: Dict[str, Any], genre_profile: Dict[str, Any]) -> str:
        methodology = writing_guidance.get("methodology") or {}
        chapter_stage = str(methodology.get("chapter_stage") or "").strip()
        genre = str(genre_profile.get("genre") or "").strip()
        if chapter_stage:
            return f"{chapter_stage}阶段节奏：中速起步，后半章明显抬升压力。"
        if genre:
            return f"{genre}向节奏：尽快进入冲突，中后段加速，章末留钩。"
        return "中速推进，关键信息尽量绑定行动代价，章末抬升压力。"

    def _build_director_review_focus(
        self,
        payoff_targets: List[str],
        must_use_entities: List[str],
        knowledge_reveals: List[str],
        forbidden_resolutions: List[str],
    ) -> List[str]:
        focus: List[str] = []
        if payoff_targets:
            focus.append(f"检查是否真实推进或兑现 {payoff_targets[0]}")
        if must_use_entities:
            focus.append(f"检查 {must_use_entities[0]} 是否承担了本章关键动作")
        if knowledge_reveals:
            focus.append(f"检查 {knowledge_reveals[0]} 是否通过行动而不是解释推进")
        if forbidden_resolutions:
            focus.append(f"检查是否违反：{forbidden_resolutions[0]}")
        if not focus:
            focus.append("检查本章目标、冲突、章末钩子是否首尾一致")
        return self._normalize_director_text_list(focus, limit=4)

    def _build_director_rationale(
        self,
        chapter: int,
        previous_summaries: List[str],
        must_advance_threads: List[str],
        knowledge_reveals: List[str],
    ) -> str:
        summary_hint = previous_summaries[-1][:80].strip() if previous_summaries else ""
        thread_hint = must_advance_threads[0] if must_advance_threads else "本章主冲突"
        if knowledge_reveals:
            return f"第{chapter}章需要延续上一章积累的压力，并把“{thread_hint}”与“{knowledge_reveals[0]}”绑定推进。{summary_hint}"
        return f"第{chapter}章需要延续上一章压力，优先推进“{thread_hint}”，避免空转铺垫。{summary_hint}"

    def _story_plan_path(self, anchor_chapter: int) -> Path:
        return self.project_root / STORY_DIRECTOR_DIR_NAME / f"plan-ch{anchor_chapter:04d}.json"

    def _write_story_plan(self, anchor_chapter: int, plan: Dict[str, Any]) -> Path:
        path = self._story_plan_path(anchor_chapter)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _load_story_plan(self, chapter: int) -> Dict[str, Any]:
        story_dir = self.project_root / STORY_DIRECTOR_DIR_NAME
        return load_story_plan_for_chapter(story_dir, chapter)

    def _normalize_story_plan_slot(self, slot: Dict[str, Any], *, chapter: int) -> Dict[str, Any]:
        normalized = {
            "chapter": int(slot.get("chapter") or chapter),
            "role": str(slot.get("role") or "").strip() or "progression",
            "chapter_goal": str(slot.get("chapter_goal") or "").strip() or "推进当前阶段主冲突并抬升下一步压力。",
            "must_advance_threads": self._normalize_director_text_list(slot.get("must_advance_threads")),
            "optional_payoffs": self._normalize_director_text_list(slot.get("optional_payoffs")),
            "forbidden_resolutions": self._normalize_director_text_list(slot.get("forbidden_resolutions")),
            "ending_hook_target": str(slot.get("ending_hook_target") or "").strip() or "章末留下下一步行动目标。",
        }
        if not normalized["must_advance_threads"]:
            normalized["must_advance_threads"] = ["推进当前主线"]
        return normalized

    def _build_fallback_story_plan(self, chapter: int) -> Dict[str, Any]:
        anchor = max(1, chapter)
        plan = {
            "anchor_chapter": anchor,
            "planning_horizon": 4,
            "priority_threads": ["推进当前主线", "维持章末钩子连续驱动"],
            "payoff_schedule": [],
            "defer_schedule": [],
            "risk_flags": ["当前缺少稳定的多章规划输入，使用保底滚动计划。"],
            "transition_notes": ["优先保证当前章有明确行动目标，并为后续章节保留升级空间。"],
            "chapters": [
                {
                    "chapter": anchor,
                    "role": "stabilize",
                    "chapter_goal": "推进当前章节主冲突，并在章末抛出下一步行动压力。",
                    "must_advance_threads": ["推进当前主线"],
                    "optional_payoffs": [],
                    "forbidden_resolutions": ["不要一次性解决所有长期悬念"],
                    "ending_hook_target": "章末留下明确的下一步行动目标或更高代价。",
                }
            ],
            "rationale": "当前尚无足够稳定的多章级规划输入，先使用最小 story plan 保持链路可运行。",
        }
        return self._normalize_story_plan(plan, chapter=anchor)

    def _normalize_story_plan(self, plan: Dict[str, Any], *, chapter: int) -> Dict[str, Any]:
        anchor_chapter = int(plan.get("anchor_chapter") or chapter or 1)
        planning_horizon = max(1, min(5, int(plan.get("planning_horizon") or 4)))
        raw_slots = [item for item in (plan.get("chapters") or []) if isinstance(item, dict)]
        slots: List[Dict[str, Any]] = []
        seen_chapters: set[int] = set()
        for item in raw_slots:
            slot = self._normalize_story_plan_slot(item, chapter=int(item.get("chapter") or anchor_chapter))
            slot_chapter = int(slot.get("chapter") or 0)
            if slot_chapter <= 0 or slot_chapter in seen_chapters:
                continue
            seen_chapters.add(slot_chapter)
            slots.append(slot)
            if len(slots) >= planning_horizon:
                break
        if anchor_chapter not in seen_chapters:
            slots.append(
                self._normalize_story_plan_slot(
                    {
                        "chapter": anchor_chapter,
                        "role": "progression",
                        "chapter_goal": "推进当前阶段主冲突并抬升下一步压力。",
                        "must_advance_threads": plan.get("priority_threads") or ["推进当前主线"],
                        "optional_payoffs": [],
                        "forbidden_resolutions": ["不要过早清空长期冲突"],
                        "ending_hook_target": "章末留下明确的下一步行动目标。",
                    },
                    chapter=anchor_chapter,
                )
            )
        slots.sort(key=lambda item: int(item.get("chapter") or 0))
        normalized = {
            "anchor_chapter": anchor_chapter,
            "planning_horizon": planning_horizon,
            "chapters": slots[:planning_horizon],
            "priority_threads": self._normalize_director_text_list(plan.get("priority_threads"), limit=8),
            "payoff_schedule": [item for item in (plan.get("payoff_schedule") or []) if isinstance(item, dict)][:8],
            "defer_schedule": [item for item in (plan.get("defer_schedule") or []) if isinstance(item, dict)][:8],
            "risk_flags": self._normalize_director_text_list(plan.get("risk_flags"), limit=8),
            "transition_notes": self._normalize_director_text_list(plan.get("transition_notes"), limit=8),
            "rationale": str(plan.get("rationale") or "").strip() or "根据当前项目状态生成的多章滚动规划。",
        }
        if not normalized["priority_threads"]:
            normalized["priority_threads"] = ["推进当前主线"]
        return normalized

    def _get_task_story_plan(self, task: Dict[str, Any], chapter: int) -> Dict[str, Any]:
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        plan = ((step_results.get("story-director") or {}).get("structured_output") or {})
        if isinstance(plan, dict) and plan:
            return self._normalize_story_plan(plan, chapter=chapter)
        stored = self._load_story_plan(chapter)
        if stored:
            return self._normalize_story_plan(stored, chapter=chapter)
        return self._build_fallback_story_plan(chapter)

    def _director_brief_path(self, chapter: int) -> Path:
        return self.project_root / DIRECTOR_DIR_NAME / f"ch{chapter:04d}.json"

    def _write_director_brief(self, chapter: int, brief: Dict[str, Any]) -> Path:
        path = self._director_brief_path(chapter)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def _load_director_brief(self, chapter: int) -> Dict[str, Any]:
        path = self._director_brief_path(chapter)
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _get_task_director_brief(self, task: Dict[str, Any], chapter: int) -> Dict[str, Any]:
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        brief = ((step_results.get("chapter-director") or {}).get("structured_output") or {})
        if isinstance(brief, dict) and brief:
            return self._normalize_director_brief(brief, chapter=chapter)
        stored = self._load_director_brief(chapter)
        if stored:
            return self._normalize_director_brief(stored, chapter=chapter)
        return self._build_fallback_director_brief(chapter)

    def _sync_context_story_contract(self, task_id: str, task: Dict[str, Any], payload: Dict[str, Any]) -> None:
        chapter = int(((task.get("request") or {}).get("chapter") or 0))
        if chapter <= 0:
            return
        story_plan = self._get_task_story_plan(task, chapter)
        director_brief = self._get_task_director_brief(task, chapter)
        current_result = (((task.get("artifacts") or {}).get("step_results") or {}).get("context") or {})
        merged_output = dict(payload or {})
        merged_output["story_plan"] = story_plan
        merged_output["director_brief"] = director_brief
        updated_result = dict(current_result)
        updated_result["success"] = True
        updated_result["structured_output"] = merged_output
        self.store.save_step_result(task_id, "context", updated_result)
        self.store.append_event(task_id, "info", "Context story contract synced", step_name="context", payload={"chapter": chapter})

    async def _apply_write_data_sync(self, task_id: str, task: Dict[str, Any], payload: Dict[str, Any]) -> None:
        request = task.get("request") or {}
        chapter = int(request.get("chapter") or 0)
        if chapter <= 0:
            raise ValueError("data-sync 缺少有效的 chapter")

        payload, enrichment = self._enrich_data_sync_payload(task, payload)
        if enrichment.get("applied"):
            self.store.append_event(
                task_id,
                "info",
                "Data sync payload enriched",
                step_name="data-sync",
                payload=enrichment,
            )

        artifacts = task.get("artifacts") or {}
        step_results = artifacts.get("step_results") or {}
        draft_output = (step_results.get("draft") or {}).get("structured_output") or {}
        polish_output = (step_results.get("polish") or {}).get("structured_output") or {}
        review_summary = artifacts.get("review_summary") or {}
        story_plan = self._get_task_story_plan(task, chapter)
        director_brief = self._get_task_director_brief(task, chapter)

        requested_chapter_file = self._default_chapter_file(chapter)
        reported_chapter_file = str(
            payload.get("chapter_file")
            or polish_output.get("chapter_file")
            or draft_output.get("chapter_file")
            or requested_chapter_file
        )
        chapter_file = requested_chapter_file
        content = payload.get("content") or polish_output.get("content") or draft_output.get("content") or ""
        if not isinstance(content, str) or not content.strip():
            raise ValueError("data-sync 无法确定章节正文内容")

        word_count = self._canonical_word_count(content)
        reported_word_count = self._parse_reported_word_count(payload, polish_output, draft_output)
        self._validate_writeback_content(content, word_count, reported_word_count)

        requested_summary_file = self._default_summary_file(chapter)
        reported_summary_file = str(payload.get("summary_file") or requested_summary_file)
        summary_file = requested_summary_file
        summary_content = payload.get("summary_content") or payload.get("summary_text")
        if not isinstance(summary_content, str) or not summary_content.strip():
            summary_content = self._build_summary_markdown(chapter, content, review_summary)
        story_alignment = self._build_story_alignment(story_plan, payload, content, chapter)
        story_refresh = self._build_story_refresh_assessment(story_plan, story_alignment, chapter=chapter)
        director_alignment = self._build_director_alignment(director_brief, payload, content)

        state_payload, structured_sync = self._normalize_state_payload(chapter, payload)
        narrative_sync = self._normalize_narrative_payload(chapter, payload)
        snapshot = self._snapshot_writeback_state(
            chapter=chapter,
            chapter_file=chapter_file,
            summary_file=summary_file,
            structured_sync=structured_sync,
            narrative_sync=narrative_sync,
        )

        try:
            chapter_path = self._write_project_text(chapter_file, content)
            summary_path = self._write_project_text(summary_file, summary_content)
            existing_chapter = self.index_manager.get_chapter(chapter) or {}
            previous_word_count = int(existing_chapter.get("word_count") or 0)

            state_manager = StateManager(get_config(project_root=self.project_root))
            state_manager.process_chapter_result(chapter, state_payload)
            state_manager.update_progress(chapter, words=0)
            state_manager._pending_progress_words_delta += word_count - previous_word_count
            state_manager.save_state()
            if structured_sync["world_settings"]:
                self._merge_world_settings(structured_sync["world_settings"])
            if structured_sync["entities"]:
                self._upsert_structured_entities(chapter, structured_sync["entities"])
            if structured_sync["relationships"]:
                self._upsert_structured_relationships(chapter, structured_sync["relationships"])
            self._record_structured_sync_event(task_id, chapter, structured_sync)
            if narrative_sync["summary"]["normalized_entries"]:
                self._write_narrative_graph(narrative_sync)
            self._record_narrative_sync_event(task_id, chapter, narrative_sync)

            chapter_meta = state_payload.get("chapter_meta") or {}
            self.index_manager.add_chapter(
                ChapterMeta(
                    chapter=chapter,
                    title=self._resolve_chapter_title(chapter, content, chapter_meta),
                    location=str(chapter_meta.get("location") or ""),
                    word_count=word_count,
                    characters=self._normalize_characters(chapter_meta.get("characters")),
                    summary=self._extract_summary_excerpt(summary_content),
                    file_path=self._relative_project_path(chapter_path),
                )
            )

            latest_task = self.store.get_task(task_id) or task
            if review_summary:
                self._persist_review_summary(latest_task, review_summary)
                self.store.append_event(
                    task_id,
                    "info",
                    "Review summary persisted",
                    step_name="data-sync",
                    payload={"chapter": chapter},
                )

            warning_payload: Dict[str, Any] = {"chapter": chapter}
            if reported_chapter_file and reported_chapter_file != requested_chapter_file:
                warning_payload["reported_chapter_file"] = reported_chapter_file
                warning_payload["actual_chapter_file"] = requested_chapter_file
            if reported_summary_file and reported_summary_file != requested_summary_file:
                warning_payload["reported_summary_file"] = reported_summary_file
                warning_payload["actual_summary_file"] = requested_summary_file
            if len(warning_payload) > 1:
                self.store.append_event(
                    task_id,
                    "warning",
                    "Write target normalized",
                    step_name="data-sync",
                    payload=warning_payload,
                )
            if story_refresh.get("should_refresh"):
                self.store.append_event(
                    task_id,
                    "warning",
                    "Story plan refresh suggested",
                    step_name="data-sync",
                    payload=story_refresh,
                )

            self._validate_writeback_consistency(
                chapter=chapter,
                chapter_path=chapter_path,
                summary_path=summary_path,
                summary_content=summary_content,
                content=content,
            )
            await self._sync_core_setting_docs(
                task_id=task_id,
                trigger="write",
                chapter=chapter,
                plan_payload=None,
                state_payload=state_payload,
                structured_sync=structured_sync,
            )

            latest_task = self.store.get_task(task_id) or task
            latest_artifacts = dict(latest_task.get("artifacts") or {})
            writeback = dict(latest_artifacts.get("writeback") or {})
            writeback.update(
                {
                    "chapter_file": self._relative_project_path(chapter_path),
                    "summary_file": self._relative_project_path(summary_path),
                    "state_file": ".webnovel/state.json",
                    "word_count": word_count,
                    "index_updated": True,
                    "structured_sync": structured_sync["summary"],
                    "narrative_sync": narrative_sync["summary"],
                    "story_alignment": story_alignment,
                    "story_refresh": story_refresh,
                    "director_alignment": director_alignment,
                }
            )
            latest_artifacts["writeback"] = writeback
            latest_artifacts["story_refresh"] = story_refresh
            self.store.update_task(task_id, artifacts=latest_artifacts)
            self.store.append_event(
                task_id,
                "info",
                "Data sync completed",
                step_name="data-sync",
                payload=writeback,
            )
        except Exception as exc:
            rollback_error = self._rollback_writeback_snapshot(task_id, chapter, snapshot)
            if rollback_error is not None:
                raise WritebackConsistencyError(f"{exc}; rollback_error={rollback_error}") from exc
            raise

    async def _apply_plan_writeback(self, task_id: str, task: Dict[str, Any], payload: Dict[str, Any]) -> None:
        if self._is_plan_payload_blocked(payload):
            return
        request = task.get("request") or {}
        volume = str(request.get("volume") or "1").strip() or "1"
        outline_file = f"{OUTLINE_DIR_NAME}/{self._volume_plan_filename(volume)}"
        outline_content = self._build_volume_plan_markdown(volume, payload)
        outline_path = self._write_project_text(outline_file, outline_content)

        latest_task = self.store.get_task(task_id) or task
        chapters = [item for item in (payload.get("chapters") or []) if isinstance(item, dict)]
        chapters_range = self._infer_plan_chapters_range(chapters)

        def _mutate(state_data: Dict[str, Any]) -> None:
            planning = state_data.setdefault("planning", {})
            volume_plans = planning.setdefault("volume_plans", {})
            volume_plans[volume] = {
                "outline_file": self._relative_project_path(outline_path),
                "updated_at": latest_task.get("updated_at"),
                "summary": self._summarize_volume_plan(payload),
                "chapter_count": len(payload.get("chapters") or []),
            }
            planning["latest_volume"] = volume
            planning["last_blocked"] = None
            progress = state_data.setdefault("progress", {})
            try:
                progress["current_volume"] = max(1, int(volume))
            except ValueError:
                progress.setdefault("current_volume", 1)
            if chapters_range:
                progress["volumes_planned"] = self._upsert_volume_plan_progress(
                    progress.get("volumes_planned"),
                    volume=progress.get("current_volume") or 1,
                    chapters_range=chapters_range,
                )

        self._update_state_data(_mutate)
        await self._sync_core_setting_docs(
            task_id=task_id,
            trigger="plan",
            chapter=None,
            plan_payload=payload,
            state_payload=None,
            structured_sync=None,
        )

        latest_artifacts = dict(latest_task.get("artifacts") or {})
        latest_artifacts["writeback"] = {
            "outline_file": self._relative_project_path(outline_path),
            "state_file": ".webnovel/state.json",
            "volume": volume,
        }
        latest_artifacts["plan_blocked"] = False
        latest_artifacts.pop("blocking_items", None)
        latest_artifacts.pop("next_step", None)
        latest_artifacts.pop("fill_template", None)
        self.store.update_task(task_id, artifacts=latest_artifacts)
        self.store.append_event(
            task_id,
            "info",
            "Plan writeback completed",
            step_name="plan",
            payload=latest_artifacts["writeback"],
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
            f"- 总评分：{review_summary.get('overall_score', 0)}",
            f"- 是否阻断：{'是' if bool(review_summary.get('blocking')) else '否'}",
            f"- 审查器数量：{len(reviewers)}",
            f"- 问题数量：{len(issues)}",
        ]
        if issues:
            lines.extend(["", SUMMARY_SECTION_ISSUES])
            for issue in issues[:5]:
                title = issue.get("title") or issue.get("message") or "未命名问题"
                severity = issue.get("severity") or "medium"
                lines.append(f"- [{self._translate_review_severity(severity)}] {title}")
        return "\n".join(lines).strip() + "\n"

    def _canonical_word_count(self, content: str) -> int:
        return len("".join(content.split()))

    def _parse_reported_word_count(self, *payloads: Dict[str, Any]) -> Optional[int]:
        for payload in payloads:
            candidate = payload.get("word_count")
            if isinstance(candidate, int) and candidate > 0:
                return candidate
            if isinstance(candidate, str) and candidate.isdigit():
                return int(candidate)
        return None

    def _validate_writeback_content(self, content: str, actual_word_count: int, reported_word_count: Optional[int]) -> None:
        if actual_word_count < MIN_WRITEBACK_WORD_COUNT:
            raise ValueError(f"chapter content too short for writeback: {actual_word_count}")
        if reported_word_count is None:
            return
        allowed_drift = max(MAX_WORD_COUNT_DRIFT, int(actual_word_count * MAX_WORD_COUNT_DRIFT_RATIO))
        if abs(reported_word_count - actual_word_count) > allowed_drift:
            raise ValueError(
                f"reported word count drift is too large: reported={reported_word_count}, actual={actual_word_count}"
            )

    def _validate_writeback_consistency(
        self,
        *,
        chapter: int,
        chapter_path: Path,
        summary_path: Path,
        summary_content: str,
        content: str,
    ) -> None:
        expected_body = self._default_chapter_file(chapter)
        actual_body = self._relative_project_path(chapter_path)
        if actual_body != expected_body:
            raise WritebackConsistencyError(f"正文文件路径错误：期望 {expected_body}，实际 {actual_body}")

        expected_summary = self._default_summary_file(chapter)
        actual_summary = self._relative_project_path(summary_path)
        if actual_summary != expected_summary:
            raise WritebackConsistencyError(f"摘要文件路径错误：期望 {expected_summary}，实际 {actual_summary}")

        chapter_record = self.index_manager.get_chapter(chapter)
        if not chapter_record:
            raise WritebackConsistencyError(f"章节索引缺失：chapter={chapter}")
        indexed_path = str(chapter_record.get("file_path") or "").replace("\\", "/")
        if indexed_path != expected_body:
            raise WritebackConsistencyError(f"章节索引 file_path 错误：期望 {expected_body}，实际 {indexed_path or '空'}")

        metrics_records = self.index_manager.get_recent_review_metrics(limit=max(10, chapter + 2))
        has_review_metrics = any(
            int(record.get("start_chapter") or 0) == chapter and int(record.get("end_chapter") or 0) == chapter
            for record in metrics_records
        )
        if not has_review_metrics:
            raise WritebackConsistencyError(f"单章 review_metrics 缺失：chapter={chapter}")

        state_data = self._read_state_data()
        progress = state_data.get("progress") or {}
        current_chapter = int(progress.get("current_chapter") or 0)
        if current_chapter < chapter:
            raise WritebackConsistencyError(f"当前进度未推进到目标章节：current_chapter={current_chapter}, chapter={chapter}")

        chapter_meta = self._get_state_chapter_meta(state_data, chapter)
        if not chapter_meta:
            raise WritebackConsistencyError(f"state.json chapter_meta 缺失：chapter={chapter}")

        if not chapter_path.is_file() or not summary_path.is_file():
            raise WritebackConsistencyError("写回文件未落盘完成")
        if not content.strip() or not summary_content.strip():
            raise WritebackConsistencyError("正文或摘要内容为空")

    def _default_chapter_file(self, chapter: int) -> str:
        volume = self._resolve_volume_for_chapter(chapter)
        return f"{BODY_DIR_NAME}/第{volume}卷/第{chapter:04d}章.md"

    def _default_summary_file(self, chapter: int) -> str:
        return f".webnovel/summaries/ch{chapter:04d}.md"

    def _repair_project_layout(self) -> None:
        try:
            self._migrate_legacy_chapter_files()
        except Exception as exc:
            logger.warning("failed to repair project layout for %s: %s", self.project_root, exc)

    def _migrate_legacy_chapter_files(self) -> None:
        body_dir = self.project_root / BODY_DIR_NAME
        if not body_dir.is_dir():
            return
        legacy_pattern = re.compile(r"^第(\d{4})章\.md$")
        moved_targets: Dict[int, str] = {}
        for candidate in sorted(body_dir.glob("第*.md")):
            if not candidate.is_file():
                continue
            matched = legacy_pattern.match(candidate.name)
            if not matched:
                continue
            chapter = int(matched.group(1))
            target_rel = self._default_chapter_file(chapter)
            target_path = self._resolve_project_path(target_rel)
            if candidate.resolve() == target_path.resolve():
                moved_targets[chapter] = target_rel
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                try:
                    if target_path.read_text(encoding="utf-8") == candidate.read_text(encoding="utf-8"):
                        candidate.unlink()
                        moved_targets[chapter] = target_rel
                except UnicodeDecodeError:
                    continue
                continue
            candidate.replace(target_path)
            moved_targets[chapter] = target_rel

        if not moved_targets:
            return
        with self.index_manager._get_conn() as conn:
            cursor = conn.cursor()
            for chapter, target_rel in moved_targets.items():
                legacy_rel = f"{BODY_DIR_NAME}/第{chapter:04d}章.md"
                cursor.execute(
                    "UPDATE chapters SET file_path = ? WHERE chapter = ? AND REPLACE(file_path, '\\\\', '/') IN (?, ?)",
                    (target_rel, chapter, legacy_rel, target_rel),
                )
            conn.commit()

    def _resolve_volume_for_chapter(self, chapter: int, state_data: Optional[Dict[str, Any]] = None) -> int:
        if chapter <= 0:
            return 1
        data = state_data if state_data is not None else self._read_state_data()
        progress = data.get("progress") or {}
        best_match: Optional[tuple[int, int]] = None
        for item in progress.get("volumes_planned") or []:
            if not isinstance(item, dict):
                continue
            volume = item.get("volume")
            if volume is None:
                continue
            parsed_range = self._parse_chapters_range(item.get("chapters_range"))
            if parsed_range is None:
                continue
            start, end = parsed_range
            if start <= chapter <= end:
                try:
                    candidate = (start, max(1, int(volume)))
                except (TypeError, ValueError):
                    continue
                if best_match is None or candidate[0] > best_match[0] or (
                    candidate[0] == best_match[0] and candidate[1] < best_match[1]
                ):
                    best_match = candidate
        if best_match is not None:
            return best_match[1]

        current_chapter = 0
        try:
            current_chapter = max(0, int(progress.get("current_chapter") or 0))
        except (TypeError, ValueError):
            current_chapter = 0
        if current_chapter > 0 and chapter in {current_chapter, current_chapter + 1}:
            for candidate in (
                progress.get("current_volume"),
                ((data.get("planning") or {}).get("latest_volume")),
            ):
                try:
                    return max(1, int(candidate or 1))
                except (TypeError, ValueError):
                    continue

        for candidate in ((((chapter - 1) // 50) + 1), 1):
            try:
                return max(1, int(candidate or 1))
            except (TypeError, ValueError):
                continue
        return 1

    def _parse_chapters_range(self, raw: Any) -> Optional[tuple[int, int]]:
        text = str(raw or "").strip()
        if not text:
            return None
        matched = re.match(r"^\s*(\d+)\s*[-~～至]\s*(\d+)\s*$", text)
        if matched:
            start, end = int(matched.group(1)), int(matched.group(2))
            if start > 0 and end >= start:
                return start, end
        if text.isdigit():
            value = int(text)
            if value > 0:
                return value, value
        return None

    def _infer_plan_chapters_range(self, chapters: List[Dict[str, Any]]) -> Optional[str]:
        numbers = []
        for item in chapters:
            try:
                chapter = int(item.get("chapter") or 0)
            except (TypeError, ValueError):
                continue
            if chapter > 0:
                numbers.append(chapter)
        if not numbers:
            return None
        return f"{min(numbers)}-{max(numbers)}"

    def _upsert_volume_plan_progress(self, raw_items: Any, *, volume: int, chapters_range: str) -> List[Dict[str, Any]]:
        items = [dict(item) for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
        updated = False
        for item in items:
            try:
                existing_volume = int(item.get("volume") or 0)
            except (TypeError, ValueError):
                existing_volume = 0
            if existing_volume == volume:
                item["chapters_range"] = chapters_range
                updated = True
                break
        if not updated:
            items.append({"volume": volume, "chapters_range": chapters_range})
        items.sort(key=lambda row: int(row.get("volume") or 0))
        return items

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

    def _snapshot_writeback_state(
        self,
        *,
        chapter: int,
        chapter_file: str,
        summary_file: str,
        structured_sync: Dict[str, Any],
        narrative_sync: Dict[str, Any],
    ) -> Dict[str, Any]:
        entity_ids = {
            str(item.get("id") or "").strip()
            for item in (structured_sync.get("entities") or [])
            if str(item.get("id") or "").strip()
        }
        relationship_keys = {
            (
                str(item.get("from_entity") or "").strip(),
                str(item.get("to_entity") or "").strip(),
                str(item.get("type") or "").strip(),
            )
            for item in (structured_sync.get("relationships") or [])
            if str(item.get("from_entity") or "").strip()
            and str(item.get("to_entity") or "").strip()
            and str(item.get("type") or "").strip()
        }
        with self.index_manager._get_conn() as conn:
            cursor = conn.cursor()
            chapter_row = cursor.execute("SELECT * FROM chapters WHERE chapter = ?", (chapter,)).fetchone()
            review_metrics_row = cursor.execute(
                "SELECT * FROM review_metrics WHERE start_chapter = ? AND end_chapter = ?",
                (chapter, chapter),
            ).fetchone()
            entity_rows = [
                dict(row)
                for row in cursor.execute("SELECT * FROM entities").fetchall()
                if row["id"] in entity_ids
                or int(row["first_appearance"] or 0) == chapter
                or int(row["last_appearance"] or 0) == chapter
            ]
            related_entity_ids = set(entity_ids)
            related_entity_ids.update(str(row.get("id") or "").strip() for row in entity_rows if str(row.get("id") or "").strip())
            alias_rows = [
                dict(row)
                for row in cursor.execute("SELECT * FROM aliases").fetchall()
                if row["entity_id"] in related_entity_ids
            ]
            relationship_rows = [
                dict(row)
                for row in cursor.execute("SELECT * FROM relationships").fetchall()
                if int(row["chapter"] or 0) == chapter
                or (str(row["from_entity"] or ""), str(row["to_entity"] or ""), str(row["type"] or "")) in relationship_keys
            ]
        return {
            "chapter": chapter,
            "chapter_file": self._snapshot_project_text(chapter_file),
            "summary_file": self._snapshot_project_text(summary_file),
            "state_file": self._snapshot_project_text(".webnovel/state.json"),
            "chapter_row": dict(chapter_row) if chapter_row else None,
            "review_metrics_row": dict(review_metrics_row) if review_metrics_row else None,
            "entity_rows": entity_rows,
            "alias_rows": alias_rows,
            "relationship_rows": relationship_rows,
            "entity_ids": sorted(related_entity_ids),
            "relationship_keys": [list(item) for item in sorted(relationship_keys)],
            "narrative_snapshot": self._snapshot_narrative_state(chapter, narrative_sync),
        }

    def _snapshot_project_text(self, raw_path: str) -> Dict[str, Any]:
        target = self._resolve_project_path(raw_path)
        exists = target.is_file()
        return {
            "path": raw_path,
            "exists": exists,
            "content": target.read_text(encoding="utf-8") if exists else "",
        }

    def _rollback_writeback_snapshot(
        self,
        task_id: str,
        chapter: int,
        snapshot: Dict[str, Any],
    ) -> Optional[str]:
        self.store.append_event(
            task_id,
            "warning",
            "writeback_rollback_started",
            step_name="data-sync",
            payload={"chapter": chapter},
        )
        try:
            self._restore_writeback_snapshot(snapshot)
        except Exception as exc:
            self.store.append_event(
                task_id,
                "error",
                "writeback_rollback_finished",
                step_name="data-sync",
                payload={"chapter": chapter, "rollback_error": str(exc)},
            )
            return str(exc)
        self.store.append_event(
            task_id,
            "info",
            "writeback_rollback_finished",
            step_name="data-sync",
            payload={"chapter": chapter},
        )
        return None

    def _restore_writeback_snapshot(self, snapshot: Dict[str, Any]) -> None:
        chapter = int(snapshot.get("chapter") or 0)
        entity_ids = {
            str(item)
            for item in (snapshot.get("entity_ids") or [])
            if str(item).strip()
        }
        relationship_keys = {
            tuple(str(part) for part in item)
            for item in (snapshot.get("relationship_keys") or [])
            if isinstance(item, list) and len(item) == 3
        }
        with self.index_manager._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM chapters WHERE chapter = ?", (chapter,))
            cursor.execute("DELETE FROM review_metrics WHERE start_chapter = ? AND end_chapter = ?", (chapter, chapter))
            relationship_rows = cursor.execute("SELECT * FROM relationships").fetchall()
            relationship_ids_to_delete = [
                int(row["id"])
                for row in relationship_rows
                if int(row["chapter"] or 0) == chapter
                or (str(row["from_entity"] or ""), str(row["to_entity"] or ""), str(row["type"] or "")) in relationship_keys
            ]
            if relationship_ids_to_delete:
                placeholders = ",".join("?" for _ in relationship_ids_to_delete)
                cursor.execute(f"DELETE FROM relationships WHERE id IN ({placeholders})", tuple(relationship_ids_to_delete))
            if entity_ids:
                placeholders = ",".join("?" for _ in entity_ids)
                cursor.execute(f"DELETE FROM aliases WHERE entity_id IN ({placeholders})", tuple(sorted(entity_ids)))
                cursor.execute(f"DELETE FROM entities WHERE id IN ({placeholders})", tuple(sorted(entity_ids)))
            for row in snapshot.get("entity_rows") or []:
                entity_ids.add(str(row.get("id") or "").strip())
            if entity_ids:
                placeholders = ",".join("?" for _ in entity_ids)
                cursor.execute(
                    f"DELETE FROM entities WHERE id IN ({placeholders})",
                    tuple(sorted(entity_ids)),
                )
                cursor.execute(
                    f"DELETE FROM aliases WHERE entity_id IN ({placeholders})",
                    tuple(sorted(entity_ids)),
                )
            self._restore_table_row(cursor, "chapters", snapshot.get("chapter_row"))
            self._restore_table_row(cursor, "review_metrics", snapshot.get("review_metrics_row"))
            self._restore_table_rows(cursor, "entities", snapshot.get("entity_rows") or [])
            self._restore_table_rows(cursor, "aliases", snapshot.get("alias_rows") or [])
            self._restore_table_rows(cursor, "relationships", snapshot.get("relationship_rows") or [])
            self._restore_narrative_state(cursor, chapter, snapshot.get("narrative_snapshot") or {})
            conn.commit()
        self._restore_project_text(snapshot.get("chapter_file") or {})
        self._restore_project_text(snapshot.get("summary_file") or {})
        self._restore_project_text(snapshot.get("state_file") or {})

    def _snapshot_narrative_state(self, chapter: int, narrative_sync: Dict[str, Any]) -> Dict[str, Any]:
        foreshadowing_names = {
            str(item.get("name") or "").strip()
            for item in (narrative_sync.get("foreshadowing_items") or [])
            if str(item.get("name") or "").strip()
        }
        timeline_keys = {
            (
                int(item.get("chapter") or chapter),
                int(item.get("scene_index") or 0),
                str(item.get("summary") or "").strip(),
            )
            for item in (narrative_sync.get("timeline_events") or [])
            if str(item.get("summary") or "").strip()
        }
        character_arc_keys = {
            (
                str(item.get("entity_id") or "").strip(),
                int(item.get("chapter") or chapter),
            )
            for item in (narrative_sync.get("character_arcs") or [])
            if str(item.get("entity_id") or "").strip()
        }
        knowledge_state_keys = {
            (
                str(item.get("entity_id") or "").strip(),
                int(item.get("chapter") or chapter),
                str(item.get("topic") or "").strip(),
            )
            for item in (narrative_sync.get("knowledge_states") or [])
            if str(item.get("entity_id") or "").strip() and str(item.get("topic") or "").strip()
        }

        with self.index_manager._get_conn() as conn:
            cursor = conn.cursor()
            snapshot: Dict[str, Any] = {
                "foreshadowing_names": sorted(foreshadowing_names),
                "timeline_keys": [list(item) for item in sorted(timeline_keys)],
                "character_arc_keys": [list(item) for item in sorted(character_arc_keys)],
                "knowledge_state_keys": [list(item) for item in sorted(knowledge_state_keys)],
                "foreshadowing_rows": [],
                "timeline_rows": [],
                "character_arc_rows": [],
                "knowledge_state_rows": [],
            }
            if self._table_exists(cursor, "foreshadowing_items"):
                snapshot["foreshadowing_rows"] = [
                    dict(row)
                    for row in cursor.execute("SELECT * FROM foreshadowing_items").fetchall()
                    if str(row["name"] or "").strip() in foreshadowing_names
                ]
            if self._table_exists(cursor, "timeline_events"):
                snapshot["timeline_rows"] = [
                    dict(row)
                    for row in cursor.execute("SELECT * FROM timeline_events").fetchall()
                    if int(row["chapter"] or 0) == chapter
                    or (
                        int(row["chapter"] or 0),
                        int(row["scene_index"] or 0),
                        str(row["summary"] or "").strip(),
                    )
                    in timeline_keys
                ]
            if self._table_exists(cursor, "character_arcs"):
                snapshot["character_arc_rows"] = [
                    dict(row)
                    for row in cursor.execute("SELECT * FROM character_arcs").fetchall()
                    if int(row["chapter"] or 0) == chapter
                    or (str(row["entity_id"] or "").strip(), int(row["chapter"] or 0)) in character_arc_keys
                ]
            if self._table_exists(cursor, "knowledge_states"):
                snapshot["knowledge_state_rows"] = [
                    dict(row)
                    for row in cursor.execute("SELECT * FROM knowledge_states").fetchall()
                    if int(row["chapter"] or 0) == chapter
                    or (
                        str(row["entity_id"] or "").strip(),
                        int(row["chapter"] or 0),
                        str(row["topic"] or "").strip(),
                    )
                    in knowledge_state_keys
                ]
        return snapshot

    def _restore_narrative_state(self, cursor: sqlite3.Cursor, chapter: int, snapshot: Dict[str, Any]) -> None:
        foreshadowing_names = {
            str(item)
            for item in (snapshot.get("foreshadowing_names") or [])
            if str(item).strip()
        }
        timeline_keys = {
            tuple(item)
            for item in (snapshot.get("timeline_keys") or [])
            if isinstance(item, list) and len(item) == 3
        }
        character_arc_keys = {
            tuple(item)
            for item in (snapshot.get("character_arc_keys") or [])
            if isinstance(item, list) and len(item) == 2
        }
        knowledge_state_keys = {
            tuple(item)
            for item in (snapshot.get("knowledge_state_keys") or [])
            if isinstance(item, list) and len(item) == 3
        }

        if self._table_exists(cursor, "foreshadowing_items"):
            if foreshadowing_names:
                placeholders = ",".join("?" for _ in foreshadowing_names)
                cursor.execute(
                    f"DELETE FROM foreshadowing_items WHERE name IN ({placeholders})",
                    tuple(sorted(foreshadowing_names)),
                )
            self._restore_table_rows(cursor, "foreshadowing_items", snapshot.get("foreshadowing_rows") or [])

        if self._table_exists(cursor, "timeline_events"):
            timeline_rows = cursor.execute("SELECT * FROM timeline_events").fetchall()
            ids_to_delete = [
                int(row["id"])
                for row in timeline_rows
                if int(row["chapter"] or 0) == chapter
                or (
                    int(row["chapter"] or 0),
                    int(row["scene_index"] or 0),
                    str(row["summary"] or "").strip(),
                )
                in timeline_keys
            ]
            if ids_to_delete:
                placeholders = ",".join("?" for _ in ids_to_delete)
                cursor.execute(f"DELETE FROM timeline_events WHERE id IN ({placeholders})", tuple(ids_to_delete))
            self._restore_table_rows(cursor, "timeline_events", snapshot.get("timeline_rows") or [])

        if self._table_exists(cursor, "character_arcs"):
            if character_arc_keys:
                cursor.execute("DELETE FROM character_arcs WHERE chapter = ?", (chapter,))
                for entity_id, arc_chapter in character_arc_keys:
                    cursor.execute(
                        "DELETE FROM character_arcs WHERE entity_id = ? AND chapter = ?",
                        (entity_id, arc_chapter),
                    )
            else:
                cursor.execute("DELETE FROM character_arcs WHERE chapter = ?", (chapter,))
            self._restore_table_rows(cursor, "character_arcs", snapshot.get("character_arc_rows") or [])

        if self._table_exists(cursor, "knowledge_states"):
            if knowledge_state_keys:
                cursor.execute("DELETE FROM knowledge_states WHERE chapter = ?", (chapter,))
                for entity_id, state_chapter, topic in knowledge_state_keys:
                    cursor.execute(
                        "DELETE FROM knowledge_states WHERE entity_id = ? AND chapter = ? AND topic = ?",
                        (entity_id, state_chapter, topic),
                    )
            else:
                cursor.execute("DELETE FROM knowledge_states WHERE chapter = ?", (chapter,))
            self._restore_table_rows(cursor, "knowledge_states", snapshot.get("knowledge_state_rows") or [])

    def _table_exists(self, cursor: sqlite3.Cursor, table: str) -> bool:
        row = cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        return row is not None

    def _restore_table_row(self, cursor: sqlite3.Cursor, table: str, row: Optional[Dict[str, Any]]) -> None:
        if not row:
            return
        self._restore_table_rows(cursor, table, [row])

    def _restore_table_rows(self, cursor: sqlite3.Cursor, table: str, rows: List[Dict[str, Any]]) -> None:
        for row in rows:
            columns = list(row.keys())
            placeholders = ", ".join("?" for _ in columns)
            column_sql = ", ".join(columns)
            values = [row[column] for column in columns]
            cursor.execute(f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})", values)

    def _restore_project_text(self, snapshot: Dict[str, Any]) -> None:
        raw_path = str(snapshot.get("path") or "").strip()
        if not raw_path:
            return
        target = self._resolve_project_path(raw_path)
        if snapshot.get("exists"):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(snapshot.get("content") or ""), encoding="utf-8")
            return
        if target.exists():
            target.unlink()

    def _validate_output(self, step: Dict[str, Any], payload: Dict[str, Any]) -> Optional[Dict[str, str]]:
        required = step.get("required_output_keys", [])
        missing = [key for key in required if key not in payload]
        if str(step.get("name") or "").strip().lower() == "context":
            missing = [key for key in missing if key not in {"director_brief", "story_plan"}]
        if missing:
            return {
                "code": "INVALID_STEP_OUTPUT",
                "message": f"缺少必要字段：{', '.join(missing)}",
                "parse_stage": "missing_required_keys",
                "missing_required_keys": missing,
                "raw_output_present": True,
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

    def _translate_review_severity(self, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        mapping = {
            "critical": "严重",
            "high": "高",
            "medium": "中",
            "low": "低",
        }
        return mapping.get(normalized, str(value or "中"))

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

    def _resolve_issue_chapter(
        self,
        issue: Dict[str, Any],
        *,
        request: Dict[str, Any],
    ) -> int:
        for key in ("chapter", "chapter_number", "target_chapter"):
            try:
                chapter = int(issue.get(key) or 0)
            except (TypeError, ValueError):
                chapter = 0
            if chapter > 0:
                return chapter
        try:
            request_chapter = int(request.get("chapter") or 0)
        except (TypeError, ValueError):
            request_chapter = 0
        if request_chapter > 0:
            return request_chapter
        chapter_range = self._parse_chapter_range(request.get("chapter_range"))
        if chapter_range is not None and chapter_range[0] == chapter_range[1]:
            return chapter_range[0]
        return 0

    def _default_repair_guardrails(self, issue_type: str) -> List[str]:
        return [
            "仅修复当前章节局部连续性问题",
            "不要改写卷纲或跨章主线",
            "不要重塑角色声音",
            "不要引入与现有设定冲突的新规则",
            f"优先解决 {issue_type or '当前问题'}，避免顺手重写无关段落",
        ]

    def _normalize_repair_guardrails(self, raw_value: Any, issue_type: str) -> List[str]:
        items: List[str] = []
        if isinstance(raw_value, list):
            for item in raw_value:
                text = str(item or "").strip()
                if text:
                    items.append(text)
        elif isinstance(raw_value, str):
            text = raw_value.strip()
            if text:
                items.append(text)
        if not items:
            items = self._default_repair_guardrails(issue_type)
        deduped: List[str] = []
        seen = set()
        for item in items:
            if item not in seen:
                seen.add(item)
                deduped.append(item)
        return deduped

    def _build_repair_candidates(self, task: Dict[str, Any], issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        request = task.get("request") or {}
        project_root = str(request.get("project_root") or self.project_root)
        mode = str(request.get("mode") or "standard")
        candidates: List[Dict[str, Any]] = []
        seen: set[tuple[int, str, str]] = set()

        for index, issue in enumerate(issues):
            issue_type = str(issue.get("type") or issue.get("issue_type") or "").strip().upper()
            title = str(issue.get("title") or issue.get("summary") or issue.get("message") or issue_type or "未命名问题").strip()
            chapter = self._resolve_issue_chapter(issue, request=request)
            dedupe_key = (chapter, issue_type, title)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rewrite_goal = str(issue.get("rewrite_goal") or issue.get("repair_goal") or issue.get("description") or issue.get("detail") or title).strip()
            guardrails = self._normalize_repair_guardrails(issue.get("guardrails"), issue_type)
            eligible = bool(issue_type in AUTO_REPAIR_ISSUE_TYPES and chapter > 0 and rewrite_goal)
            reason = ""
            if not eligible:
                if issue_type not in AUTO_REPAIR_ISSUE_TYPES:
                    reason = "当前问题类型不在自动修稿白名单内。"
                elif chapter <= 0:
                    reason = "当前问题缺少明确章节定位，无法直接发起自动修稿。"
                else:
                    reason = "当前问题缺少明确修稿目标，无法直接发起自动修稿。"

            candidate = {
                "chapter": chapter or None,
                "issue_type": issue_type or "UNKNOWN",
                "issue_title": title,
                "source": str(issue.get("source") or ""),
                "auto_rewrite_eligible": eligible,
                "rewrite_goal": rewrite_goal,
                "guardrails": guardrails,
            }
            if reason:
                candidate["reason"] = reason
            if eligible:
                candidate["operator_action"] = self._build_operator_action(
                    f"repair:{task.get('id')}:{chapter}:{issue_type}:{index}",
                    "launch-task",
                    "启动自动修稿",
                    variant="primary",
                    task_type="repair",
                    payload={
                        "project_root": project_root,
                        "chapter": chapter,
                        "mode": mode,
                        "require_manual_approval": False,
                        "options": {
                            "source_task_id": str(task.get("id") or ""),
                            "issue_type": issue_type,
                            "issue_title": title,
                            "rewrite_goal": rewrite_goal,
                            "guardrails": guardrails,
                        },
                    },
                )
            candidates.append(candidate)

        return candidates

    def _resolve_repair_chapter_meta_key(self, state_data: Dict[str, Any], chapter: int) -> str:
        chapter_meta = state_data.get("chapter_meta", {})
        if isinstance(chapter_meta, dict):
            for lookup_key in (f"{chapter:04d}", str(chapter)):
                if lookup_key in chapter_meta:
                    return lookup_key
            for raw_key in chapter_meta:
                try:
                    if int(str(raw_key).strip()) == chapter:
                        return str(raw_key)
                except ValueError:
                    continue
        return str(chapter)

    def _build_repair_plan(self, task: Dict[str, Any]) -> Dict[str, Any]:
        request = task.get("request") or {}
        options = request.get("options") if isinstance(request.get("options"), dict) else {}
        chapter = int(request.get("chapter") or 0)
        if chapter <= 0:
            raise RepairTaskError(REPAIR_INPUT_INVALID_CODE, "repair 缺少有效的 chapter。")
        issue_type = str(options.get("issue_type") or "").strip().upper()
        if not issue_type:
            raise RepairTaskError(REPAIR_INPUT_INVALID_CODE, "repair 缺少 issue_type。")
        if issue_type not in AUTO_REPAIR_ISSUE_TYPES:
            raise RepairTaskError(REPAIR_NOT_ELIGIBLE_CODE, "当前问题类型不在自动修稿白名单内。", {"issue_type": issue_type})
        issue_title = str(options.get("issue_title") or issue_type).strip()
        rewrite_goal = str(options.get("rewrite_goal") or "").strip()
        if not rewrite_goal:
            raise RepairTaskError(REPAIR_INPUT_INVALID_CODE, "repair 缺少 rewrite_goal。")
        chapter_file = self._default_chapter_file(chapter)
        chapter_path = self._resolve_project_path(chapter_file)
        if not chapter_path.is_file():
            raise RepairTaskError(REPAIR_INPUT_INVALID_CODE, f"repair 目标章节不存在：{chapter_file}")
        original_content = chapter_path.read_text(encoding="utf-8")
        if not original_content.strip():
            raise RepairTaskError(REPAIR_INPUT_INVALID_CODE, "repair 目标章节正文为空。")
        summary_file = self._default_summary_file(chapter)
        summary_path = self._resolve_project_path(summary_file)
        summary_content = summary_path.read_text(encoding="utf-8") if summary_path.is_file() else ""
        guardrails = self._normalize_repair_guardrails(options.get("guardrails"), issue_type)
        return {
            "chapter": chapter,
            "chapter_file": chapter_file,
            "summary_file": summary_file,
            "source_task_id": str(options.get("source_task_id") or ""),
            "issue_type": issue_type,
            "issue_title": issue_title,
            "rewrite_goal": rewrite_goal,
            "guardrails": guardrails,
            "original_word_count": self._canonical_word_count(original_content),
            "existing_summary_excerpt": self._extract_summary_excerpt(summary_content) if summary_content else "",
        }

    def _repair_backups_dir(self) -> Path:
        return self.project_root / REPAIR_BACKUPS_DIR_NAME

    def _repair_reports_dir(self) -> Path:
        return self.project_root / REPAIR_REPORTS_DIR_NAME

    def _repair_backup_path(self, chapter: int, *, kind: str, suffix: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        filename = f"ch{chapter:04d}-{timestamp}-{kind}.{suffix}"
        return self._repair_backups_dir() / filename

    def _repair_report_path(self, chapter: int) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        return self._repair_reports_dir() / f"repair-report-ch{chapter:04d}-{timestamp}.json"

    def _save_review_metrics_record(
        self,
        *,
        chapter: int,
        summary: Dict[str, Any],
        report_file: str,
    ) -> None:
        metrics = ReviewMetrics(
            start_chapter=chapter,
            end_chapter=chapter,
            overall_score=float(summary.get("overall_score") or 0.0),
            dimension_scores={
                reviewer.get("step_name", ""): float(reviewer.get("score") or 0.0)
                for reviewer in summary.get("reviewers", [])
                if reviewer.get("step_name")
            },
            severity_counts=summary.get("severity_counts") or {},
            critical_issues=[issue.get("title", issue.get("message", "")) for issue in summary.get("issues", []) if str(issue.get("severity", "")).lower() == "critical"],
            report_file=report_file,
            notes=json.dumps({**summary, "report_file": report_file}, ensure_ascii=False),
        )
        self.index_manager.save_review_metrics(metrics)

    def _apply_repair_writeback(self, task_id: str, task: Dict[str, Any]) -> Dict[str, Any]:
        request = task.get("request") or {}
        chapter = int(request.get("chapter") or 0)
        if chapter <= 0:
            raise RepairTaskError(REPAIR_INPUT_INVALID_CODE, "repair-writeback 缺少有效的 chapter")

        artifacts = task.get("artifacts") or {}
        step_results = artifacts.get("step_results") or {}
        repair_plan = (step_results.get("repair-plan") or {}).get("structured_output") or {}
        repair_output = (step_results.get("repair-draft") or {}).get("structured_output") or {}
        review_summary = artifacts.get("review_summary") or {}
        if bool(review_summary.get("blocking")):
            raise RepairTaskError(
                REPAIR_REVIEW_BLOCKED_CODE,
                "修稿复审未通过，禁止写回正文。",
                {
                    "blocking_issues": review_summary.get("hard_blocking_issues") or review_summary.get("issues") or [],
                    "review_summary": review_summary,
                },
            )

        chapter_file = self._default_chapter_file(chapter)
        summary_file = self._default_summary_file(chapter)
        chapter_path = self._resolve_project_path(chapter_file)
        summary_path = self._resolve_project_path(summary_file)
        if not chapter_path.is_file():
            raise RepairTaskError(REPAIR_INPUT_INVALID_CODE, f"repair 目标章节不存在：{chapter_file}")

        original_content = chapter_path.read_text(encoding="utf-8")
        original_summary = summary_path.read_text(encoding="utf-8") if summary_path.is_file() else ""
        content = str(repair_output.get("content") or "").strip()
        if not content:
            raise RepairTaskError(REPAIR_INPUT_INVALID_CODE, "repair-draft 未生成可写回的正文内容。")
        word_count = self._canonical_word_count(content)
        reported_word_count = self._parse_reported_word_count(repair_output)
        try:
            self._validate_writeback_content(content, word_count, reported_word_count)
        except ValueError as exc:
            raise RepairTaskError(REPAIR_INPUT_INVALID_CODE, str(exc)) from exc
        summary_content = self._build_summary_markdown(chapter, content, review_summary)

        backup_body_path = self._repair_backup_path(chapter, kind="body", suffix="md.bak")
        self._write_text_atomically(backup_body_path, original_content)
        backup_summary_rel: Optional[str] = None
        if original_summary:
            backup_summary_path = self._repair_backup_path(chapter, kind="summary", suffix="md.bak")
            self._write_text_atomically(backup_summary_path, original_summary)
            backup_summary_rel = self._relative_project_path(backup_summary_path)

        written_chapter_path = self._write_project_text(chapter_file, content)
        written_summary_path = self._write_project_text(summary_file, summary_content)

        state_data = self._read_state_data()
        chapter_meta = self._get_state_chapter_meta(state_data, chapter)
        chapter_meta_key = self._resolve_repair_chapter_meta_key(state_data, chapter)
        repaired_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        issue_types = [str(issue_type).strip() for issue_type in chapter_meta.get("last_repair_issue_types", []) if str(issue_type).strip()]
        current_issue_type = str(repair_plan.get("issue_type") or "").strip()
        if current_issue_type and current_issue_type not in issue_types:
            issue_types.append(current_issue_type)

        def _mutate(state_payload: Dict[str, Any]) -> None:
            chapter_meta_map = state_payload.setdefault("chapter_meta", {})
            if not isinstance(chapter_meta_map, dict):
                chapter_meta_map = {}
                state_payload["chapter_meta"] = chapter_meta_map
            merged_meta = dict(get_chapter_meta_entry(state_payload, chapter) or {})
            merged_meta.update(chapter_meta)
            merged_meta["last_repaired_at"] = repaired_at
            merged_meta["last_repair_task_id"] = task_id
            merged_meta["last_repair_issue_types"] = issue_types
            chapter_meta_map[chapter_meta_key] = merged_meta

        self._update_state_data(_mutate)

        self.index_manager.add_chapter(
            ChapterMeta(
                chapter=chapter,
                title=self._resolve_chapter_title(chapter, content, chapter_meta),
                location=str(chapter_meta.get("location") or ""),
                word_count=word_count,
                characters=self._normalize_characters(chapter_meta.get("characters")),
                summary=self._extract_summary_excerpt(summary_content),
                file_path=self._relative_project_path(written_chapter_path),
            )
        )

        report_path = self._repair_report_path(chapter)
        report_payload = {
            "chapter": chapter,
            "generated_at": repaired_at,
            "task_id": task_id,
            "source_task_id": repair_plan.get("source_task_id"),
            "issue_type": repair_plan.get("issue_type"),
            "issue_title": repair_plan.get("issue_title"),
            "rewrite_goal": repair_plan.get("rewrite_goal"),
            "guardrails": repair_plan.get("guardrails") or [],
            "chapter_file": self._relative_project_path(written_chapter_path),
            "summary_file": self._relative_project_path(written_summary_path),
            "backup_paths": {
                "chapter": self._relative_project_path(backup_body_path),
                "summary": backup_summary_rel,
            },
            "before_summary": self._extract_summary_excerpt(original_summary or original_content),
            "after_summary": self._extract_summary_excerpt(summary_content),
            "review_summary": review_summary,
            "issue_mapping": [
                {
                    "issue_type": repair_plan.get("issue_type"),
                    "issue_title": repair_plan.get("issue_title"),
                    "rewrite_goal": repair_plan.get("rewrite_goal"),
                }
            ],
        }
        self._write_json_atomically(report_path, report_payload)
        self._save_review_metrics_record(
            chapter=chapter,
            summary=review_summary,
            report_file=self._relative_project_path(report_path),
        )

        latest_task = self.store.get_task(task_id) or task
        latest_artifacts = dict(latest_task.get("artifacts") or {})
        latest_artifacts["repair"] = {
            "chapter": chapter,
            "chapter_file": self._relative_project_path(written_chapter_path),
            "summary_file": self._relative_project_path(written_summary_path),
            "backup_paths": {
                "chapter": self._relative_project_path(backup_body_path),
                "summary": backup_summary_rel,
            },
            "report_file": self._relative_project_path(report_path),
            "issue_type": repair_plan.get("issue_type"),
            "issue_title": repair_plan.get("issue_title"),
            "rewrite_goal": repair_plan.get("rewrite_goal"),
            "word_count": word_count,
            "review_summary": review_summary,
        }
        self.store.update_task(task_id, artifacts=latest_artifacts)
        return latest_artifacts["repair"]

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
        repair_candidates = self._build_repair_candidates(task, issues)
        return {
            "overall_score": overall_score,
            "reviewers": reviewers,
            "issues": issues,
            "severity_counts": severity_counts,
            "hard_blocking_issues": hard_blocking_issues,
            "blocking": blocking,
            "can_proceed": not blocking,
            "repair_candidates": repair_candidates,
            "repairable_issue_count": sum(1 for item in repair_candidates if item.get("auto_rewrite_eligible")),
        }

    def _persist_review_summary(self, task: Dict[str, Any], summary: Dict[str, Any]) -> None:
        request = task.get("request") or {}
        chapter = int(request.get("chapter") or 0)
        chapter_range = self._parse_chapter_range(request.get("chapter_range"))
        if chapter > 0:
            start_chapter = chapter
            end_chapter = chapter
        elif chapter_range is not None:
            start_chapter, end_chapter = chapter_range
        else:
            return
        report_file = self._review_report_file(start_chapter, end_chapter)
        report_path = self._write_project_text(
            report_file,
            self._build_review_report_markdown(task, summary, start_chapter=start_chapter, end_chapter=end_chapter),
        )
        reviewed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        def _mutate(state_data: Dict[str, Any]) -> None:
            self._upsert_review_checkpoint(
                state_data,
                start_chapter=start_chapter,
                end_chapter=end_chapter,
                report_file=self._relative_project_path(report_path),
                reviewed_at=reviewed_at,
                summary=summary,
            )

        self._update_state_data(_mutate)
        metrics = ReviewMetrics(
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            overall_score=float(summary.get("overall_score") or 0.0),
            dimension_scores={
                reviewer.get("step_name", ""): float(reviewer.get("score") or 0.0)
                for reviewer in summary.get("reviewers", [])
                if reviewer.get("step_name")
            },
            severity_counts=summary.get("severity_counts") or {},
            critical_issues=[issue.get("title", issue.get("message", "")) for issue in summary.get("issues", []) if str(issue.get("severity", "")).lower() == "critical"],
            report_file=self._relative_project_path(report_path),
            notes=json.dumps({**summary, "report_file": self._relative_project_path(report_path)}, ensure_ascii=False),
        )
        self.index_manager.save_review_metrics(metrics)

    def _review_report_file(self, start_chapter: int, end_chapter: int) -> str:
        return f"{REVIEW_REPORT_DIR_NAME}/\u7b2c{start_chapter}-{end_chapter}\u7ae0\u5ba1\u67e5\u62a5\u544a.md"

    def _build_review_report_markdown(
        self,
        task: Dict[str, Any],
        summary: Dict[str, Any],
        *,
        start_chapter: int,
        end_chapter: int,
    ) -> str:
        reviewers = summary.get("reviewers") or []
        issues = summary.get("issues") or []
        severity_counts = summary.get("severity_counts") or {}
        request = task.get("request") or {}
        lines = [
            f"# 第 {start_chapter}-{end_chapter} 章质量审查报告",
            "",
            "## 总览",
            f"- 任务类型: {task.get('task_type') or 'review'}",
            f"- 章节范围: {start_chapter}-{end_chapter}",
            f"- 总评分: {summary.get('overall_score', 0)}",
            f"- 是否阻断: {'是' if bool(summary.get('blocking')) else '否'}",
            f"- 是否可继续: {'是' if bool(summary.get('can_proceed', True)) else '否'}",
            f"- 审查器数量: {len(reviewers)}",
            f"- 问题数量: {len(issues)}",
        ]
        if request:
            lines.append(f"- request: {json.dumps(request, ensure_ascii=False)}")
        if severity_counts:
            lines.extend(["", "## 严重度统计"])
            for level in ("critical", "high", "medium", "low"):
                lines.append(f"- {self._translate_review_severity(level)}: {severity_counts.get(level, 0)}")
        if reviewers:
            lines.extend(["", "## 分审查器结果"])
            for reviewer in reviewers:
                lines.append(
                    f"- {reviewer.get('step_name')}: score={reviewer.get('score', 0)}, pass={reviewer.get('pass')}, summary={reviewer.get('summary') or ''}"
                )
        lines.extend(["", "## 问题清单"])
        if issues:
            for idx, issue in enumerate(issues, start=1):
                title = issue.get("title") or issue.get("message") or "未命名问题"
                severity = issue.get("severity") or "medium"
                source = issue.get("source") or "unknown"
                detail = issue.get("description") or issue.get("detail") or ""
                lines.append(f"{idx}. [{self._translate_review_severity(severity)}] {title} ({source})")
                if detail:
                    lines.append(f"   - {detail}")
        else:
            lines.append("- 无")
        return "\n".join(lines).strip() + "\n"

    def _upsert_review_checkpoint(
        self,
        state_data: Dict[str, Any],
        *,
        start_chapter: int,
        end_chapter: int,
        report_file: str,
        reviewed_at: str,
        summary: Dict[str, Any],
    ) -> None:
        checkpoints = state_data.setdefault("review_checkpoints", [])
        if not isinstance(checkpoints, list):
            checkpoints = []
            state_data["review_checkpoints"] = checkpoints
        chapters_range = f"{start_chapter}-{end_chapter}"
        entry = {
            "chapters": chapters_range,
            "report": report_file,
            "reviewed_at": reviewed_at,
            "overall_score": float(summary.get("overall_score") or 0.0),
            "blocking": bool(summary.get("blocking")),
        }
        for index, checkpoint in enumerate(checkpoints):
            if isinstance(checkpoint, dict) and str(checkpoint.get("chapters") or "").strip() == chapters_range:
                checkpoints[index] = {**checkpoint, **entry}
                return
        checkpoints.append(entry)

    def _parse_chapter_range(self, raw_value: Any) -> Optional[tuple[int, int]]:
        if raw_value is None:
            return None
        text = str(raw_value).strip()
        if not text or "-" not in text:
            return None
        start_text, end_text = [part.strip() for part in text.split("-", 1)]
        if not start_text.isdigit() or not end_text.isdigit():
            return None
        start_chapter = int(start_text)
        end_chapter = int(end_text)
        if start_chapter <= 0 or end_chapter < start_chapter:
            return None
        return start_chapter, end_chapter

    def _resolve_resume_target_task(self, resume_task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        request = resume_task.get("request") or {}
        requested_chapter = int(request.get("chapter") or 0)
        requested_range = str(request.get("chapter_range") or "").strip()
        options = request.get("options") if isinstance(request.get("options"), dict) else {}
        explicit_target_id = options.get("target_task_id")
        if explicit_target_id:
            target = self.store.get_task(str(explicit_target_id))
            if target and target.get("task_type") != "resume":
                return target

        candidates: List[Dict[str, Any]] = []
        for candidate in self.store.list_tasks(limit=200):
            if candidate.get("task_type") == "resume":
                continue
            if candidate.get("project_root") != str(self.project_root):
                continue
            if candidate.get("status") not in {"interrupted", "resumable"}:
                continue
            if requested_chapter and int((candidate.get("request") or {}).get("chapter") or 0) != requested_chapter:
                continue
            if requested_range and str((candidate.get("request") or {}).get("chapter_range") or "").strip() != requested_range:
                continue
            candidates.append(candidate)

        if not candidates:
            return None

        status_order = {"running": 0, "interrupted": 1, "resumable": 2}
        candidates.sort(
            key=lambda item: self._parse_iso_datetime(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        candidates.sort(key=lambda item: status_order.get(str(item.get("status")), 99))
        return candidates[0]

    def _build_resume_decision(self, target: Dict[str, Any]) -> Dict[str, Any]:
        if target.get("task_type") == "write" and self._writeback_is_complete(target):
            return {
                "action": "complete",
                "resume_from_step": None,
                "reason": "writeback already persisted",
                "target_task_id": target["id"],
            }
        resume_from_step = self._determine_resume_from_step(target)
        if resume_from_step is None:
            return {
                "action": "complete",
                "resume_from_step": None,
                "reason": "all workflow steps are already persisted",
                "target_task_id": target["id"],
            }
        return {
            "action": "resume",
            "resume_from_step": resume_from_step,
            "reason": f"resume from {resume_from_step}",
            "target_task_id": target["id"],
        }

    def _build_resume_result_contract(
        self,
        *,
        task_id: str,
        target: Optional[Dict[str, Any]],
        decision: Dict[str, Any],
        outcome: str,
        blocking_reason: str = "",
    ) -> Dict[str, Any]:
        target_task_id = str((target or {}).get("id") or decision.get("target_task_id") or "")
        resume_from_step = decision.get("resume_from_step")
        decision_reason = str(decision.get("reason") or "")
        if outcome == "complete":
            resume_action = self._build_operator_action(
                f"resume:{task_id}:complete",
                "complete-noop",
                "无需恢复",
                variant="secondary",
                disabled=True,
                reason=decision_reason,
            )
        elif outcome == "resume":
            resume_action = self._build_operator_action(
                f"resume:{task_id}:resume",
                "resume-existing-task",
                "继续恢复当前任务",
                variant="primary",
                task_id=target_task_id or None,
                resume_from_step=resume_from_step,
                reason=decision_reason,
            )
        else:
            resume_action = self._build_operator_action(
                f"resume:{task_id}:blocked",
                "open-blocked-task",
                "查看阻塞任务",
                variant="primary",
                task_id=target_task_id or None,
                disabled=not bool(target_task_id),
                reason=blocking_reason or decision_reason or None,
            )

        return {
            "target_task_id": target_task_id,
            "resume_from_step": resume_from_step,
            "resume_reason": decision_reason,
            "blocking_reason": str(blocking_reason or ""),
            "resume_action": resume_action,
            "operator_actions": [resume_action],
            "decision": decision,
        }

    def _determine_resume_from_step(self, task: Dict[str, Any]) -> Optional[str]:
        workflow = self._resolve_task_workflow(task)
        steps = [step["name"] for step in workflow.get("steps", [])]
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        current_step = task.get("current_step")
        if current_step in {"polish", "data-sync", "repair-writeback"}:
            return current_step
        if task.get("task_type") == "write" and task.get("approval_status") == "approved":
            if current_step in {"approval-gate", "data-sync"}:
                return current_step
            if "polish" in step_results and "data-sync" not in step_results:
                return "data-sync"
        if task.get("task_type") == "repair" and task.get("approval_status") == "approved":
            if current_step in {"approval-gate", "repair-writeback"}:
                return current_step
            if "review-summary" in step_results and "repair-writeback" not in step_results:
                return "repair-writeback"
        if current_step and current_step in steps:
            return current_step
        for step_name in steps:
            if step_name not in step_results:
                return step_name
        return None

    def _writeback_is_complete(self, task: Dict[str, Any]) -> bool:
        request = task.get("request") or {}
        chapter = int(request.get("chapter") or 0)
        if chapter <= 0:
            return False
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        draft_output = (step_results.get("draft") or {}).get("structured_output") or {}
        polish_output = (step_results.get("polish") or {}).get("structured_output") or {}
        data_sync_output = (step_results.get("data-sync") or {}).get("structured_output") or {}
        writeback = ((task.get("artifacts") or {}).get("writeback") or {})
        chapter_file = str(writeback.get("chapter_file") or self._default_chapter_file(chapter))
        summary_file = str(writeback.get("summary_file") or self._default_summary_file(chapter))
        chapter_path = self._resolve_project_path(chapter_file)
        summary_path = self._resolve_project_path(summary_file)
        if not chapter_path.is_file() or not summary_path.is_file():
            return False
        chapter_record = self.index_manager.get_chapter(chapter)
        if not chapter_record:
            return False
        indexed_path = str(chapter_record.get("file_path") or "").replace("\\", "/")
        if indexed_path != self._default_chapter_file(chapter):
            return False
        metrics_records = self.index_manager.get_recent_review_metrics(limit=max(10, chapter + 2))
        if not any(
            int(record.get("start_chapter") or 0) == chapter and int(record.get("end_chapter") or 0) == chapter
            for record in metrics_records
        ):
            return False
        state_data = self._read_state_data()
        progress = state_data.get("progress") or {}
        if int(progress.get("current_chapter") or 0) < chapter:
            return False
        chapter_meta = self._get_state_chapter_meta(state_data, chapter)
        return bool(chapter_meta)

    def _get_state_chapter_meta(self, state_data: Dict[str, Any], chapter: int) -> Dict[str, Any]:
        try:
            return dict(get_chapter_meta_entry(state_data, chapter) or {})
        except Exception:
            return {}

    def _volume_plan_filename(self, volume: str) -> str:
        normalized = volume.strip()
        if normalized.isdigit():
            return f"volume-{int(normalized):02d}-plan.md"
        safe_value = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in normalized).strip("-") or "custom"
        return f"volume-{safe_value}-plan.md"

    def _build_volume_plan_markdown(self, volume: str, payload: Dict[str, Any]) -> str:
        volume_plan = payload.get("volume_plan") or {}
        chapters = payload.get("chapters") or []
        lines = [
            f"# Volume {volume} Plan",
            "",
            f"Title: {volume_plan.get('title') or f'Volume {volume}'}",
        ]
        summary_text = volume_plan.get("summary") or volume_plan.get("description") or ""
        if summary_text:
            lines.extend(["", "## Summary", str(summary_text).strip()])
        if chapters:
            lines.extend(["", "## Chapter Beats"])
            for item in chapters:
                chapter_num = item.get("chapter", "?")
                goal = item.get("goal") or item.get("summary") or item.get("hook") or ""
                lines.append(f"- Chapter {chapter_num}: {goal}".rstrip())
        lines.append("")
        return "\n".join(lines)

    def _summarize_volume_plan(self, payload: Dict[str, Any]) -> str:
        volume_plan = payload.get("volume_plan") or {}
        summary_text = str(volume_plan.get("summary") or volume_plan.get("description") or "").strip()
        if summary_text:
            return summary_text[:300]
        chapters = payload.get("chapters") or []
        if not chapters:
            return ""
        snippets = []
        for item in chapters[:5]:
            goal = str(item.get("goal") or item.get("summary") or item.get("hook") or "").strip()
            if goal:
                snippets.append(goal)
        return " | ".join(snippets)[:300]

    def _resolve_chapter_title(self, chapter: int, content: str, chapter_meta: Dict[str, Any]) -> str:
        title = str(chapter_meta.get("title") or "").strip()
        if title:
            return title
        for line in content.splitlines():
            stripped = line.strip().lstrip("#").strip()
            if stripped:
                return stripped[:120]
        return f"Chapter {chapter:04d}"

    def _normalize_characters(self, characters: Any) -> List[str]:
        if isinstance(characters, list):
            return [str(item).strip() for item in characters if str(item).strip()]
        if isinstance(characters, str) and characters.strip():
            return [characters.strip()]
        return []

    def _extract_summary_excerpt(self, summary_content: str) -> str:
        text = " ".join(line.strip() for line in summary_content.splitlines() if line.strip() and not line.strip().startswith("#"))
        return text[:500]

    def _run_plan_preflight(self, task_id: str, task: Dict[str, Any], step: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if task.get("task_type") != "plan" or step.get("name") != "plan":
            return None

        health = self._evaluate_plan_inputs()
        latest_task = self.store.get_task(task_id) or task
        latest_artifacts = dict(latest_task.get("artifacts") or {})
        latest_artifacts["plan_health_check"] = health
        self.store.update_task(task_id, artifacts=latest_artifacts)
        self.store.append_event(
            task_id,
            "info" if health["ok"] else "warning",
            "plan_input_health_checked" if health["ok"] else "plan_input_health_failed",
            step_name=step["name"],
            payload=health,
        )
        if health["ok"]:
            return None

        blocked_payload = {
            "plan_blocked": True,
            "reason": str(health.get("reason") or "planning_profile_incomplete"),
            "blocking_items": health.get("blocking_items", []),
            "next_step": "请先到总览页补齐规划必填信息，然后重新运行 plan。",
            "fill_template": build_planning_fill_template(),
            "readiness": health,
        }
        error_info = self._build_plan_blocked_error(blocked_payload)
        self.store.save_step_result(task_id, step["name"], {"success": False, "structured_output": blocked_payload, "error": error_info})
        latest_artifacts.update(
            {
                "plan_blocked": True,
                "blocking_items": blocked_payload["blocking_items"],
                "next_step": blocked_payload["next_step"],
                "fill_template": blocked_payload["fill_template"],
                "plan_health_check": health,
            }
        )
        self.store.update_task(task_id, artifacts=latest_artifacts)
        self._persist_plan_blocked_state(
            task_id,
            latest_task,
            reason=str(blocked_payload["reason"] or "planning_profile_incomplete"),
            blocking_items=blocked_payload["blocking_items"],
            readiness=health,
        )
        self.store.append_event(
            task_id,
            "warning",
            "plan_blocked",
            step_name=step["name"],
            payload=blocked_payload,
        )
        return error_info

    def _evaluate_plan_inputs(self) -> Dict[str, Any]:
        outline_path = self.project_root / OUTLINE_DIR_NAME / OUTLINE_SUMMARY_FILE
        state_data = self._read_state_data()
        project_info = state_data.get("project_info") or {}
        planning = state_data.setdefault("planning", {})
        planning_project_info = planning.setdefault("project_info", {})
        planning_project_info.setdefault("title", str(project_info.get("title") or "").strip())
        planning_project_info.setdefault("genre", str(project_info.get("genre") or "").strip())
        planning_project_info.setdefault("outline_file", f"{OUTLINE_DIR_NAME}/{OUTLINE_SUMMARY_FILE}")
        file_profile = load_planning_profile(
            self.project_root,
            title=str(project_info.get("title") or "").strip(),
            genre=str(project_info.get("genre") or "").strip(),
        )
        profile = normalize_planning_profile(
            {**dict(planning.get("profile") or {}), **dict(file_profile or {})},
            title=str(project_info.get("title") or "").strip(),
            genre=str(project_info.get("genre") or "").strip(),
        )
        outline_text = outline_path.read_text(encoding="utf-8") if outline_path.is_file() else ""
        readiness = evaluate_planning_readiness(profile, outline_text=outline_text)
        blocking_items = list(readiness.get("blocking_items") or [])
        if not outline_path.is_file():
            blocking_items = [
                {
                    "field": "outline_file",
                    "label": "总纲文件",
                    "format_hint": "请确认大纲/总纲.md 已生成。",
                },
                *blocking_items,
            ]
        readiness.update(
            {
                "reason": "ready" if readiness["ok"] else "planning_profile_incomplete",
                "outline_file": f"{OUTLINE_DIR_NAME}/{OUTLINE_SUMMARY_FILE}",
                "outline_chars": len(outline_text.strip()),
                "project_title": str(project_info.get("title") or "").strip(),
                "project_genre": str(project_info.get("genre") or "").strip(),
                "planning_project_info": dict(planning_project_info),
                "source_order": [
                    ".webnovel/planning-profile.json",
                    "state.json planning.project_info",
                    "大纲/总纲.md",
                ],
                "blocking_items": blocking_items,
            }
        )
        if not outline_path.is_file():
            readiness["ok"] = False
            readiness["reason"] = "outline_missing"
            readiness["message"] = "master outline file is missing"
            readiness["missing_count"] = len(blocking_items)
        def _mutate(latest_state: Dict[str, Any]) -> None:
            latest_planning = latest_state.setdefault("planning", {})
            latest_planning["profile"] = profile
            latest_planning["project_info"] = {
                **dict(latest_planning.get("project_info") or {}),
                **dict(planning_project_info),
            }
            latest_planning["readiness"] = readiness

        self._update_state_data(_mutate)
        return readiness

    def _build_plan_blocked_error(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        readiness = payload.get("readiness") or {}
        return {
            "code": PLAN_INPUT_BLOCKED_CODE,
            "message": PLAN_INPUT_BLOCKED_MESSAGE,
            "retryable": True,
            "details": {
                "reason": str(payload.get("reason") or readiness.get("reason") or "planning_profile_incomplete"),
                "blocking_items": list(payload.get("blocking_items") or readiness.get("blocking_items") or []),
                "next_step": str(payload.get("next_step") or ""),
            },
        }

    def _build_plan_profile_summary(self) -> Dict[str, Any]:
        state_data = self._read_state_data()
        project_info = state_data.get("project_info") or {}
        planning = state_data.get("planning") or {}
        file_profile = load_planning_profile(
            self.project_root,
            title=str(project_info.get("title") or "").strip(),
            genre=str(project_info.get("genre") or "").strip(),
        )
        profile = normalize_planning_profile(
            {**dict(planning.get("profile") or {}), **dict(file_profile or {})},
            title=str(project_info.get("title") or "").strip(),
            genre=str(project_info.get("genre") or "").strip(),
        )
        return {
            "story_logline": profile.get("story_logline") or "",
            "protagonist": {
                "name": profile.get("protagonist_name") or "",
                "identity": profile.get("protagonist_identity") or "",
                "desire": profile.get("protagonist_desire") or "",
                "flaw": profile.get("protagonist_flaw") or "",
            },
            "core_setting": profile.get("core_setting") or "",
            "ability_cost": profile.get("ability_cost") or "",
            "volume_1": {
                "title": profile.get("volume_1_title") or "",
                "conflict": profile.get("volume_1_conflict") or "",
                "climax": profile.get("volume_1_climax") or "",
            },
            "major_characters_preview": [line.strip() for line in str(profile.get("major_characters_text") or "").splitlines() if line.strip()][:3],
            "factions_preview": [line.strip() for line in str(profile.get("factions_text") or "").splitlines() if line.strip()][:3],
            "rules_preview": [line.strip() for line in str(profile.get("rules_outline") or "").splitlines() if line.strip()][:3],
        }

    def _normalize_state_payload(self, chapter: int, payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        chapter_meta = dict(payload.get("chapter_meta") or {})
        state_payload: Dict[str, Any] = {
            "entities_appeared": list(payload.get("entities_appeared", [])),
            "entities_new": list(payload.get("entities_new", [])),
            "state_changes": list(payload.get("state_changes", [])),
            "relationships_new": list(payload.get("relationships_new", [])),
            "uncertain": list(payload.get("uncertain", [])),
            "chapter_meta": chapter_meta,
        }
        structured_sync: Dict[str, Any] = {
            "input_detected": False,
            "entities": [],
            "relationships": [],
            "world_settings": {"power_system": [], "factions": [], "locations": []},
            "warnings": [],
            "summary": {
                "normalized_entries": 0,
                "entity_records": 0,
                "relationship_records": 0,
                "world_setting_records": 0,
                "state_change_records": 0,
            },
        }
        structured_names: Dict[str, List[str]] = {"factions": [], "locations": [], "rules": []}

        key_category_pairs = (
            ("organizations", "faction"),
            ("factions", "faction"),
            ("institutions", "faction"),
            ("agencies", "faction"),
            ("locations", "location"),
            ("places", "location"),
            ("sites", "location"),
            ("observation_points", "location"),
            ("rules", "rule"),
            ("world_rules", "rule"),
            ("setting_rules", "rule"),
            ("power_rules", "rule"),
        )

        for raw_key, default_category in key_category_pairs:
            for item in self._coerce_setting_items(payload.get(raw_key)):
                structured_sync["input_detected"] = True
                normalized = self._normalize_setting_entry(item, default_category)
                if normalized is None:
                    structured_sync["warnings"].append(f"unrecognized_setting:{raw_key}")
                    continue
                self._apply_normalized_setting(state_payload, chapter, normalized, structured_sync, structured_names)

        for item in self._coerce_setting_items(payload.get("setting_entries")):
            structured_sync["input_detected"] = True
            normalized = self._normalize_setting_entry(item, None)
            if normalized is None:
                structured_sync["warnings"].append("unrecognized_setting:setting_entries")
                continue
            self._apply_normalized_setting(state_payload, chapter, normalized, structured_sync, structured_names)

        for raw_key, default_category in key_category_pairs:
            for item in self._coerce_setting_items(chapter_meta.get(raw_key)):
                structured_sync["input_detected"] = True
                normalized = self._normalize_setting_entry(item, default_category)
                if normalized is None:
                    structured_sync["warnings"].append(f"unrecognized_chapter_meta:{raw_key}")
                    continue
                self._apply_normalized_setting(state_payload, chapter, normalized, structured_sync, structured_names)

        structured_settings_meta = chapter_meta.setdefault("structured_settings", {})
        if structured_names["factions"]:
            structured_settings_meta["factions"] = sorted(set(structured_names["factions"]))
        if structured_names["locations"]:
            structured_settings_meta["locations"] = sorted(set(structured_names["locations"]))
        if structured_names["rules"]:
            structured_settings_meta["rules"] = sorted(set(structured_names["rules"]))
        structured_sync["relationships"] = self._normalize_relationship_entries(
            chapter,
            payload.get("relationships_new"),
            structured_sync["entities"],
            structured_sync["warnings"],
        )

        structured_sync["summary"] = {
            "normalized_entries": len(structured_sync["entities"]) + len(structured_sync["relationships"]),
            "entity_records": len(structured_sync["entities"]),
            "relationship_records": len(structured_sync["relationships"]),
            "world_setting_records": sum(len(items) for items in structured_sync["world_settings"].values()),
            "state_change_records": max(0, len(state_payload["state_changes"]) - len(payload.get("state_changes", []))),
        }
        return state_payload, structured_sync

    def _normalize_narrative_payload(self, chapter: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        foreshadowing_items: List[Dict[str, Any]] = []
        timeline_events: List[Dict[str, Any]] = []
        character_arcs: List[Dict[str, Any]] = []
        knowledge_states: List[Dict[str, Any]] = []
        warnings: List[str] = []
        input_detected = False

        raw_foreshadowing = payload.get("foreshadowing_items")
        if isinstance(raw_foreshadowing, list):
            input_detected = True
            for item in raw_foreshadowing:
                if not isinstance(item, dict):
                    warnings.append("unrecognized_foreshadowing_item")
                    continue
                name = str(item.get("name") or item.get("title") or item.get("label") or item.get("content") or "").strip()
                if not name:
                    warnings.append("foreshadowing_missing_name")
                    continue
                foreshadowing_items.append(
                    {
                        "name": name,
                        "content": str(item.get("content") or item.get("summary") or name).strip(),
                        "planted_chapter": self._coerce_narrative_int(item.get("planted_chapter") or item.get("chapter"), default=chapter),
                        "planned_payoff_chapter": self._coerce_narrative_int(item.get("planned_payoff_chapter") or item.get("due_chapter"), default=0),
                        "payoff_chapter": self._coerce_narrative_int(item.get("payoff_chapter"), default=0),
                        "status": str(item.get("status") or "active").strip() or "active",
                        "importance": str(item.get("importance") or item.get("tier") or "medium").strip() or "medium",
                        "owner_entity": str(item.get("owner_entity") or item.get("entity_id") or "").strip(),
                        "payoff_note": str(item.get("payoff_note") or item.get("note") or "").strip(),
                    }
                )

        raw_timeline = payload.get("timeline_events")
        if isinstance(raw_timeline, list):
            input_detected = True
            for item in raw_timeline:
                if not isinstance(item, dict):
                    warnings.append("unrecognized_timeline_event")
                    continue
                summary = str(item.get("summary") or item.get("content") or item.get("description") or "").strip()
                if not summary:
                    warnings.append("timeline_missing_summary")
                    continue
                timeline_events.append(
                    {
                        "chapter": self._coerce_narrative_int(item.get("chapter"), default=chapter),
                        "scene_index": self._coerce_narrative_int(item.get("scene_index"), default=0),
                        "event_time_label": str(item.get("event_time_label") or item.get("time_label") or "").strip(),
                        "location": str(item.get("location") or "").strip(),
                        "summary": summary,
                        "participants": self._normalize_characters(item.get("participants")),
                        "objective_fact": self._coerce_narrative_bool(item.get("objective_fact"), default=True),
                        "source": str(item.get("source") or "data-sync").strip() or "data-sync",
                    }
                )

        raw_character_arcs = payload.get("character_arcs")
        if isinstance(raw_character_arcs, list):
            input_detected = True
            for item in raw_character_arcs:
                if not isinstance(item, dict):
                    warnings.append("unrecognized_character_arc")
                    continue
                entity_id = str(item.get("entity_id") or item.get("character") or item.get("id") or "").strip()
                if not entity_id:
                    warnings.append("character_arc_missing_entity_id")
                    continue
                character_arcs.append(
                    {
                        "entity_id": entity_id,
                        "chapter": self._coerce_narrative_int(item.get("chapter"), default=chapter),
                        "desire": str(item.get("desire") or "").strip(),
                        "fear": str(item.get("fear") or "").strip(),
                        "misbelief": str(item.get("misbelief") or "").strip(),
                        "arc_stage": str(item.get("arc_stage") or item.get("stage") or "").strip(),
                        "relationship_state": self._coerce_narrative_object(item.get("relationship_state")),
                        "notes": str(item.get("notes") or item.get("note") or "").strip(),
                    }
                )

        raw_knowledge_states = payload.get("knowledge_states")
        if isinstance(raw_knowledge_states, list):
            input_detected = True
            for item in raw_knowledge_states:
                if not isinstance(item, dict):
                    warnings.append("unrecognized_knowledge_state")
                    continue
                entity_id = str(item.get("entity_id") or item.get("character") or item.get("id") or "").strip()
                topic = str(item.get("topic") or "").strip()
                belief = str(item.get("belief") or "").strip()
                if not entity_id or not topic or not belief:
                    warnings.append("knowledge_state_missing_fields")
                    continue
                try:
                    confidence = float(item.get("confidence") if item.get("confidence") is not None else 1.0)
                except (TypeError, ValueError):
                    confidence = 1.0
                knowledge_states.append(
                    {
                        "entity_id": entity_id,
                        "chapter": self._coerce_narrative_int(item.get("chapter"), default=chapter),
                        "topic": topic,
                        "belief": belief,
                        "truth_status": str(item.get("truth_status") or "unknown").strip() or "unknown",
                        "confidence": max(0.0, min(1.0, confidence)),
                        "evidence": str(item.get("evidence") or "").strip(),
                    }
                )

        summary = {
            "normalized_entries": len(foreshadowing_items) + len(timeline_events) + len(character_arcs) + len(knowledge_states),
            "foreshadowing_items": len(foreshadowing_items),
            "timeline_events": len(timeline_events),
            "character_arcs": len(character_arcs),
            "knowledge_states": len(knowledge_states),
        }
        return {
            "input_detected": input_detected,
            "foreshadowing_items": foreshadowing_items,
            "timeline_events": timeline_events,
            "character_arcs": character_arcs,
            "knowledge_states": knowledge_states,
            "warnings": warnings,
            "summary": summary,
        }

    def _coerce_narrative_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        normalized = str(value).strip().casefold()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
        return default

    def _coerce_narrative_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _coerce_narrative_object(self, value: Any) -> Dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    def _enrich_data_sync_payload(self, task: Dict[str, Any], payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        enriched = dict(payload)
        chapter_meta = dict(enriched.get("chapter_meta") or {})
        enrichment: Dict[str, Any] = {"applied": False}

        state_data = self._read_state_data()
        profile = ((state_data.get("planning") or {}).get("profile") or {})
        step_results = ((task.get("artifacts") or {}).get("step_results") or {})
        context_output = ((step_results.get("context") or {}).get("structured_output") or {})
        task_brief = context_output.get("task_brief") if isinstance(context_output.get("task_brief"), dict) else {}

        if not self._coerce_setting_items(enriched.get("organizations")):
            organization_entries = self._entries_from_multiline_text(profile.get("factions_text") or profile.get("factions"))
            if organization_entries:
                enriched["organizations"] = organization_entries
                enrichment["organizations"] = len(organization_entries)
                enrichment["applied"] = True

        if not self._coerce_setting_items(enriched.get("world_rules")):
            world_rule_entries = self._merge_named_entries(
                [],
                [
                    *self._entries_from_multiline_text(profile.get("rules_outline")),
                    *self._entries_from_text_fields(
                        profile.get("golden_finger_name"),
                        profile.get("core_setting"),
                        profile.get("ability_cost"),
                        profile.get("gf_irreversible_cost"),
                        profile.get("power_system_type"),
                    ),
                ],
            )
            if world_rule_entries:
                enriched["world_rules"] = world_rule_entries
                enrichment["world_rules"] = len(world_rule_entries)
                enrichment["applied"] = True

        if not self._normalize_characters(chapter_meta.get("characters")):
            character_names = self._character_names_from_profile(profile)
            if character_names:
                chapter_meta["characters"] = character_names
                enrichment["chapter_characters"] = len(character_names)
                enrichment["applied"] = True

        if not str(chapter_meta.get("title") or "").strip():
            title = ""
            if isinstance(task_brief, dict):
                title = str(task_brief.get("title") or task_brief.get("chapter_title") or "").strip()
            if title:
                chapter_meta["title"] = title
                enrichment["chapter_title"] = title
                enrichment["applied"] = True

        if chapter_meta:
            enriched["chapter_meta"] = chapter_meta
        return enriched, enrichment

    def _entries_from_text_fields(self, *values: Any) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            entries.append({"name": text})
        return entries

    def _entries_from_multiline_text(self, value: Any) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        for row in self._split_structured_text(value):
            parts = [part.strip() for part in row.split("|")]
            name = parts[0] if parts else ""
            if not name:
                continue
            entry: Dict[str, Any] = {"name": name}
            summary = " | ".join(part for part in parts[1:] if part)
            if summary:
                entry["summary"] = summary
            entries.append(entry)
        return entries

    def _character_names_from_profile(self, profile: Dict[str, Any]) -> List[str]:
        names: List[str] = []
        protagonist_name = str(profile.get("protagonist_name") or "").strip()
        if protagonist_name:
            names.append(protagonist_name)
        for row in self._split_structured_text(profile.get("major_characters_text")):
            name = row.split("|", 1)[0].strip()
            if name:
                names.append(name)
        return self._merge_string_entries([], names)

    def _split_structured_text(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).replace("\r", "\n")
        parts = re.split(r"[\n;；]+", text)
        return [part.strip() for part in parts if part.strip()]

    def _merge_named_entries(self, current: Any, fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for item in [*self._coerce_setting_items(current), *fallback]:
            if isinstance(item, str):
                name = item.strip()
                if not name:
                    continue
                entry = {"name": name}
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("title") or "").strip()
                if not name:
                    continue
                entry = dict(item)
                entry["name"] = name
            else:
                continue
            key = str(entry["name"]).casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(entry)
        return merged

    def _merge_string_entries(self, current: Any, fallback: List[str]) -> List[str]:
        merged: List[str] = []
        seen: set[str] = set()
        for item in [*self._normalize_characters(current), *fallback]:
            value = str(item).strip()
            if not value:
                continue
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            merged.append(value)
        return merged

    def _coerce_setting_items(self, raw: Any) -> List[Any]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, tuple):
            return list(raw)
        if isinstance(raw, (str, dict)):
            return [raw]
        return []

    def _normalize_setting_entry(self, raw: Any, default_category: Optional[str]) -> Optional[Dict[str, Any]]:
        if isinstance(raw, str):
            name = raw.strip()
            if not name:
                return None
            category = default_category or "rule"
            aliases: List[str] = []
            summary = ""
            entity_type = self._entity_type_for_setting(category)
            tier = "重要"
        elif isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("title") or raw.get("label") or "").strip()
            if not name:
                return None
            category = self._map_setting_category(raw.get("category") or raw.get("type") or raw.get("kind") or default_category)
            aliases = [str(item).strip() for item in raw.get("aliases", []) if str(item).strip()]
            mentions = [str(item).strip() for item in raw.get("mentions", []) if str(item).strip()]
            aliases.extend(item for item in mentions if item not in aliases)
            summary = str(raw.get("summary") or raw.get("description") or raw.get("desc") or raw.get("detail") or "").strip()
            entity_type = str(raw.get("entity_type") or self._entity_type_for_setting(category))
            tier = str(raw.get("tier") or "重要").strip() or "重要"
        else:
            return None

        entity_id = f"{category}-{self._slugify_setting_name(name)}"
        return {
            "id": entity_id,
            "name": name,
            "category": category,
            "aliases": aliases,
            "summary": summary,
            "entity_type": entity_type,
            "tier": tier,
        }

    def _map_setting_category(self, raw: Any) -> str:
        normalized = str(raw or "").strip().lower()
        if not normalized:
            return "rule"
        if any(token in normalized for token in ("faction", "organization", "institution", "agency", "bureau", "组织", "势力", "机构", "部门", "阵营")):
            return "faction"
        if any(token in normalized for token in ("location", "place", "site", "checkpoint", "point", "地点", "场所", "据点", "站点", "观察点")):
            return "location"
        return "rule"

    def _entity_type_for_setting(self, category: str) -> str:
        if category == "faction":
            return "势力"
        if category == "location":
            return "地点"
        return "规则"

    def _slugify_setting_name(self, name: str) -> str:
        normalized = re.sub(r"[^\w]+", "-", name.strip().lower(), flags=re.UNICODE).strip("-")
        return normalized or "setting"

    def _apply_normalized_setting(
        self,
        state_payload: Dict[str, Any],
        chapter: int,
        normalized: Dict[str, Any],
        structured_sync: Dict[str, Any],
        structured_names: Dict[str, List[str]],
    ) -> None:
        category = normalized["category"]
        name = normalized["name"]
        world_entry = {"name": name, "chapter": chapter}
        if normalized["summary"]:
            world_entry["summary"] = normalized["summary"]

        if category == "faction":
            world_entry["type"] = normalized["entity_type"]
            structured_sync["world_settings"]["factions"].append(world_entry)
            structured_names["factions"].append(name)
        elif category == "location":
            structured_sync["world_settings"]["locations"].append(world_entry)
            structured_names["locations"].append(name)
        else:
            world_entry["type"] = "rule"
            structured_sync["world_settings"]["power_system"].append(world_entry)
            structured_names["rules"].append(name)

        entity_record = {
            "id": normalized["id"],
            "name": name,
            "type": normalized["entity_type"],
            "tier": normalized["tier"],
            "summary": normalized["summary"],
            "aliases": normalized["aliases"],
            "current": {"category": category},
        }
        structured_sync["entities"].append(entity_record)
        if category in {"faction", "location"}:
            self._append_entity_payload(state_payload["entities_new"], entity_record)
        self._append_registry_state_change(state_payload["state_changes"], normalized)

    def _append_entity_payload(self, entities_new: List[Dict[str, Any]], entity_record: Dict[str, Any]) -> None:
        for candidate in entities_new:
            if str(candidate.get("suggested_id") or candidate.get("id") or "").strip() == entity_record["id"]:
                return
            if str(candidate.get("name") or "").strip() == entity_record["name"] and str(candidate.get("type") or "").strip() == entity_record["type"]:
                return
        mentions = [entity_record["name"], *entity_record.get("aliases", [])]
        entities_new.append(
            {
                "suggested_id": entity_record["id"],
                "name": entity_record["name"],
                "type": entity_record["type"],
                "tier": entity_record["tier"],
                "mentions": [item for item in mentions if item],
            }
        )

    def _append_registry_state_change(self, state_changes: List[Dict[str, Any]], normalized: Dict[str, Any]) -> None:
        field = "world_rule" if normalized["category"] == "rule" else "registry"
        new_value = normalized["summary"] or normalized["name"]
        for change in state_changes:
            if change.get("entity_id") == normalized["id"] and change.get("field") == field and change.get("new") == new_value:
                return
        state_changes.append(
            {
                "entity_id": normalized["id"],
                "field": field,
                "old": "",
                "new": new_value,
                "reason": f"introduced_{normalized['category']}",
            }
        )

    def _merge_world_settings(self, updates: Dict[str, List[Dict[str, Any]]]) -> None:
        def _mutate(state_data: Dict[str, Any]) -> None:
            world_settings = state_data.setdefault("world_settings", {"power_system": [], "factions": [], "locations": []})
            for category in ("power_system", "factions", "locations"):
                existing_items = world_settings.setdefault(category, [])
                if not isinstance(existing_items, list):
                    existing_items = []
                    world_settings[category] = existing_items
                existing_by_name = {
                    self._slugify_setting_name(str(item.get("name") or "")): item
                    for item in existing_items
                    if isinstance(item, dict) and str(item.get("name") or "").strip()
                }
                for item in updates.get(category, []):
                    item_name = str(item.get("name") or "").strip()
                    if not item_name:
                        continue
                    key = self._slugify_setting_name(item_name)
                    if key in existing_by_name:
                        existing_by_name[key].update(item)
                    else:
                        cloned = dict(item)
                        existing_items.append(cloned)
                        existing_by_name[key] = cloned

        self._update_state_data(_mutate)

    def _upsert_structured_entities(self, chapter: int, entities: List[Dict[str, Any]]) -> None:
        seen_ids: set[str] = set()
        for entity in entities:
            entity_id = str(entity.get("id") or "").strip()
            if not entity_id or entity_id in seen_ids:
                continue
            seen_ids.add(entity_id)
            self.index_manager.upsert_entity(
                EntityMeta(
                    id=entity_id,
                    type=str(entity.get("type") or "规则"),
                    canonical_name=str(entity.get("name") or entity_id),
                    tier=str(entity.get("tier") or "重要"),
                    desc=str(entity.get("summary") or ""),
                    current=dict(entity.get("current") or {}),
                    first_appearance=chapter,
                    last_appearance=chapter,
                ),
                update_metadata=True,
            )
            for alias in entity.get("aliases", []):
                alias_text = str(alias).strip()
                if alias_text:
                    self.index_manager.register_alias(alias_text, entity_id, str(entity.get("type") or "规则"))

    def _normalize_relationship_entries(
        self,
        chapter: int,
        raw_relationships: Any,
        entities: List[Dict[str, Any]],
        warnings: List[str],
    ) -> List[Dict[str, Any]]:
        known_entities: Dict[str, str] = {}
        for entity in entities:
            entity_id = str(entity.get("id") or "").strip()
            canonical_name = str(entity.get("name") or "").strip()
            if entity_id:
                known_entities[entity_id] = entity_id
            if canonical_name:
                known_entities[canonical_name] = entity_id or canonical_name
            for alias in entity.get("aliases", []):
                alias_text = str(alias).strip()
                if alias_text:
                    known_entities[alias_text] = entity_id or alias_text

        normalized_rows: List[Dict[str, Any]] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for item in self._coerce_setting_items(raw_relationships):
            if not isinstance(item, dict):
                warnings.append("unrecognized_relationship:raw")
                continue
            relation_type = str(item.get("type") or item.get("relationship") or item.get("relation") or "").strip()
            from_ref = str(item.get("from_entity") or item.get("from") or item.get("source") or "").strip()
            to_ref = str(item.get("to_entity") or item.get("to") or item.get("target") or "").strip()
            if not relation_type or not from_ref or not to_ref:
                warnings.append("unrecognized_relationship:missing_fields")
                continue
            from_entity = known_entities.get(from_ref, from_ref)
            to_entity = known_entities.get(to_ref, to_ref)
            dedupe_key = (from_entity, to_entity, relation_type)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            normalized_rows.append(
                {
                    "from_entity": from_entity,
                    "to_entity": to_entity,
                    "type": relation_type,
                    "description": str(item.get("description") or item.get("summary") or "").strip(),
                    "chapter": chapter,
                }
            )
        return normalized_rows

    def _upsert_structured_relationships(self, chapter: int, relationships: List[Dict[str, Any]]) -> None:
        for relationship in relationships:
            from_entity = str(relationship.get("from_entity") or "").strip()
            to_entity = str(relationship.get("to_entity") or "").strip()
            rel_type = str(relationship.get("type") or "").strip()
            if not from_entity or not to_entity or not rel_type:
                continue
            self.index_manager.upsert_relationship(
                RelationshipMeta(
                    from_entity=from_entity,
                    to_entity=to_entity,
                    type=rel_type,
                    description=str(relationship.get("description") or "").strip(),
                    chapter=int(relationship.get("chapter") or chapter),
                )
            )

    def _record_structured_sync_event(self, task_id: str, chapter: int, structured_sync: Dict[str, Any]) -> None:
        summary = structured_sync.get("summary") or {}
        if structured_sync.get("input_detected") and not summary.get("normalized_entries"):
            self.store.append_event(
                task_id,
                "warning",
                "Structured setting sync missing",
                step_name="data-sync",
                payload={"chapter": chapter, "warnings": structured_sync.get("warnings", [])},
            )
            return
        if summary.get("normalized_entries"):
            self.store.append_event(
                task_id,
                "info",
                "Structured settings synced",
                step_name="data-sync",
                payload={"chapter": chapter, **summary},
            )
            return
        self.store.append_event(
            task_id,
            "warning",
            "Structured setting sync missing",
            step_name="data-sync",
            payload={
                "chapter": chapter,
                "warnings": structured_sync.get("warnings", []),
                **summary,
            },
        )

    def _write_narrative_graph(self, narrative_sync: Dict[str, Any]) -> None:
        self.narrative_graph.write_batch(
            foreshadowing_items=narrative_sync.get("foreshadowing_items") or [],
            timeline_events=narrative_sync.get("timeline_events") or [],
            character_arcs=narrative_sync.get("character_arcs") or [],
            knowledge_states=narrative_sync.get("knowledge_states") or [],
        )

    def _record_narrative_sync_event(self, task_id: str, chapter: int, narrative_sync: Dict[str, Any]) -> None:
        summary = narrative_sync.get("summary") or {}
        if narrative_sync.get("input_detected") and not summary.get("normalized_entries"):
            self.store.append_event(
                task_id,
                "warning",
                "Narrative state sync missing",
                step_name="data-sync",
                payload={"chapter": chapter, "warnings": narrative_sync.get("warnings", [])},
            )
            return
        if summary.get("normalized_entries"):
            self.store.append_event(
                task_id,
                "info",
                "Narrative state synced",
                step_name="data-sync",
                payload={"chapter": chapter, **summary},
            )
            return

    def _build_story_alignment(
        self,
        story_plan: Dict[str, Any],
        payload: Dict[str, Any],
        content: str,
        chapter: int,
    ) -> Dict[str, List[str]]:
        alignment = {"satisfied": [], "missed": [], "deferred": []}
        if not isinstance(story_plan, dict) or not story_plan:
            return alignment

        slot = self._get_story_plan_slot(story_plan, chapter)
        text_evidence = "\n".join(
            [
                str(content or ""),
                json.dumps(payload.get("foreshadowing_items") or [], ensure_ascii=False),
                json.dumps(payload.get("timeline_events") or [], ensure_ascii=False),
                json.dumps(payload.get("knowledge_states") or [], ensure_ascii=False),
                json.dumps((payload.get("chapter_meta") or {}).get("characters") or [], ensure_ascii=False),
            ]
        ).casefold()

        def has_text(target: str) -> bool:
            normalized = str(target or "").strip().casefold()
            return bool(normalized) and normalized in text_evidence

        for target in self._normalize_director_text_list(slot.get("must_advance_threads")):
            if has_text(target):
                alignment["satisfied"].append(f"thread:{target}")
            else:
                alignment["missed"].append(f"thread:{target}")

        for target in self._normalize_director_text_list(slot.get("optional_payoffs")):
            if has_text(target):
                alignment["satisfied"].append(f"payoff:{target}")
            else:
                alignment["deferred"].append(f"payoff:{target}")

        for item in [row for row in (story_plan.get("payoff_schedule") or []) if isinstance(row, dict)]:
            target = str(item.get("thread") or "").strip()
            target_chapter = int(item.get("target_chapter") or 0)
            if not target:
                continue
            if target_chapter > chapter:
                alignment["deferred"].append(f"scheduled:{target}@{target_chapter}")
            elif has_text(target):
                alignment["satisfied"].append(f"scheduled:{target}@{target_chapter}")
            else:
                alignment["missed"].append(f"scheduled:{target}@{target_chapter}")

        for key in alignment:
            alignment[key] = self._normalize_director_text_list(alignment[key], limit=20)
        return alignment

    def _build_director_alignment(self, director_brief: Dict[str, Any], payload: Dict[str, Any], content: str) -> Dict[str, List[str]]:
        alignment = {"satisfied": [], "missed": [], "deferred": []}
        if not isinstance(director_brief, dict) or not director_brief:
            return alignment

        chapter_meta = dict(payload.get("chapter_meta") or {})
        payload_foreshadowing = [item for item in (payload.get("foreshadowing_items") or []) if isinstance(item, dict)]
        payload_timeline = [item for item in (payload.get("timeline_events") or []) if isinstance(item, dict)]
        payload_arcs = [item for item in (payload.get("character_arcs") or []) if isinstance(item, dict)]
        payload_knowledge = [item for item in (payload.get("knowledge_states") or []) if isinstance(item, dict)]
        payload_relationships = [item for item in (payload.get("relationships_new") or []) if isinstance(item, dict)]
        chapter_characters = self._normalize_characters(chapter_meta.get("characters"))

        text_evidence = "\n".join(
            [
                str(content or ""),
                json.dumps(payload_foreshadowing, ensure_ascii=False),
                json.dumps(payload_timeline, ensure_ascii=False),
                json.dumps(payload_arcs, ensure_ascii=False),
                json.dumps(payload_knowledge, ensure_ascii=False),
                json.dumps(payload_relationships, ensure_ascii=False),
                json.dumps(chapter_characters, ensure_ascii=False),
            ]
        ).casefold()

        def has_text(target: str) -> bool:
            normalized = str(target or "").strip().casefold()
            return bool(normalized) and normalized in text_evidence

        foreshadowing_by_name = {
            str(item.get("name") or "").strip().casefold(): item
            for item in payload_foreshadowing
            if str(item.get("name") or "").strip()
        }

        for target in self._normalize_director_text_list(director_brief.get("payoff_targets")):
            matched = foreshadowing_by_name.get(target.casefold())
            if matched and str(matched.get("status") or "").strip().casefold() in {"paid_off", "resolved", "fulfilled"}:
                alignment["satisfied"].append(f"payoff:{target}")
            elif matched:
                alignment["deferred"].append(f"payoff:{target}")
            else:
                alignment["missed"].append(f"payoff:{target}")

        for target in self._normalize_director_text_list(director_brief.get("setup_targets")):
            if has_text(target):
                alignment["satisfied"].append(f"setup:{target}")
            else:
                alignment["missed"].append(f"setup:{target}")

        for target in self._normalize_director_text_list(director_brief.get("must_advance_threads")):
            if has_text(target):
                alignment["satisfied"].append(f"thread:{target}")
            else:
                alignment["missed"].append(f"thread:{target}")

        for target in self._normalize_director_text_list(director_brief.get("must_use_entities")):
            if has_text(target):
                alignment["satisfied"].append(f"entity:{target}")
            else:
                alignment["missed"].append(f"entity:{target}")

        for target in self._normalize_director_text_list(director_brief.get("relationship_moves")):
            if has_text(target):
                alignment["satisfied"].append(f"relationship:{target}")
            else:
                alignment["missed"].append(f"relationship:{target}")

        for target in self._normalize_director_text_list(director_brief.get("knowledge_reveals")):
            if has_text(target):
                alignment["satisfied"].append(f"knowledge:{target}")
            else:
                alignment["missed"].append(f"knowledge:{target}")

        for key in alignment:
            alignment[key] = self._normalize_director_text_list(alignment[key], limit=20)
        return alignment

    async def _sync_core_setting_docs(
        self,
        *,
        task_id: str,
        trigger: str,
        chapter: Optional[int],
        plan_payload: Optional[Dict[str, Any]],
        state_payload: Optional[Dict[str, Any]],
        structured_sync: Optional[Dict[str, Any]],
    ) -> None:
        state_data = await asyncio.to_thread(self._read_state_data)
        sync_input = await asyncio.to_thread(
            self._build_setting_sync_input,
            state_data=state_data,
            trigger=trigger,
            chapter=chapter,
            plan_payload=plan_payload,
            state_payload=state_payload,
            structured_sync=structured_sync,
        )
        generated = await asyncio.to_thread(self._generate_setting_docs, sync_input)
        changed_paths: List[str] = []
        for key, path in SETTING_DOC_PATHS.items():
            content = str(generated.get(key) or "").strip()
            if not content:
                continue
            resolved = self._resolve_project_path(path)
            existing = resolved.read_text(encoding="utf-8") if resolved.is_file() else ""
            merged = self._merge_setting_doc_content(existing, content)
            if existing.strip() == merged.strip():
                continue
            self._write_project_text(path, merged if merged.endswith("\n") else merged + "\n")
            changed_paths.append(path)
        if changed_paths:
            self.store.append_event(
                task_id,
                "info",
                "Core setting docs synced",
                step_name="data-sync" if trigger == "write" else "plan",
                payload={"trigger": trigger, "files": changed_paths, "chapter": chapter},
            )

    def _build_setting_sync_input(
        self,
        *,
        state_data: Dict[str, Any],
        trigger: str,
        chapter: Optional[int],
        plan_payload: Optional[Dict[str, Any]],
        state_payload: Optional[Dict[str, Any]],
        structured_sync: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        project_info = dict(state_data.get("project_info") or {})
        protagonist_state = dict(state_data.get("protagonist_state") or {})
        golden_finger = dict(protagonist_state.get("golden_finger") or {})
        planning = state_data.get("planning") or {}
        profile = dict(planning.get("profile") or {})
        readiness = dict(planning.get("readiness") or {})
        world_settings = dict(state_data.get("world_settings") or {})
        chapter_meta = self._get_state_chapter_meta(state_data, chapter or 0) if chapter else {}
        chapters = self.index_manager.get_recent_chapters(limit=20)
        review_metrics = self.index_manager.get_recent_review_metrics(limit=20)
        return {
            "trigger": trigger,
            "chapter": chapter,
            "project_info": project_info,
            "protagonist_state": protagonist_state,
            "golden_finger": golden_finger,
            "planning_profile": profile,
            "planning_readiness": readiness,
            "world_settings": world_settings,
            "chapter_meta": chapter_meta,
            "chapter_rows": chapters,
            "review_metrics": review_metrics,
            "plan_payload": plan_payload or {},
            "state_payload": state_payload or {},
            "structured_sync": structured_sync or {},
        }

    def _generate_setting_docs(self, sync_input: Dict[str, Any]) -> Dict[str, str]:
        if self._should_use_llm_for_setting_docs():
            generated = self._generate_setting_docs_with_llm(sync_input)
            if generated:
                return generated
        return self._generate_setting_docs_deterministically(sync_input)

    def _should_use_llm_for_setting_docs(self) -> bool:
        mode = str(getattr(self.runner, "mode", "") or "").strip().lower()
        provider = str(getattr(self.runner, "provider", "") or "").strip().lower()
        return mode == "api" or provider in {"openai-compatible", "openai", "azure-openai"}

    def _generate_setting_docs_with_llm(self, sync_input: Dict[str, Any]) -> Dict[str, str]:
        step_spec = {
            "name": "setting-docs-sync",
            "instructions": (
                "根据输入中的项目状态、卷规划和章节结构化结果，输出 4 份中文 Markdown 文档。"
                "必须分别覆盖：世界观、力量体系、主角卡、金手指设计。"
                "每份文档都要按固定小标题组织，缺失信息请明确写“待补充”，不要输出空壳模板。"
                "输出 JSON，不要附加解释。"
            ),
            "required_output_keys": ["worldview", "power_system", "protagonist", "golden_finger"],
            "output_schema": {
                "worldview": "string",
                "power_system": "string",
                "protagonist": "string",
                "golden_finger": "string",
            },
        }
        prompt_bundle = {
            "task_id": f"settings-sync-{sync_input.get('trigger')}-{sync_input.get('chapter') or 'base'}",
            "input": sync_input,
            "reference_documents": [],
            "project_context": [
                {
                    "path": path,
                    "content": self._resolve_project_path(path).read_text(encoding="utf-8")
                    if self._resolve_project_path(path).is_file()
                    else "",
                }
                for path in SETTING_DOC_PATHS.values()
            ],
        }
        try:
            result = self.runner.run(step_spec, self.project_root, prompt_bundle)
        except Exception as exc:
            logger.warning("setting doc llm sync failed: %s", exc)
            return {}
        if not result.success or not isinstance(result.structured_output, dict):
            return {}
        return {
            "worldview": str(result.structured_output.get("worldview") or "").strip(),
            "power_system": str(result.structured_output.get("power_system") or "").strip(),
            "protagonist": str(result.structured_output.get("protagonist") or "").strip(),
            "golden_finger": str(result.structured_output.get("golden_finger") or "").strip(),
        }

    def _generate_setting_docs_deterministically(self, sync_input: Dict[str, Any]) -> Dict[str, str]:
        project = sync_input.get("project_info") or {}
        profile = sync_input.get("planning_profile") or {}
        protagonist_state = sync_input.get("protagonist_state") or {}
        golden_finger = sync_input.get("golden_finger") or {}
        world_settings = sync_input.get("world_settings") or {}
        plan_payload = sync_input.get("plan_payload") or {}
        chapter_meta = sync_input.get("chapter_meta") or {}
        structured_sync = sync_input.get("structured_sync") or {}
        chapter_rows = sync_input.get("chapter_rows") or []
        review_metrics = sync_input.get("review_metrics") or []

        worldview_lines = [
            "# 世界观",
            "",
            "## 项目概览",
            f"- 书名：{project.get('title') or '待补充'}",
            f"- 题材：{project.get('genre') or '待补充'}",
            f"- 世界规模：{project.get('world_scale') or '待补充'}",
            f"- 核心卖点：{project.get('core_selling_points') or '待补充'}",
            "",
            "## 城市与异常环境",
            self._bullet_block(world_settings.get("locations"), empty_text="待补充"),
            "",
            "## 势力与规则",
            self._bullet_block(world_settings.get("factions"), empty_text="待补充"),
            "",
            "## 卷规划沉淀",
            f"- 最新卷：{((sync_input.get('planning_profile') or {}).get('volume_1_title') or ((plan_payload.get('volume_plan') or {}).get('title')) or '待补充')}",
            f"- 卷冲突：{profile.get('volume_1_conflict') or self._summarize_volume_plan(plan_payload) or '待补充'}",
            f"- 卷高潮：{profile.get('volume_1_climax') or '待补充'}",
        ]

        power_lines = [
            "# 力量体系",
            "",
            "## 能力主轴",
            f"- 体系类型：{project.get('power_system_type') or '待补充'}",
            f"- 金手指：{golden_finger.get('name') or project.get('golden_finger_name') or '待补充'}",
            f"- 类型：{project.get('golden_finger_type') or '待补充'}",
            "",
            "## 规则与代价",
            f"- 公开可见度：{project.get('gf_visibility') or '待补充'}",
            f"- 不可逆代价：{project.get('gf_irreversible_cost') or '待补充'}",
            f"- 风格定位：{project.get('golden_finger_style') or '待补充'}",
            "",
            "## 已沉淀规则",
            self._bullet_block(world_settings.get("power_system"), empty_text="待补充"),
        ]

        protagonist_lines = [
            "# 主角卡",
            "",
            "## 基础信息",
            f"- 姓名：{protagonist_state.get('name') or profile.get('protagonist_name') or '待补充'}",
            f"- 身份：{profile.get('protagonist_identity') or '待补充'}",
            f"- 初始状态：{profile.get('protagonist_initial_state') or '待补充'}",
            "",
            "## 动机与缺陷",
            f"- 欲望：{profile.get('protagonist_desire') or project.get('protagonist_desire') or '待补充'}",
            f"- 缺陷：{profile.get('protagonist_flaw') or '待补充'}",
            f"- 原型：{profile.get('protagonist_archetype') or '待补充'}",
            "",
            "## 近期章节体现",
            self._render_recent_chapter_notes(chapter_rows, review_metrics, chapter_meta),
        ]

        gf_lines = [
            "# 金手指设计",
            "",
            "## 核心定义",
            f"- 名称：{golden_finger.get('name') or project.get('golden_finger_name') or '待补充'}",
            f"- 类型：{project.get('golden_finger_type') or '待补充'}",
            f"- 当前等级：{golden_finger.get('level') if golden_finger.get('level') is not None else '待补充'}",
            "",
            "## 触发与限制",
            f"- 冷却：{golden_finger.get('cooldown') if golden_finger.get('cooldown') is not None else '待补充'}",
            f"- 技能清单：{self._inline_join(golden_finger.get('skills')) or '待补充'}",
            f"- 不可逆代价：{project.get('gf_irreversible_cost') or '待补充'}",
            "",
            "## 最近结构化补充",
            self._render_structured_sync_notes(structured_sync),
        ]

        return {
            "worldview": "\n".join(worldview_lines).strip(),
            "power_system": "\n".join(power_lines).strip(),
            "protagonist": "\n".join(protagonist_lines).strip(),
            "golden_finger": "\n".join(gf_lines).strip(),
        }

    def _merge_setting_doc_content(self, existing: str, generated: str) -> str:
        existing_text = str(existing or "").strip()
        generated_text = str(generated or "").strip()
        if not existing_text:
            return generated_text
        if self._looks_like_template_doc(existing_text):
            return generated_text
        existing_sections = self._split_markdown_sections(existing_text)
        generated_sections = self._split_markdown_sections(generated_text)
        if not existing_sections or not generated_sections:
            return generated_text
        title, body = generated_sections[0]
        merged: List[str] = [f"{title}\n{body}".strip()]
        existing_map = {title: body for title, body in existing_sections[1:]}
        generated_titles = {title for title, _ in generated_sections[1:]}
        for title, body in generated_sections[1:]:
            merged.append(f"## {title}\n{body}".strip())
        for title, body in existing_sections[1:]:
            if title not in generated_titles and body.strip():
                merged.append(f"## {title}\n{body}".strip())
        return "\n\n".join(block.strip() for block in merged if block.strip())

    def _looks_like_template_doc(self, content: str) -> bool:
        normalized = content.strip()
        if not normalized:
            return True
        template_signals = ("待补充", "（待填写）", "（待补）", "暂无内容", "TODO")
        section_count = normalized.count("## ")
        signal_count = sum(normalized.count(token) for token in template_signals)
        return section_count > 0 and signal_count >= max(2, section_count // 2)

    def _split_markdown_sections(self, text: str) -> List[tuple[str, str]]:
        stripped = text.strip()
        if not stripped:
            return []
        parts = re.split(r"^##\s+", stripped, flags=re.MULTILINE)
        sections: List[tuple[str, str]] = []
        title_line, _, body = parts[0].partition("\n")
        sections.append((title_line.strip(), body.strip()))
        for part in parts[1:]:
            title, _, section_body = part.partition("\n")
            sections.append((title.strip(), section_body.strip()))
        return sections

    def _bullet_block(self, items: Any, *, empty_text: str) -> str:
        normalized_items: List[str] = []
        for item in items or []:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                summary = str(item.get("summary") or "").strip()
                if name and summary:
                    normalized_items.append(f"- {name}：{summary}")
                elif name:
                    normalized_items.append(f"- {name}")
            elif str(item).strip():
                normalized_items.append(f"- {str(item).strip()}")
        return "\n".join(normalized_items) if normalized_items else f"- {empty_text}"

    def _inline_join(self, items: Any) -> str:
        if not isinstance(items, list):
            return ""
        values = [str(item).strip() for item in items if str(item).strip()]
        return "；".join(values)

    def _render_recent_chapter_notes(
        self,
        chapter_rows: List[Dict[str, Any]],
        review_metrics: List[Dict[str, Any]],
        chapter_meta: Dict[str, Any],
    ) -> str:
        blocks: List[str] = []
        if chapter_meta:
            title = str(chapter_meta.get("title") or "").strip() or "当前章节"
            location = str(chapter_meta.get("location") or "").strip() or "待补充"
            characters = self._inline_join(chapter_meta.get("characters")) or "待补充"
            blocks.append(f"- 最近章节标题：{title}")
            blocks.append(f"- 最近章节地点：{location}")
            blocks.append(f"- 最近涉及角色：{characters}")
        if chapter_rows:
            latest = chapter_rows[0]
            blocks.append(f"- 当前最新章节：第{latest.get('chapter')}章，标题《{latest.get('title') or '未命名'}》")
        if review_metrics:
            latest_metric = review_metrics[0]
            blocks.append(f"- 最近审查分：{latest_metric.get('overall_score') or 0}")
        return "\n".join(blocks) if blocks else "- 待补充"

    def _render_structured_sync_notes(self, structured_sync: Dict[str, Any]) -> str:
        if not structured_sync:
            return "- 待补充"
        summary = structured_sync.get("summary") or {}
        warnings = structured_sync.get("warnings") or []
        lines = [
            f"- 结构化实体：{summary.get('entity_records') or 0}",
            f"- 结构化关系：{summary.get('relationship_records') or 0}",
            f"- 世界设定项：{summary.get('world_setting_records') or 0}",
        ]
        if warnings:
            lines.append(f"- 待确认项：{'；'.join(str(item) for item in warnings[:5])}")
        return "\n".join(lines)

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













