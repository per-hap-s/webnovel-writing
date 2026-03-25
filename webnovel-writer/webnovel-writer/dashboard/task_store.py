from __future__ import annotations

import json
from heapq import nlargest
import logging
import os
import tempfile
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

from filelock import FileLock, Timeout


logger = logging.getLogger(__name__)

FILE_LOCK_TIMEOUT = 30


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _parse_sort_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        return datetime.min.replace(tzinfo=timezone.utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        return parsed.replace(tzinfo=local_tz).astimezone(timezone.utc)
    return parsed.astimezone(timezone.utc)


class TaskStore:
    """Persist orchestration tasks under .webnovel/observability for resumable UI state."""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root).resolve()
        self.base_dir = self.project_root / ".webnovel" / "observability" / "task-runs"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._locks_dir = self.base_dir / ".locks"
        self._locks_dir.mkdir(parents=True, exist_ok=True)
        self._active_locks: Dict[str, Dict[str, Any]] = {}
        self._locks_monitor_lock = threading.Lock()
        
    def _register_lock_acquire(self, lock_key: str, lock_path: Path) -> None:
        """
        注册锁获取事件，用于泄漏检测
        
        Args:
            lock_key: 锁的唯一标识符
            lock_path: 锁文件路径
        """
        with self._locks_monitor_lock:
            self._active_locks[lock_key] = {
                "path": str(lock_path),
                "acquired_at": time.time(),
                "thread_id": threading.get_ident(),
                "process_id": os.getpid(),
            }
            logger.debug("锁注册成功，锁标识: %s，线程: %d", lock_key, threading.get_ident())
            
    def _register_lock_release(self, lock_key: str) -> None:
        """
        注册锁释放事件
        
        Args:
            lock_key: 锁的唯一标识符
        """
        with self._locks_monitor_lock:
            if lock_key in self._active_locks:
                hold_time = time.time() - self._active_locks[lock_key]["acquired_at"]
                del self._active_locks[lock_key]
                logger.debug("锁释放注册成功，锁标识: %s，持有时间: %.2f秒", lock_key, hold_time)
                
    def check_lock_health(self) -> Dict[str, Any]:
        """
        检查锁健康状态，检测潜在的锁泄漏
        
        Returns:
            包含健康检查结果的字典：
            - healthy: 是否健康
            - active_locks_count: 当前活跃锁数量
            - stale_locks: 可能泄漏的锁列表
            - details: 详细信息
        """
        current_time = time.time()
        stale_threshold = FILE_LOCK_TIMEOUT * 2
        stale_locks = []
        
        with self._locks_monitor_lock:
            for lock_key, lock_info in self._active_locks.items():
                hold_time = current_time - lock_info["acquired_at"]
                if hold_time > stale_threshold:
                    stale_locks.append({
                        "lock_key": lock_key,
                        "hold_time": hold_time,
                        **lock_info,
                    })
                    
            active_locks_count = len(self._active_locks)
            
        is_healthy = len(stale_locks) == 0
        
        if stale_locks:
            logger.warning(
                "检测到潜在锁泄漏，数量: %d，详情: %s",
                len(stale_locks),
                [{"lock_key": l["lock_key"], "hold_time": f"{l['hold_time']:.2f}s"} for l in stale_locks]
            )
            
        return {
            "healthy": is_healthy,
            "active_locks_count": active_locks_count,
            "stale_locks": stale_locks,
            "stale_threshold_seconds": stale_threshold,
        }
        
    def cleanup_stale_locks(self) -> int:
        """
        清理过期的锁文件
        
        Returns:
            清理的锁文件数量
        """
        cleaned = 0
        current_time = time.time()
        stale_threshold = FILE_LOCK_TIMEOUT * 3
        
        try:
            for lock_file in self._locks_dir.glob("*.lock"):
                try:
                    stat = lock_file.stat()
                    file_age = current_time - stat.st_mtime
                    
                    if file_age > stale_threshold:
                        lock_file.unlink()
                        cleaned += 1
                        logger.info("清理过期锁文件: %s，文件年龄: %.2f秒", lock_file, file_age)
                except FileNotFoundError:
                    pass
                except Exception as e:
                    logger.warning("清理锁文件失败: %s，错误: %s", lock_file, e)
                    
        except Exception as e:
            logger.error("锁文件清理过程出错: %s", e)
            
        return cleaned

    def create_task(self, task_type: str, request: Dict[str, Any], workflow: Dict[str, Any]) -> Dict[str, Any]:
        task_id = uuid.uuid4().hex
        task = {
            "id": task_id,
            "task_type": task_type,
            "workflow_name": workflow.get("name", task_type),
            "workflow_version": workflow.get("version", 1),
            "status": "queued",
            "approval_status": "not_required",
            "current_step": None,
            "request": request,
            "project_root": str(self.project_root),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "interrupted_at": None,
            "recovered_at": None,
            "parent_task_id": None,
            "parent_step_name": None,
            "root_task_id": None,
            "trigger_source": None,
            "resume_target_task_id": None,
            "resume_from_step": None,
            "resume_reason": None,
            "error": None,
            "step_order": [step["name"] for step in workflow.get("steps", [])],
            "workflow_spec": workflow,
            "artifacts": {
                "step_results": {},
                "review_summary": None,
                "approval": {},
            },
            "runtime_meta": {
                "last_event": None,
                "last_non_heartbeat_event": None,
            },
        }
        self._write_task(task)
        self.append_event(task_id, "info", f"任务已加入队列: {task_type}")
        return task

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        列出所有任务
        
        返回按创建时间倒序排列的任务列表。
        解析失败的文件会被跳过并记录警告日志。
        """
        if limit <= 0:
            return []

        def _iter_tasks() -> Iterator[tuple[Dict[str, Any], int]]:
            for path in self.base_dir.glob("*.json"):
                try:
                    yield json.loads(path.read_text(encoding="utf-8")), path.stat().st_mtime_ns
                except json.JSONDecodeError as e:
                    logger.warning("任务文件 JSON 解析失败，文件: %s，错误: %s", str(path), e)
                    continue

        ranked = nlargest(
            limit,
            _iter_tasks(),
            key=lambda entry: (_parse_sort_datetime(entry[0].get("created_at")), entry[1]),
        )
        return [item for item, _ in ranked]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定任务
        
        如果任务不存在或 JSON 解析失败，返回 None。
        解析失败时会记录警告日志。
        """
        path = self._task_path(task_id)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning("任务文件 JSON 解析失败，任务ID: %s，错误: %s", task_id, e)
            return None

    def update_task(self, task_id: str, **updates: Any) -> Dict[str, Any]:
        def _mutate(task: Dict[str, Any]) -> None:
            task.update(updates)
            task["updated_at"] = _now_iso()
        return self._mutate_task(task_id, _mutate)

    def save_step_result(self, task_id: str, step_name: str, result: Dict[str, Any]) -> Dict[str, Any]:
        def _mutate(task: Dict[str, Any]) -> None:
            artifacts = task.setdefault("artifacts", {})
            step_results = artifacts.setdefault("step_results", {})
            step_results[step_name] = result
            task["updated_at"] = _now_iso()
        return self._mutate_task(task_id, _mutate)

    def append_event(
        self,
        task_id: str,
        level: str,
        message: str,
        *,
        step_name: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        追加事件到任务事件日志
        
        使用文件锁确保跨进程/线程的并发安全。
        支持原子追加操作，避免事件丢失或损坏。
        
        Args:
            task_id: 任务ID
            level: 日志级别（info/warning/error）
            message: 事件消息
            step_name: 可选的步骤名称
            payload: 可选的事件载荷
            
        Returns:
            创建的事件字典
            
        Raises:
            Timeout: 文件锁获取超时
        """
        event = {
            "id": uuid.uuid4().hex,
            "task_id": task_id,
            "level": level,
            "message": message,
            "step_name": step_name,
            "payload": payload or {},
            "timestamp": _now_iso(),
        }
        path = self._events_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        lock_path = self._locks_dir / f"{task_id}.events.lock"
        file_lock = FileLock(lock_path)
        lock_key = f"events:{task_id}:{threading.get_ident()}"
        
        lock_acquired = False
        try:
            logger.debug("尝试获取事件文件锁，任务ID: %s，锁路径: %s", task_id, lock_path)
            file_lock.acquire(timeout=FILE_LOCK_TIMEOUT)
            lock_acquired = True
            self._register_lock_acquire(lock_key, lock_path)
            logger.debug("事件文件锁获取成功，任务ID: %s", task_id)
            
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            logger.debug("事件追加成功，任务ID: %s，事件ID: %s", task_id, event["id"])
            
        except Timeout:
            logger.error(
                "事件文件锁获取超时，任务ID: %s，锁路径: %s，超时时间: %d秒",
                task_id, lock_path, FILE_LOCK_TIMEOUT
            )
            raise
        except Exception as e:
            logger.error(
                "事件追加失败，任务ID: %s，错误类型: %s，错误信息: %s\n调用栈:\n%s",
                task_id, type(e).__name__, str(e), traceback.format_exc()
            )
            raise
        finally:
            if lock_acquired:
                try:
                    file_lock.release()
                    self._register_lock_release(lock_key)
                    logger.debug("事件文件锁释放成功，任务ID: %s", task_id)
                except Exception as e:
                    logger.warning("事件文件锁释放失败，任务ID: %s，错误: %s", task_id, e)

        self._record_runtime_event(task_id, event)
        
        return event

    def get_events(self, task_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """
        获取任务事件列表
        
        返回按时间顺序排列的事件列表。
        解析失败的行会被跳过并记录警告日志。
        """
        path = self._events_path(task_id)
        if not path.is_file():
            return []
        rows: List[Dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.warning("事件日志 JSON 解析失败，任务ID: %s，错误: %s", task_id, e)
                continue
        return rows[-limit:]

    def mark_running(self, task_id: str, step_name: Optional[str]) -> Dict[str, Any]:
        def _mutate(task: Dict[str, Any]) -> None:
            task["status"] = "running"
            task["current_step"] = step_name
            task["started_at"] = task.get("started_at") or _now_iso()
            task["error"] = None
            task["updated_at"] = _now_iso()
        return self._mutate_task(task_id, _mutate)

    def mark_waiting_for_approval(
        self,
        task_id: str,
        step_name: str,
        approval: Dict[str, Any],
        *,
        status: str = "awaiting_writeback_approval",
        approval_kind: str = "writeback",
    ) -> Dict[str, Any]:
        def _mutate(task: Dict[str, Any]) -> None:
            artifacts = task.setdefault("artifacts", {})
            approval_artifacts = dict(artifacts.get("approval") or {})
            approval_record = {
                **approval,
                "kind": approval_kind,
                "status": str(approval.get("status") or "pending"),
            }
            for key, value in approval_record.items():
                if key == "current":
                    continue
                approval_artifacts[key] = value
            approval_artifacts["current"] = approval_record
            approval_artifacts[approval_kind] = approval_record
            artifacts["approval"] = approval_artifacts
            task["status"] = status
            task["approval_status"] = "pending"
            task["current_step"] = step_name
            task["updated_at"] = _now_iso()
        return self._mutate_task(task_id, _mutate)

    def mark_completed(self, task_id: str) -> Dict[str, Any]:
        return self.update_task(
            task_id,
            status="completed",
            current_step=None,
            finished_at=_now_iso(),
            error=None,
        )

    def mark_failed(self, task_id: str, step_name: Optional[str], error: Dict[str, Any]) -> Dict[str, Any]:
        return self.update_task(
            task_id,
            status="failed",
            current_step=step_name,
            finished_at=_now_iso(),
            error=error,
        )

    def mark_interrupted(self, task_id: str, step_name: Optional[str], reason: str) -> Dict[str, Any]:
        return self.update_task(
            task_id,
            status="interrupted",
            current_step=step_name,
            interrupted_at=_now_iso(),
            finished_at=None,
            error={"code": "TASK_INTERRUPTED", "message": reason, "retryable": True},
        )

    def mark_cancelled(self, task_id: str, step_name: Optional[str], reason: str) -> Dict[str, Any]:
        return self.update_task(
            task_id,
            status="interrupted",
            current_step=step_name,
            interrupted_at=_now_iso(),
            finished_at=_now_iso(),
            error={"code": "TASK_CANCELLED", "message": reason, "retryable": False},
        )

    def mark_rejected(self, task_id: str, reason: str, *, error_code: str = "WRITEBACK_REJECTED") -> Dict[str, Any]:
        return self.update_task(
            task_id,
            status="rejected",
            current_step=None,
            finished_at=_now_iso(),
            approval_status="rejected",
            error={"code": error_code, "message": reason},
        )

    def reset_for_retry(self, task_id: str, *, preserve_approval: bool = False) -> Dict[str, Any]:
        def _mutate(task: Dict[str, Any]) -> None:
            failed_step = task.get("current_step")
            artifacts = task.setdefault("artifacts", {})
            step_results = artifacts.setdefault("step_results", {})
            if failed_step:
                step_results.pop(failed_step, None)
            if not preserve_approval:
                artifacts["approval"] = {}
            task["status"] = "retrying"
            if not preserve_approval:
                task["approval_status"] = "not_required"
            task["current_step"] = None
            task["finished_at"] = None
            task["error"] = None
            task["updated_at"] = _now_iso()
        return self._mutate_task(task_id, _mutate)

    def prepare_for_resume(self, task_id: str, *, resume_from_step: Optional[str], reason: str) -> Dict[str, Any]:
        def _mutate(task: Dict[str, Any]) -> None:
            task["status"] = "queued"
            task["current_step"] = resume_from_step
            task["finished_at"] = None
            task["error"] = None
            task["recovered_at"] = _now_iso()
            task["resume_from_step"] = resume_from_step
            task["resume_reason"] = reason
            task["updated_at"] = _now_iso()
        return self._mutate_task(task_id, _mutate)

    def mark_stale_running_tasks(self, active_task_ids: Optional[set[str]] = None) -> int:
        active = active_task_ids or set()
        updated = 0
        for task in self.list_tasks(limit=1000):
            task_id = task.get("id")
            if not task_id or task.get("status") != "running" or task_id in active:
                continue
            current_step = task.get("current_step")
            self.mark_interrupted(task_id, current_step, "服务重启前任务未完成，已中断，可从当前步骤继续处理。")
            self.append_event(
                task_id,
                "warning",
                "服务重启后检测到未完成任务，已标记为中断",
                step_name=current_step,
                payload={"resume_hint": current_step},
            )
            updated += 1
        return updated

    def _task_path(self, task_id: str) -> Path:
        return self.base_dir / f"{task_id}.json"

    def _events_path(self, task_id: str) -> Path:
        return self.base_dir / f"{task_id}.events.jsonl"

    def _record_runtime_event(self, task_id: str, event: Dict[str, Any]) -> None:
        def _mutate(task: Dict[str, Any]) -> None:
            runtime_meta = task.setdefault("runtime_meta", {})
            runtime_meta["last_event"] = self._compact_runtime_event(event)
            if str(event.get("message") or "") != "step_heartbeat":
                runtime_meta["last_non_heartbeat_event"] = self._compact_runtime_event(event)
                task["updated_at"] = str(event.get("timestamp") or _now_iso())
        try:
            self._mutate_task(task_id, _mutate)
        except KeyError:
            return

    def _mutate_task(self, task_id: str, mutator: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
        with self._lock:
            def _apply(path: Path) -> Dict[str, Any]:
                task = self._read_task_file(path)
                if task is None:
                    raise KeyError(task_id)
                mutator(task)
                self._write_task_file(path, task)
                return task

            return self._with_task_file_lock(task_id, _apply)

    def _read_task_file(self, path: Path) -> Optional[Dict[str, Any]]:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.warning("任务文件 JSON 解析失败，文件: %s，错误: %s", path, e)
            return None

    def _with_task_file_lock(self, task_id: str, callback: Callable[[Path], Any]) -> Any:
        path = self._task_path(task_id)
        lock_path = self._locks_dir / f"{task_id}.lock"
        file_lock = FileLock(lock_path)
        lock_key = f"task:{task_id}:{threading.get_ident()}"
        lock_acquired = False
        try:
            logger.debug("尝试获取文件锁，任务ID: %s，锁路径: %s", task_id, lock_path)
            file_lock.acquire(timeout=FILE_LOCK_TIMEOUT)
            lock_acquired = True
            self._register_lock_acquire(lock_key, lock_path)
            logger.debug("文件锁获取成功，任务ID: %s", task_id)
            return callback(path)
        except Timeout:
            logger.error(
                "文件锁获取超时，任务ID: %s，锁路径: %s，超时时间: %d秒",
                task_id, lock_path, FILE_LOCK_TIMEOUT
            )
            raise
        finally:
            if lock_acquired:
                try:
                    file_lock.release()
                    self._register_lock_release(lock_key)
                    logger.debug("文件锁释放成功，任务ID: %s", task_id)
                except Exception as e:
                    logger.warning("文件锁释放失败，任务ID: %s，错误: %s", task_id, e)

    def _write_task_file(self, path: Path, task: Dict[str, Any]) -> None:
        tmp_suffix = f".tmp.{os.getpid()}.{threading.get_ident()}"
        tmp_path = path.with_suffix(f".json{tmp_suffix}")
        try:
            json_content = json.dumps(task, ensure_ascii=False, indent=2)
            tmp_path.write_text(json_content, encoding="utf-8")
            logger.debug("临时文件写入成功，路径: %s，大小: %d 字节", tmp_path, len(json_content))
            os.replace(str(tmp_path), str(path))
            logger.debug("原子替换完成，任务ID: %s，最终路径: %s", task.get("id"), path)
        except Exception as e:
            logger.error(
                "任务写入失败，任务ID: %s，错误类型: %s，错误信息: %s\n调用栈:\n%s",
                task.get("id"), type(e).__name__, str(e), traceback.format_exc()
            )
            raise
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                    logger.debug("清理临时文件成功，路径: %s", tmp_path)
                except Exception as e:
                    logger.warning("清理临时文件失败，路径: %s，错误: %s", tmp_path, e)

    def _compact_runtime_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        payload = event.get("payload") or {}
        compact_payload = {
            key: payload.get(key)
            for key in (
                "attempt",
                "retry_count",
                "timeout_seconds",
                "retryable",
                "error_code",
                "http_status",
                "next_step",
                "resume_from_step",
            )
            if payload.get(key) is not None
        }
        return {
            "id": event.get("id"),
            "level": event.get("level"),
            "message": event.get("message"),
            "step_name": event.get("step_name"),
            "timestamp": event.get("timestamp"),
            "payload": compact_payload,
        }

    def _write_task(self, task: Dict[str, Any]) -> None:
        """
        原子写入任务数据到文件
        
        使用文件锁确保跨进程/线程的并发安全：
        1. 获取文件锁（阻塞等待，超时30秒）
        2. 写入临时文件
        3. 使用 os.replace 进行原子替换
        4. 释放文件锁
        
        临时文件命名格式：<task_id>.json.tmp.<pid>.<thread_id>
        
        Raises:
            Timeout: 文件锁获取超时
            IOError: 文件写入失败
        """
        task_id = task["id"]
        self._with_task_file_lock(task_id, lambda path: self._write_task_file(path, task))


