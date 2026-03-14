#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
State Manager - 状态管理模块 (v5.4)

管理 state.json 的读写操作：
- 实体状态管理
- 进度追踪
- 关系记录

v5.1 变更（v5.4 沿用）:
- 集成 SQLStateManager，同步写入 SQLite (index.db)
- state.json 保留精简数据，大数据自动迁移到 SQLite
"""

import json
import logging
import sqlite3
import sys
import time
from copy import deepcopy

from runtime_compat import enable_windows_utf8_stdio
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
import filelock

from .config import get_config
from .observability import safe_append_perf_timing, safe_log_tool_call
from .retry_utils import SyncStatus, retry_sync_safe


logger = logging.getLogger(__name__)

try:
    # 当 scripts 目录在 sys.path 中（常见：从 scripts/ 运行）
    from security_utils import atomic_write_json, read_json_safe
except ImportError:  # pragma: no cover
    # 当以 `python -m scripts.data_modules...` 从仓库根目录运行
    from scripts.security_utils import atomic_write_json, read_json_safe


@dataclass
class EntityState:
    """实体状态"""
    id: str
    name: str
    type: str  # 角色/地点/物品/势力
    tier: str = "装饰"  # 核心/重要/次要/装饰
    aliases: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    first_appearance: int = 0
    last_appearance: int = 0


@dataclass
class Relationship:
    """实体关系"""
    from_entity: str
    to_entity: str
    type: str
    description: str
    chapter: int


@dataclass
class StateChange:
    """状态变化记录"""
    entity_id: str
    field: str
    old_value: Any
    new_value: Any
    reason: str
    chapter: int
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class _EntityPatch:
    """待写入的实体增量补丁（用于锁内合并）"""
    entity_type: str
    entity_id: str
    replace: bool = False
    base_entity: Optional[Dict[str, Any]] = None  # 新建实体时的完整快照（用于填充缺失字段）
    top_updates: Dict[str, Any] = field(default_factory=dict)
    current_updates: Dict[str, Any] = field(default_factory=dict)
    appearance_chapter: Optional[int] = None


class StateManager:
    """状态管理器（v5.1 entities_v3 格式 + SQLite 同步，v5.4 沿用）"""

    # v5.0 引入的实体类型
    ENTITY_TYPES = ["角色", "地点", "物品", "势力", "招式"]

    def __init__(self, config=None, enable_sqlite_sync: bool = True):
        """
        初始化状态管理器

        参数:
        - config: 配置对象
        - enable_sqlite_sync: 是否启用 SQLite 同步 (默认 True)
        """
        self.config = config or get_config()
        self._state: Dict[str, Any] = {}
        # 与 security_utils.atomic_write_json 保持一致：state.json.lock
        self._lock_path = self.config.state_file.with_suffix(self.config.state_file.suffix + ".lock")

        # v5.1 引入: SQLite 同步
        self._enable_sqlite_sync = enable_sqlite_sync
        self._sql_state_manager = None
        if enable_sqlite_sync:
            try:
                from .sql_state_manager import SQLStateManager
                self._sql_state_manager = SQLStateManager(self.config)
            except ImportError as e:
                logger.warning(
                    "SQLStateManager 不可用，将使用 JSON 存储模式。原因: %s",
                    str(e)
                )

        # 待写入的增量（锁内重读 + 合并 + 写入）
        self._pending_entity_patches: Dict[tuple[str, str], _EntityPatch] = {}
        self._pending_alias_entries: Dict[str, List[Dict[str, str]]] = {}
        self._pending_state_changes: List[Dict[str, Any]] = []
        self._pending_structured_relationships: List[Dict[str, Any]] = []
        self._pending_disambiguation_warnings: List[Dict[str, Any]] = []
        self._pending_disambiguation_pending: List[Dict[str, Any]] = []
        self._pending_progress_chapter: Optional[int] = None
        self._pending_progress_words_delta: int = 0
        self._pending_chapter_meta: Dict[str, Any] = {}

        # v5.1 引入: 缓存待同步到 SQLite 的数据
        self._pending_sqlite_data: Dict[str, Any] = {
            "entities_appeared": [],
            "entities_new": [],
            "state_changes": [],
            "relationships_new": [],
            "chapter": None
        }

        # v5.5 引入: 同步状态追踪器，用于记录同步失败的数据
        self._sync_status = SyncStatus()

        # v5.5 引入: 同步配置
        self._sync_max_retries = 3
        self._sync_base_delay = 0.5
        self._sync_max_delay = 5.0

        self._load_state()

    def _now_progress_timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_state_schema(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """确保 state.json 具备运行所需的关键字段（尽量不破坏既有数据）。"""
        if not isinstance(state, dict):
            state = {}

        state.setdefault("project_info", {})
        state.setdefault("progress", {})
        state.setdefault("protagonist_state", {})

        # relationships: 旧版本可能是 list（实体关系），v5.0 运行态用 dict（人物关系/重要关系）
        relationships = state.get("relationships")
        if isinstance(relationships, list):
            state.setdefault("structured_relationships", [])
            if isinstance(state.get("structured_relationships"), list):
                state["structured_relationships"].extend(relationships)
            state["relationships"] = {}
        elif not isinstance(relationships, dict):
            state["relationships"] = {}

        state.setdefault("world_settings", {"power_system": [], "factions": [], "locations": []})
        state.setdefault("plot_threads", {"active_threads": [], "foreshadowing": []})
        state.setdefault("review_checkpoints", [])
        state.setdefault("chapter_meta", {})
        state.setdefault(
            "strand_tracker",
            {
                "last_quest_chapter": 0,
                "last_fire_chapter": 0,
                "last_constellation_chapter": 0,
                "current_dominant": "quest",
                "chapters_since_switch": 0,
                "history": [],
            },
        )

        # v5.1 引入: entities_v3, alias_index, state_changes, structured_relationships 已迁移到 index.db
        # 不再在 state.json 中初始化或维护这些字段

        if not isinstance(state.get("disambiguation_warnings"), list):
            state["disambiguation_warnings"] = []

        if not isinstance(state.get("disambiguation_pending"), list):
            state["disambiguation_pending"] = []

        # progress 基础字段
        progress = state["progress"]
        if not isinstance(progress, dict):
            progress = {}
            state["progress"] = progress
        progress.setdefault("current_chapter", 0)
        progress.setdefault("total_words", 0)
        progress.setdefault("last_updated", self._now_progress_timestamp())

        return state

    def _load_state(self):
        """加载状态文件"""
        if self.config.state_file.exists():
            self._state = read_json_safe(self.config.state_file, default={})
            self._state = self._ensure_state_schema(self._state)
        else:
            self._state = self._ensure_state_schema({})

    def save_state(self):
        """
        保存状态文件（锁内重读 + 合并 + 原子写入）。

        解决多 Agent 并行下的“读-改-写覆盖”风险：
        - 获取锁
        - 重新读取磁盘最新 state.json
        - 仅合并本实例产生的增量（pending_*）
        - 原子化写入
        """
        # 无增量时不写入，避免无意义覆盖
        has_pending = any(
            [
                self._pending_entity_patches,
                self._pending_alias_entries,
                self._pending_state_changes,
                self._pending_structured_relationships,
                self._pending_disambiguation_warnings,
                self._pending_disambiguation_pending,
                self._pending_chapter_meta,
                self._pending_progress_chapter is not None,
                self._pending_progress_words_delta != 0,
            ]
        )
        if not has_pending:
            return

        self.config.ensure_dirs()

        lock_timeout = 10
        lock = filelock.FileLock(str(self._lock_path), timeout=lock_timeout)
        lock_acquire_start = time.time()
        
        try:
            with lock:
                lock_acquire_time = time.time() - lock_acquire_start
                if lock_acquire_time > 1.0:
                    logger.warning(
                        "[save_state] 获取文件锁耗时较长: %.2f 秒，锁文件: %s",
                        lock_acquire_time,
                        self._lock_path
                    )
                
                disk_state = read_json_safe(self.config.state_file, default={})
                disk_state = self._ensure_state_schema(disk_state)

                # progress（合并为 max(chapter) + words_delta 累加）
                if self._pending_progress_chapter is not None or self._pending_progress_words_delta != 0:
                    progress = disk_state.get("progress", {})
                    if not isinstance(progress, dict):
                        progress = {}
                        disk_state["progress"] = progress

                    try:
                        current_chapter = int(progress.get("current_chapter", 0) or 0)
                    except (TypeError, ValueError):
                        current_chapter = 0

                    if self._pending_progress_chapter is not None:
                        progress["current_chapter"] = max(current_chapter, int(self._pending_progress_chapter))

                    if self._pending_progress_words_delta:
                        try:
                            total_words = int(progress.get("total_words", 0) or 0)
                        except (TypeError, ValueError):
                            total_words = 0
                        progress["total_words"] = total_words + int(self._pending_progress_words_delta)

                    progress["last_updated"] = self._now_progress_timestamp()

                # v5.1 引入: 强制使用 SQLite 模式，移除大数据字段
                # 确保 state.json 中不存在这些膨胀字段
                for field in ["entities_v3", "alias_index", "state_changes", "structured_relationships"]:
                    disk_state.pop(field, None)
                # 标记已迁移
                disk_state["_migrated_to_sqlite"] = True

                # disambiguation_warnings（追加去重 + 截断）
                if self._pending_disambiguation_warnings:
                    warnings_list = disk_state.get("disambiguation_warnings")
                    if not isinstance(warnings_list, list):
                        warnings_list = []
                        disk_state["disambiguation_warnings"] = warnings_list

                    def _warn_key(w: Dict[str, Any]) -> tuple:
                        return (
                            w.get("chapter"),
                            w.get("mention"),
                            w.get("chosen_id"),
                            w.get("confidence"),
                        )

                    existing_keys = {_warn_key(w) for w in warnings_list if isinstance(w, dict)}
                    for w in self._pending_disambiguation_warnings:
                        if not isinstance(w, dict):
                            continue
                        k = _warn_key(w)
                        if k in existing_keys:
                            continue
                        warnings_list.append(w)
                        existing_keys.add(k)

                    # 只保留最近 N 条，避免文件无限增长
                    max_keep = self.config.max_disambiguation_warnings
                    if len(warnings_list) > max_keep:
                        disk_state["disambiguation_warnings"] = warnings_list[-max_keep:]

                # disambiguation_pending（追加去重 + 截断）
                if self._pending_disambiguation_pending:
                    pending_list = disk_state.get("disambiguation_pending")
                    if not isinstance(pending_list, list):
                        pending_list = []
                        disk_state["disambiguation_pending"] = pending_list

                    def _pending_key(w: Dict[str, Any]) -> tuple:
                        return (
                            w.get("chapter"),
                            w.get("mention"),
                            w.get("suggested_id"),
                            w.get("confidence"),
                        )

                    existing_keys = {_pending_key(w) for w in pending_list if isinstance(w, dict)}
                    for w in self._pending_disambiguation_pending:
                        if not isinstance(w, dict):
                            continue
                        k = _pending_key(w)
                        if k in existing_keys:
                            continue
                        pending_list.append(w)
                        existing_keys.add(k)

                    max_keep = self.config.max_disambiguation_pending
                    if len(pending_list) > max_keep:
                        disk_state["disambiguation_pending"] = pending_list[-max_keep:]

                # chapter_meta（新增：按章节号覆盖写入）
                if self._pending_chapter_meta:
                    chapter_meta = disk_state.get("chapter_meta")
                    if not isinstance(chapter_meta, dict):
                        chapter_meta = {}
                        disk_state["chapter_meta"] = chapter_meta
                    chapter_meta.update(self._pending_chapter_meta)

                # 原子写入（锁已持有，不再二次加锁）
                atomic_write_json(self.config.state_file, disk_state, use_lock=False, backup=True)

                # v5.1 引入: 同步到 SQLite（失败时保留 pending 以便重试）
                sqlite_pending_snapshot = self._snapshot_sqlite_pending()
                sqlite_sync_ok = self._sync_to_sqlite_with_retry()

                # 同步内存为磁盘最新快照
                self._state = disk_state

                # state.json 侧 pending 已写盘，直接清空
                self._pending_disambiguation_warnings.clear()
                self._pending_disambiguation_pending.clear()
                self._pending_chapter_meta.clear()
                self._pending_progress_chapter = None
                self._pending_progress_words_delta = 0

                # SQLite 侧 pending：成功后清空，失败则恢复快照（避免静默丢数据）
                if sqlite_sync_ok:
                    self._pending_entity_patches.clear()
                    self._pending_alias_entries.clear()
                    self._pending_state_changes.clear()
                    self._pending_structured_relationships.clear()
                    self._clear_pending_sqlite_data()
                    self._sync_status.mark_success("sqlite_sync")
                    logger.info("[save_state] SQLite 同步成功")
                else:
                    self._restore_sqlite_pending(sqlite_pending_snapshot)
                    self._sync_status.mark_failed("sqlite_sync", Exception("SQLite 同步失败"))
                    logger.warning("[save_state] SQLite 同步失败，数据已保留在待同步队列中")

        except filelock.Timeout:
            lock_wait_time = time.time() - lock_acquire_start
            pending_summary = {
                "entity_patches": len(self._pending_entity_patches),
                "alias_entries": len(self._pending_alias_entries),
                "state_changes": len(self._pending_state_changes),
                "structured_relationships": len(self._pending_structured_relationships),
                "progress_chapter": self._pending_progress_chapter,
                "progress_words_delta": self._pending_progress_words_delta,
            }
            logger.error(
                "[save_state] 获取文件锁超时，等待时间: %.2f 秒，超时设置: %d 秒",
                lock_wait_time,
                lock_timeout
            )
            logger.error(
                "[save_state] 锁文件路径: %s",
                self._lock_path
            )
            logger.error(
                "[save_state] 待保存数据摘要: %s",
                pending_summary
            )
            logger.error(
                "[save_state] 建议: 检查是否有其他进程长时间持有锁，或增加锁超时时间"
            )
            raise RuntimeError(
                f"无法获取 state.json 文件锁（等待 {lock_wait_time:.2f} 秒），"
                "请稍后重试或检查是否有其他进程阻塞"
            )

    def _sync_to_sqlite(self) -> bool:
        """同步待处理数据到 SQLite（v5.1 引入，v5.4 沿用）"""
        if not self._sql_state_manager:
            return True

        sqlite_data = self._pending_sqlite_data
        chapter = sqlite_data.get("chapter")

        processed_appearances = set()

        if chapter is not None:
            try:
                self._sql_state_manager.process_chapter_entities(
                    chapter=chapter,
                    entities_appeared=sqlite_data.get("entities_appeared", []),
                    entities_new=sqlite_data.get("entities_new", []),
                    state_changes=sqlite_data.get("state_changes", []),
                    relationships_new=sqlite_data.get("relationships_new", [])
                )
                for entity in sqlite_data.get("entities_appeared", []):
                    if entity.get("id"):
                        processed_appearances.add((entity.get("id"), chapter))
                for entity in sqlite_data.get("entities_new", []):
                    eid = entity.get("suggested_id") or entity.get("id")
                    if eid:
                        processed_appearances.add((eid, chapter))
            except sqlite3.Error as exc:
                logger.warning(
                    "SQLite 同步失败 (process_chapter_entities): %s, 章节: %s",
                    exc,
                    chapter,
                    exc_info=True,
                )
                return False
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning(
                    "SQLite 数据格式错误 (process_chapter_entities): %s, 章节: %s",
                    exc,
                    chapter,
                    exc_info=True,
                )
                return False

        return self._sync_pending_patches_to_sqlite(processed_appearances)

    def _sync_to_sqlite_with_retry(self) -> bool:
        """
        带重试机制的 SQLite 同步方法（v5.5 引入，v5.6 增强）
        
        使用指数退避策略进行重试，确保在临时故障时能够恢复。
        如果所有重试都失败，数据会保留在待同步队列中。
        
        返回: 同步是否成功
        """
        if not self._sql_state_manager:
            logger.debug("[_sync_to_sqlite_with_retry] SQLite 同步已禁用，跳过")
            return True

        pending_summary = {
            "entity_patches": len(self._pending_entity_patches),
            "alias_entries": len(self._pending_alias_entries),
            "state_changes": len(self._pending_state_changes),
            "structured_relationships": len(self._pending_structured_relationships),
            "sqlite_data_chapter": self._pending_sqlite_data.get("chapter"),
        }
        logger.info(
            "[_sync_to_sqlite_with_retry] 开始同步，待同步数据: %s",
            pending_summary
        )

        attempt_times = []
        start_time = time.time()

        def on_retry_callback(attempt: int, exc: Exception) -> None:
            """
            重试回调函数，记录每次重试的详细信息
            
            参数:
            - attempt: 当前重试次数
            - exc: 触发重试的异常
            """
            delay = min(self._sync_base_delay * (2 ** (attempt - 1)), self._sync_max_delay)
            attempt_times.append({
                "attempt": attempt,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "delay": delay,
                "timestamp": time.time() - start_time
            })
            logger.warning(
                "[_sync_to_sqlite_with_retry] 第 %d/%d 次重试，"
                "错误: %s (%s)，%.2f秒后重试",
                attempt,
                self._sync_max_retries,
                str(exc),
                type(exc).__name__,
                delay
            )

        def on_failure_callback(exc: Exception) -> None:
            """
            最终失败回调函数，记录详细的失败信息
            
            参数:
            - exc: 最终导致失败的异常
            """
            total_time = time.time() - start_time
            logger.error(
                "[_sync_to_sqlite_with_retry] SQLite 同步最终失败，"
                "共重试 %d 次，总耗时 %.2f 秒，最终错误: %s (%s)",
                self._sync_max_retries,
                total_time,
                str(exc),
                type(exc).__name__
            )
            logger.error(
                "[_sync_to_sqlite_with_retry] 重试历史: %s",
                attempt_times
            )
            logger.error(
                "[_sync_to_sqlite_with_retry] 待恢复数据摘要: %s",
                pending_summary
            )

        success, _, error = retry_sync_safe(
            self._sync_to_sqlite,
            max_retries=self._sync_max_retries,
            base_delay=self._sync_base_delay,
            max_delay=self._sync_max_delay,
            exponential_backoff=True,
            default=False,
            on_retry=on_retry_callback,
            on_failure=on_failure_callback
        )

        return success

    def get_sync_status(self) -> Dict[str, Any]:
        """
        获取同步状态信息（v5.5 引入）
        
        返回当前同步状态，包括待同步数据和失败计数。
        """
        return {
            "pending_count": len(self._sync_status.get_all_pending()),
            "failed_count": self._sync_status.get_failed_count("sqlite_sync"),
            "last_error": self._sync_status.get_last_error("sqlite_sync"),
            "pending_entity_patches": len(self._pending_entity_patches),
            "pending_alias_entries": len(self._pending_alias_entries),
            "pending_state_changes": len(self._pending_state_changes),
            "pending_structured_relationships": len(self._pending_structured_relationships),
        }

    def recover_failed_sync(self, max_attempts: int = 3) -> Dict[str, Any]:
        """
        恢复失败的同步数据（v5.6 引入）
        
        尝试将之前同步失败的数据重新同步到 SQLite。
        该方法会遍历所有待同步的数据，并尝试重新执行同步操作。
        
        参数:
        - max_attempts: 每个数据项的最大恢复尝试次数
        
        返回: 恢复结果摘要
        """
        if not self._sql_state_manager:
            logger.info("[recover_failed_sync] SQLite 同步已禁用，无需恢复")
            return {"recovered": 0, "failed": 0, "skipped": 0, "reason": "sqlite_disabled"}

        recovery_result = {
            "recovered": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
            "start_time": time.time()
        }

        pending_count = (
            len(self._pending_entity_patches) +
            len(self._pending_alias_entries) +
            len(self._pending_state_changes) +
            len(self._pending_structured_relationships)
        )

        if pending_count == 0:
            logger.info("[recover_failed_sync] 没有待恢复的数据")
            return {**recovery_result, "reason": "no_pending_data"}

        logger.info(
            "[recover_failed_sync] 开始恢复，待恢复数据项: %d (实体补丁: %d, 别名: %d, 状态变化: %d, 关系: %d)",
            pending_count,
            len(self._pending_entity_patches),
            len(self._pending_alias_entries),
            len(self._pending_state_changes),
            len(self._pending_structured_relationships)
        )

        success = self._sync_to_sqlite_with_retry()

        if success:
            recovery_result["recovered"] = pending_count
            recovery_result["details"].append({
                "type": "all_pending",
                "status": "recovered",
                "count": pending_count
            })
            self._sync_status.mark_success("sqlite_sync")
            logger.info("[recover_failed_sync] 数据恢复成功，共恢复 %d 项", pending_count)
        else:
            recovery_result["failed"] = pending_count
            recovery_result["details"].append({
                "type": "all_pending",
                "status": "failed",
                "count": pending_count,
                "error": self._sync_status.get_last_error("sqlite_sync")
            })
            logger.error(
                "[recover_failed_sync] 数据恢复失败，共 %d 项未能同步",
                pending_count
            )

        recovery_result["elapsed_time"] = time.time() - recovery_result["start_time"]
        del recovery_result["start_time"]

        return recovery_result

    def get_pending_sync_summary(self) -> Dict[str, Any]:
        """
        获取待同步数据的详细摘要（v5.6 引入）
        
        返回所有待同步数据的详细信息，用于诊断和恢复操作。
        
        返回: 待同步数据的详细摘要
        """
        summary = {
            "timestamp": datetime.now().isoformat(),
            "entity_patches": [],
            "alias_entries": [],
            "state_changes": [],
            "structured_relationships": [],
            "sqlite_data": {}
        }

        for (entity_type, entity_id), patch in self._pending_entity_patches.items():
            patch_info = {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "is_new": patch.base_entity is not None,
                "has_top_updates": bool(patch.top_updates),
                "has_current_updates": bool(patch.current_updates),
                "appearance_chapter": patch.appearance_chapter
            }
            summary["entity_patches"].append(patch_info)

        for alias, entries in self._pending_alias_entries.items():
            summary["alias_entries"].append({
                "alias": alias,
                "entries_count": len(entries),
                "entries": entries
            })

        for change in self._pending_state_changes:
            summary["state_changes"].append({
                "entity_id": change.get("entity_id"),
                "field": change.get("field"),
                "chapter": change.get("chapter")
            })

        for rel in self._pending_structured_relationships:
            summary["structured_relationships"].append({
                "from_entity": rel.get("from_entity"),
                "to_entity": rel.get("to_entity"),
                "type": rel.get("type"),
                "chapter": rel.get("chapter")
            })

        summary["sqlite_data"] = {
            "chapter": self._pending_sqlite_data.get("chapter"),
            "entities_appeared_count": len(self._pending_sqlite_data.get("entities_appeared", [])),
            "entities_new_count": len(self._pending_sqlite_data.get("entities_new", [])),
            "state_changes_count": len(self._pending_sqlite_data.get("state_changes", [])),
            "relationships_new_count": len(self._pending_sqlite_data.get("relationships_new", []))
        }

        summary["totals"] = {
            "entity_patches": len(summary["entity_patches"]),
            "alias_entries": len(summary["alias_entries"]),
            "state_changes": len(summary["state_changes"]),
            "structured_relationships": len(summary["structured_relationships"])
        }

        return summary

    def _sync_pending_patches_to_sqlite(self, processed_appearances: set = None) -> bool:
        """同步 _pending_entity_patches 等到 SQLite（v5.1 引入，v5.4 沿用）

        Args:
            processed_appearances: 已通过 process_chapter_entities 处理的 (entity_id, chapter) 集合，
                                   用于避免重复写入 appearances 表（防止覆盖 mentions）
        """
        if not self._sql_state_manager:
            return True

        if processed_appearances is None:
            processed_appearances = set()

        # 元数据字段（不应写入 current_json）
        METADATA_FIELDS = {"canonical_name", "tier", "desc", "is_protagonist", "is_archived"}

        try:
            from .sql_state_manager import EntityData
            from .index_manager import EntityMeta

            # 同步实体补丁
            for (entity_type, entity_id), patch in self._pending_entity_patches.items():
                if patch.base_entity:
                    # 新实体
                    entity_data = EntityData(
                        id=entity_id,
                        type=entity_type,
                        name=patch.base_entity.get("canonical_name", entity_id),
                        tier=patch.base_entity.get("tier", "装饰"),
                        desc=patch.base_entity.get("desc", ""),
                        current=patch.base_entity.get("current", {}),
                        aliases=[],
                        first_appearance=patch.base_entity.get("first_appearance", 0),
                        last_appearance=patch.base_entity.get("last_appearance", 0),
                        is_protagonist=patch.base_entity.get("is_protagonist", False)
                    )
                    self._sql_state_manager.upsert_entity(entity_data)

                    # 记录首次出场（跳过已处理的，避免覆盖 mentions）
                    if patch.appearance_chapter is not None:
                        if (entity_id, patch.appearance_chapter) not in processed_appearances:
                            self._sql_state_manager._index_manager.record_appearance(
                                entity_id=entity_id,
                                chapter=patch.appearance_chapter,
                                mentions=[entity_data.name],
                                confidence=1.0,
                                skip_if_exists=True  # 关键：不覆盖已有记录
                            )
                else:
                    # 更新现有实体
                    has_metadata_updates = bool(patch.top_updates and
                                                 any(k in METADATA_FIELDS for k in patch.top_updates))

                    # 非元数据的 top_updates 应该当作 current 更新
                    # 例如：realm, layer, location 等状态字段
                    non_metadata_top_updates = {
                        k: v for k, v in patch.top_updates.items()
                        if k not in METADATA_FIELDS
                    } if patch.top_updates else {}

                    # 合并 current_updates 和非元数据的 top_updates
                    effective_current_updates = {**non_metadata_top_updates}
                    if patch.current_updates:
                        effective_current_updates.update(patch.current_updates)

                    if has_metadata_updates:
                        # 有元数据更新：使用 upsert_entity(update_metadata=True)
                        existing = self._sql_state_manager.get_entity(entity_id)
                        if existing:
                            # 合并 current
                            current = existing.get("current_json", {})
                            if isinstance(current, str):
                                import json
                                current = json.loads(current) if current else {}
                            if effective_current_updates:
                                current.update(effective_current_updates)

                            new_canonical_name = patch.top_updates.get("canonical_name")
                            old_canonical_name = existing.get("canonical_name", "")

                            entity_meta = EntityMeta(
                                id=entity_id,
                                type=existing.get("type", entity_type),
                                canonical_name=new_canonical_name or old_canonical_name,
                                tier=patch.top_updates.get("tier", existing.get("tier", "装饰")),
                                desc=patch.top_updates.get("desc", existing.get("desc", "")),
                                current=current,
                                first_appearance=existing.get("first_appearance", 0),
                                last_appearance=patch.appearance_chapter or existing.get("last_appearance", 0),
                                is_protagonist=patch.top_updates.get("is_protagonist", existing.get("is_protagonist", False)),
                                is_archived=patch.top_updates.get("is_archived", existing.get("is_archived", False))
                            )
                            self._sql_state_manager._index_manager.upsert_entity(entity_meta, update_metadata=True)

                            # 如果 canonical_name 改名，自动注册新名字为 alias
                            if new_canonical_name and new_canonical_name != old_canonical_name:
                                self._sql_state_manager.register_alias(
                                    new_canonical_name, entity_id, existing.get("type", entity_type)
                                )
                    elif effective_current_updates:
                        # 只有 current 更新（包括非元数据的 top_updates）
                        self._sql_state_manager.update_entity_current(entity_id, effective_current_updates)

                    # 更新 last_appearance 并记录出场
                    if patch.appearance_chapter is not None:
                        self._sql_state_manager._update_last_appearance(entity_id, patch.appearance_chapter)
                        # 补充 appearances 记录
                        # 使用 skip_if_exists=True 避免覆盖已有记录的 mentions
                        if (entity_id, patch.appearance_chapter) not in processed_appearances:
                            self._sql_state_manager._index_manager.record_appearance(
                                entity_id=entity_id,
                                chapter=patch.appearance_chapter,
                                mentions=[],
                                confidence=1.0,
                                skip_if_exists=True  # 关键：不覆盖已有记录
                            )

            # 同步别名
            for alias, entries in self._pending_alias_entries.items():
                for entry in entries:
                    entity_type = entry.get("type")
                    entity_id = entry.get("id")
                    if entity_type and entity_id:
                        self._sql_state_manager.register_alias(alias, entity_id, entity_type)

            # 同步状态变化
            for change in self._pending_state_changes:
                self._sql_state_manager.record_state_change(
                    entity_id=change.get("entity_id", ""),
                    field=change.get("field", ""),
                    old_value=change.get("old", change.get("old_value", "")),
                    new_value=change.get("new", change.get("new_value", "")),
                    reason=change.get("reason", ""),
                    chapter=change.get("chapter", 0)
                )

            # 同步关系
            for rel in self._pending_structured_relationships:
                self._sql_state_manager.upsert_relationship(
                    from_entity=rel.get("from_entity", ""),
                    to_entity=rel.get("to_entity", ""),
                    type=rel.get("type", "相识"),
                    description=rel.get("description", ""),
                    chapter=rel.get("chapter", 0)
                )

            return True

        except sqlite3.Error as e:
            logger.warning(
                "SQLite 同步失败: %s, 操作: _sync_pending_patches_to_sqlite",
                e,
                exc_info=True,
            )
            return False
        except (KeyError, TypeError, ValueError) as e:
            logger.warning(
                "SQLite 数据格式错误: %s, 操作: _sync_pending_patches_to_sqlite",
                e,
                exc_info=True,
            )
            return False

    def _snapshot_sqlite_pending(self) -> Dict[str, Any]:
        """抓取 SQLite 侧 pending 快照，用于同步失败回滚内存队列。"""
        return {
            "entity_patches": deepcopy(self._pending_entity_patches),
            "alias_entries": deepcopy(self._pending_alias_entries),
            "state_changes": deepcopy(self._pending_state_changes),
            "structured_relationships": deepcopy(self._pending_structured_relationships),
            "sqlite_data": deepcopy(self._pending_sqlite_data),
        }

    def _restore_sqlite_pending(self, snapshot: Dict[str, Any]) -> None:
        """恢复 SQLite 侧 pending 快照，避免同步失败后数据静默丢失。"""
        self._pending_entity_patches = snapshot.get("entity_patches", {})
        self._pending_alias_entries = snapshot.get("alias_entries", {})
        self._pending_state_changes = snapshot.get("state_changes", [])
        self._pending_structured_relationships = snapshot.get("structured_relationships", [])
        self._pending_sqlite_data = snapshot.get("sqlite_data", {
            "entities_appeared": [],
            "entities_new": [],
            "state_changes": [],
            "relationships_new": [],
            "chapter": None,
        })

    def _clear_pending_sqlite_data(self):
        """清空待同步的 SQLite 数据"""
        self._pending_sqlite_data = {
            "entities_appeared": [],
            "entities_new": [],
            "state_changes": [],
            "relationships_new": [],
            "chapter": None
        }

    # ==================== 进度管理 ====================

    def get_current_chapter(self) -> int:
        """
        获取当前章节号。
        
        返回:
            int: 当前章节号，如果未设置则返回 0。
        """
        return self._state.get("progress", {}).get("current_chapter", 0)

    def update_progress(self, chapter: int, words: int = 0):
        """
        更新写作进度。
        
        记录当前章节号和新增字数。章节号采用取最大值策略，
        字数采用累加策略，确保多 Agent 并行写入时数据正确。
        
        参数:
            chapter: 当前章节号。
            words: 新增字数，默认为 0。
        """
        if "progress" not in self._state:
            self._state["progress"] = {}
        self._state["progress"]["current_chapter"] = chapter
        if words > 0:
            total = self._state["progress"].get("total_words", 0)
            self._state["progress"]["total_words"] = total + words

        if self._pending_progress_chapter is None:
            self._pending_progress_chapter = chapter
        else:
            self._pending_progress_chapter = max(self._pending_progress_chapter, chapter)
        if words > 0:
            self._pending_progress_words_delta += int(words)

    # ==================== 实体管理 (v5.1 SQLite-first) ====================

    def get_entity(self, entity_id: str, entity_type: str = None) -> Optional[Dict]:
        """
        获取实体信息。
        
        优先从 SQLite 数据库读取实体信息，如果 SQLite 不可用则回退到内存状态。
        
        参数:
            entity_id: 实体唯一标识符。
            entity_type: 实体类型（角色/地点/物品/势力/招式），可选。
            
        返回:
            Optional[Dict]: 实体信息字典，如果未找到则返回 None。
        """
        if self._sql_state_manager:
            entity = self._sql_state_manager._index_manager.get_entity(entity_id)
            if entity:
                return entity

        entities_v3 = self._state.get("entities_v3", {})
        if entity_type:
            return entities_v3.get(entity_type, {}).get(entity_id)

        for type_name, entities in entities_v3.items():
            if entity_id in entities:
                return entities[entity_id]
        return None

    def get_entity_type(self, entity_id: str) -> Optional[str]:
        """
        获取实体所属类型。
        
        优先从 SQLite 数据库查询实体类型，如果不可用则遍历内存状态查找。
        
        参数:
            entity_id: 实体唯一标识符。
            
        返回:
            Optional[str]: 实体类型（角色/地点/物品/势力/招式），如果未找到则返回 None。
        """
        if self._sql_state_manager:
            entity = self._sql_state_manager._index_manager.get_entity(entity_id)
            if entity:
                return entity.get("type")

        for type_name, entities in self._state.get("entities_v3", {}).items():
            if entity_id in entities:
                return type_name
        return None

    def get_all_entities(self) -> Dict[str, Dict]:
        """
        获取所有实体的扁平化视图。
        
        优先从 SQLite 数据库读取所有实体，如果不可用则从内存状态构建。
        返回的字典以实体 ID 为键，包含实体信息和类型字段。
        
        返回:
            Dict[str, Dict]: 所有实体的字典，键为实体 ID，值为包含实体信息和类型的字典。
        """
        if self._sql_state_manager:
            result = {}
            for entity_type in self.ENTITY_TYPES:
                entities = self._sql_state_manager._index_manager.get_entities_by_type(entity_type)
                for e in entities:
                    eid = e.get("id")
                    if eid:
                        result[eid] = {**e, "type": entity_type}
            if result:
                return result

        result = {}
        for type_name, entities in self._state.get("entities_v3", {}).items():
            for eid, e in entities.items():
                result[eid] = {**e, "type": type_name}
        return result

    def get_entities_by_type(self, entity_type: str) -> Dict[str, Dict]:
        """
        按类型获取实体。
        
        优先从 SQLite 数据库读取指定类型的实体，如果不可用则从内存状态读取。
        
        参数:
            entity_type: 实体类型（角色/地点/物品/势力/招式）。
            
        返回:
            Dict[str, Dict]: 指定类型的实体字典，键为实体 ID，值为实体信息。
        """
        if self._sql_state_manager:
            entities = self._sql_state_manager._index_manager.get_entities_by_type(entity_type)
            if entities:
                return {e.get("id"): e for e in entities if e.get("id")}

        return self._state.get("entities_v3", {}).get(entity_type, {})

    def get_entities_by_tier(self, tier: str) -> Dict[str, Dict]:
        """
        按层级获取实体。
        
        优先从 SQLite 数据库读取指定层级的实体，如果不可用则从内存状态筛选。
        
        参数:
            tier: 实体层级（核心/重要/次要/装饰）。
            
        返回:
            Dict[str, Dict]: 指定层级的实体字典，键为实体 ID，值为包含实体信息和类型的字典。
        """
        if self._sql_state_manager:
            result = {}
            for entity_type in self.ENTITY_TYPES:
                entities = self._sql_state_manager._index_manager.get_entities_by_tier(tier)
                for e in entities:
                    eid = e.get("id")
                    if eid and e.get("type") == entity_type:
                        result[eid] = {**e, "type": entity_type}
            if result:
                return result

        result = {}
        for type_name, entities in self._state.get("entities_v3", {}).items():
            for eid, e in entities.items():
                if e.get("tier") == tier:
                    result[eid] = {**e, "type": type_name}
        return result

    def add_entity(self, entity: EntityState) -> bool:
        """
        添加新实体。
        
        将实体信息写入内存状态和待同步队列，并注册别名到 SQLite 数据库。
        如果实体已存在则不会重复添加。
        
        参数:
            entity: 实体状态对象，包含 ID、名称、类型、层级等信息。
            
        返回:
            bool: 添加成功返回 True，实体已存在返回 False。
        """
        entity_type = entity.type
        if entity_type not in self.ENTITY_TYPES:
            entity_type = "角色"

        if "entities_v3" not in self._state:
            self._state["entities_v3"] = {t: {} for t in self.ENTITY_TYPES}

        if entity_type not in self._state["entities_v3"]:
            self._state["entities_v3"][entity_type] = {}

        if entity.id in self._state["entities_v3"][entity_type]:
            return False

        v3_entity = {
            "canonical_name": entity.name,
            "tier": entity.tier,
            "desc": "",
            "current": entity.attributes,
            "first_appearance": entity.first_appearance,
            "last_appearance": entity.last_appearance,
            "history": []
        }
        self._state["entities_v3"][entity_type][entity.id] = v3_entity

        patch = self._pending_entity_patches.get((entity_type, entity.id))
        if patch is None:
            patch = _EntityPatch(entity_type=entity_type, entity_id=entity.id)
            self._pending_entity_patches[(entity_type, entity.id)] = patch
        patch.replace = True
        patch.base_entity = v3_entity

        if self._sql_state_manager:
            self._sql_state_manager._index_manager.register_alias(entity.name, entity.id, entity_type)
            for alias in entity.aliases:
                if alias:
                    self._sql_state_manager._index_manager.register_alias(alias, entity.id, entity_type)

        return True

    def _register_alias_internal(self, entity_id: str, entity_type: str, alias: str):
        """内部方法：注册别名到 index.db（v5.1 引入）"""
        if not alias:
            return
        # v5.1 引入: 直接写入 SQLite
        if self._sql_state_manager:
            self._sql_state_manager._index_manager.register_alias(alias, entity_id, entity_type)

    def update_entity(self, entity_id: str, updates: Dict[str, Any], entity_type: str = None) -> bool:
        """
        更新实体属性。
        
        支持更新实体的元数据（如 canonical_name、tier）和当前状态（current）。
        更新会同时写入内存状态和待同步队列，确保 SQLite 同步时数据一致。
        
        参数:
            entity_id: 实体唯一标识符。
            updates: 要更新的属性字典。支持 "attributes"/"current" 键更新状态，
                     其他键直接更新顶层属性。
            entity_type: 实体类型，可选。如果未指定则自动查找。
            
        返回:
            bool: 更新成功返回 True，实体不存在返回 False。
        """
        resolved_type = entity_type or self.get_entity_type(entity_id)
        if not resolved_type:
            return False
        if resolved_type not in self.ENTITY_TYPES:
            resolved_type = "角色"

        entities_v3 = self._state.get("entities_v3")
        entity = None
        if isinstance(entities_v3, dict):
            bucket = entities_v3.get(resolved_type)
            if isinstance(bucket, dict):
                entity = bucket.get(entity_id)

        patch = None
        if self._sql_state_manager:
            patch = self._pending_entity_patches.get((resolved_type, entity_id))
            if patch is None:
                patch = _EntityPatch(entity_type=resolved_type, entity_id=entity_id)
                self._pending_entity_patches[(resolved_type, entity_id)] = patch

        if entity is None and patch is None:
            return False

        did_any = False
        for key, value in updates.items():
            if key == "attributes" and isinstance(value, dict):
                if entity is not None:
                    if "current" not in entity:
                        entity["current"] = {}
                    entity["current"].update(value)
                if patch is not None:
                    patch.current_updates.update(value)
                did_any = True
            elif key == "current" and isinstance(value, dict):
                if entity is not None:
                    if "current" not in entity:
                        entity["current"] = {}
                    entity["current"].update(value)
                if patch is not None:
                    patch.current_updates.update(value)
                did_any = True
            else:
                if entity is not None:
                    entity[key] = value
                if patch is not None:
                    patch.top_updates[key] = value
                did_any = True

        return did_any

    def update_entity_appearance(self, entity_id: str, chapter: int, entity_type: str = None):
        """
        更新实体出场章节。
        
        更新实体的首次出场和最近出场章节号。首次出场只在为 0 时设置，
        最近出场始终更新为当前章节。同时记录补丁用于 SQLite 同步。
        
        参数:
            entity_id: 实体唯一标识符。
            chapter: 当前章节号。
            entity_type: 实体类型，可选。如果未指定则自动查找。
        """
        if not entity_type:
            entity_type = self.get_entity_type(entity_id)
        if not entity_type:
            return

        entities_v3 = self._state.get("entities_v3")
        if not isinstance(entities_v3, dict):
            entities_v3 = {t: {} for t in self.ENTITY_TYPES}
            self._state["entities_v3"] = entities_v3
        entities_v3.setdefault(entity_type, {})

        entity = entities_v3[entity_type].get(entity_id)
        if entity:
            if entity.get("first_appearance", 0) == 0:
                entity["first_appearance"] = chapter
            entity["last_appearance"] = chapter

            patch = self._pending_entity_patches.get((entity_type, entity_id))
            if patch is None:
                patch = _EntityPatch(entity_type=entity_type, entity_id=entity_id)
                self._pending_entity_patches[(entity_type, entity_id)] = patch
            if patch.appearance_chapter is None:
                patch.appearance_chapter = chapter
            else:
                patch.appearance_chapter = max(int(patch.appearance_chapter), int(chapter))

    # ==================== 状态变化记录 ====================

    def record_state_change(
        self,
        entity_id: str,
        field: str,
        old_value: Any,
        new_value: Any,
        reason: str,
        chapter: int
    ):
        """
        记录实体状态变化。
        
        记录实体属性的变化历史，包括旧值、新值、变化原因和章节号。
        同时更新实体的当前属性。
        
        参数:
            entity_id: 实体唯一标识符。
            field: 发生变化的字段名。
            old_value: 变化前的值。
            new_value: 变化后的值。
            reason: 变化原因说明。
            chapter: 发生变化的章节号。
        """
        if "state_changes" not in self._state:
            self._state["state_changes"] = []

        change = StateChange(
            entity_id=entity_id,
            field=field,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            chapter=chapter
        )
        change_dict = asdict(change)
        self._state["state_changes"].append(change_dict)
        self._pending_state_changes.append(change_dict)

        self.update_entity(entity_id, {"attributes": {field: new_value}})

    def get_state_changes(self, entity_id: Optional[str] = None) -> List[Dict]:
        """
        获取状态变化历史。
        
        参数:
            entity_id: 实体唯一标识符，可选。如果指定则只返回该实体的变化记录。
            
        返回:
            List[Dict]: 状态变化记录列表。
        """
        changes = self._state.get("state_changes", [])
        if entity_id:
            changes = [c for c in changes if c.get("entity_id") == entity_id]
        return changes

    # ==================== 关系管理 ====================

    def add_relationship(
        self,
        from_entity: str,
        to_entity: str,
        rel_type: str,
        description: str,
        chapter: int
    ):
        """
        添加实体间的关系。
        
        记录两个实体之间的关系信息，包括关系类型、描述和发生章节。
        关系数据会同时写入内存状态和待同步队列，确保 SQLite 同步时数据一致。
        
        参数:
            from_entity: 关系起始实体的唯一标识符。
            to_entity: 关系目标实体的唯一标识符。
            rel_type: 关系类型（如：相识、敌对、师徒等）。
            description: 关系的详细描述说明。
            chapter: 关系建立或发生变化的章节号。
        """
        rel = Relationship(
            from_entity=from_entity,
            to_entity=to_entity,
            type=rel_type,
            description=description,
            chapter=chapter
        )

        # v5.0 引入: 实体关系存入 structured_relationships，避免与 relationships(人物关系字典) 冲突
        if "structured_relationships" not in self._state:
            self._state["structured_relationships"] = []
        rel_dict = asdict(rel)
        self._state["structured_relationships"].append(rel_dict)
        self._pending_structured_relationships.append(rel_dict)

    def get_relationships(self, entity_id: Optional[str] = None) -> List[Dict]:
        """
        获取关系列表。
        
        查询实体间的关系记录。如果指定了实体 ID，则只返回与该实体相关的关系；
        如果未指定，则返回所有关系记录。
        
        参数:
            entity_id: 实体唯一标识符，可选。如果指定，只返回该实体作为起点或终点的关系。
            
        返回:
            List[Dict]: 关系记录列表，每条记录包含 from_entity、to_entity、type、description、chapter 等字段。
        """
        rels = self._state.get("structured_relationships", [])
        if entity_id:
            rels = [
                r for r in rels
                if r.get("from_entity") == entity_id or r.get("to_entity") == entity_id
            ]
        return rels

    # ==================== 批量操作 ====================

    def _record_disambiguation(self, chapter: int, uncertain_items: Any) -> List[str]:
        """
        记录消歧反馈到 state.json，便于 Writer/Context Agent 感知风险。

        约定：
        - >= extraction_confidence_medium：写入 disambiguation_warnings（采用但警告）
        - < extraction_confidence_medium：写入 disambiguation_pending（需人工确认）
        """
        if not isinstance(uncertain_items, list) or not uncertain_items:
            return []

        warnings: List[str] = []
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for item in uncertain_items:
            if not isinstance(item, dict):
                continue

            mention = str(item.get("mention", "") or "").strip()
            if not mention:
                continue

            raw_conf = item.get("confidence", 0.0)
            try:
                confidence = float(raw_conf)
            except (TypeError, ValueError):
                confidence = 0.0

            # 候选：支持 [{"type","id"}...] 或 ["id1","id2"] 两种形式
            candidates_raw = item.get("candidates", [])
            candidates: List[Dict[str, str]] = []
            if isinstance(candidates_raw, list):
                for c in candidates_raw:
                    if isinstance(c, dict):
                        cid = str(c.get("id", "") or "").strip()
                        ctype = str(c.get("type", "") or "").strip()
                        entry: Dict[str, str] = {}
                        if ctype:
                            entry["type"] = ctype
                        if cid:
                            entry["id"] = cid
                        if entry:
                            candidates.append(entry)
                    else:
                        cid = str(c).strip()
                        if cid:
                            candidates.append({"id": cid})

            entity_type = str(item.get("type", "") or "").strip()
            suggested_id = str(item.get("suggested", "") or "").strip()

            adopted_raw = item.get("adopted", None)
            chosen_id = ""
            if isinstance(adopted_raw, str):
                chosen_id = adopted_raw.strip()
            elif adopted_raw is True:
                chosen_id = suggested_id
            else:
                # 兼容字段名：entity_id / chosen_id
                chosen_id = str(item.get("entity_id") or item.get("chosen_id") or "").strip() or suggested_id

            context = str(item.get("context", "") or "").strip()
            note = str(item.get("warning", "") or "").strip()

            record: Dict[str, Any] = {
                "chapter": int(chapter),
                "mention": mention,
                "type": entity_type,
                "suggested_id": suggested_id,
                "chosen_id": chosen_id,
                "confidence": confidence,
                "candidates": candidates,
                "context": context,
                "note": note,
                "created_at": now,
            }

            if confidence >= float(self.config.extraction_confidence_medium):
                self._state.setdefault("disambiguation_warnings", []).append(record)
                self._pending_disambiguation_warnings.append(record)
                chosen_part = f" → {chosen_id}" if chosen_id else ""
                warnings.append(f"消歧警告: {mention}{chosen_part} (confidence: {confidence:.2f})")
            else:
                self._state.setdefault("disambiguation_pending", []).append(record)
                self._pending_disambiguation_pending.append(record)
                warnings.append(f"消歧需人工确认: {mention} (confidence: {confidence:.2f})")

        return warnings

    def process_chapter_result(self, chapter: int, result: Dict) -> List[str]:
        """
        处理 Data Agent 的章节处理结果（v5.1 引入，v5.4 沿用）

        输入格式:
        - entities_appeared: 出场实体列表
        - entities_new: 新实体列表
        - state_changes: 状态变化列表
        - relationships_new: 新关系列表

        返回警告列表
        """
        warnings = []

        # v5.1 引入: 记录章节号用于 SQLite 同步
        self._pending_sqlite_data["chapter"] = chapter

        # 处理出场实体
        for entity in result.get("entities_appeared", []):
            entity_id = entity.get("id")
            entity_type = entity.get("type")
            if entity_id:
                self.update_entity_appearance(entity_id, chapter, entity_type)
                # v5.1 引入: 缓存用于 SQLite 同步
                self._pending_sqlite_data["entities_appeared"].append(entity)

        # 处理新实体
        for entity in result.get("entities_new", []):
            entity_id = entity.get("suggested_id") or entity.get("id")
            if entity_id and entity_id != "NEW":
                new_entity = EntityState(
                    id=entity_id,
                    name=entity.get("name", ""),
                    type=entity.get("type", "角色"),
                    tier=entity.get("tier", "装饰"),
                    aliases=entity.get("mentions", []),
                    first_appearance=chapter,
                    last_appearance=chapter
                )
                if not self.add_entity(new_entity):
                    warnings.append(f"实体已存在: {entity_id}")
                # v5.1 引入: 缓存用于 SQLite 同步
                self._pending_sqlite_data["entities_new"].append(entity)

        # 处理状态变化
        for change in result.get("state_changes", []):
            self.record_state_change(
                entity_id=change.get("entity_id", ""),
                field=change.get("field", ""),
                old_value=change.get("old"),
                new_value=change.get("new"),
                reason=change.get("reason", ""),
                chapter=chapter
            )
            # v5.1 引入: 缓存用于 SQLite 同步
            self._pending_sqlite_data["state_changes"].append(change)

        # 处理关系
        for rel in result.get("relationships_new", []):
            self.add_relationship(
                from_entity=rel.get("from", ""),
                to_entity=rel.get("to", ""),
                rel_type=rel.get("type", ""),
                description=rel.get("description", ""),
                chapter=chapter
            )
            # v5.1 引入: 缓存用于 SQLite 同步
            self._pending_sqlite_data["relationships_new"].append(rel)

        # 处理消歧不确定项（不影响实体写入，但必须对 Writer 可见）
        warnings.extend(self._record_disambiguation(chapter, result.get("uncertain", [])))

        # 写入 chapter_meta（钩子/模式/结束状态）
        chapter_meta = result.get("chapter_meta")
        if isinstance(chapter_meta, dict):
            meta_key = f"{int(chapter):04d}"
            self._state.setdefault("chapter_meta", {})
            self._state["chapter_meta"][meta_key] = chapter_meta
            self._pending_chapter_meta[meta_key] = chapter_meta

        # 更新进度
        self.update_progress(chapter)

        # 同步主角状态（entities_v3 → protagonist_state）
        self.sync_protagonist_from_entity()

        return warnings

    # ==================== 导出 ====================

    def export_for_context(self) -> Dict:
        """
        导出用于上下文的精简版状态。
        
        生成一个精简的状态快照，供 Context Agent 等模块使用。
        包含进度信息、实体扁平化视图、消歧警告和待确认项。
        
        返回:
            Dict: 精简版状态字典，包含以下字段：
                - progress: 写作进度信息
                - entities: 实体扁平化视图（ID 为键）
                - alias_index: 别名索引（v5.1 后为空，已迁移到 SQLite）
                - recent_changes: 最近变化记录（v5.1 后从 index.db 查询）
                - disambiguation: 消歧警告和待确认项
        """
        # 从 entities_v3 构建精简视图
        entities_flat = {}
        for type_name, entities in self._state.get("entities_v3", {}).items():
            for eid, e in entities.items():
                entities_flat[eid] = {
                    "name": e.get("canonical_name", eid),
                    "type": type_name,
                    "tier": e.get("tier", "装饰"),
                    "current": e.get("current", {})
                }

        return {
            "progress": self._state.get("progress", {}),
            "entities": entities_flat,
            # v5.1 引入: alias_index 已迁移到 index.db，这里返回空（兼容性）
            "alias_index": {},
            "recent_changes": [],  # v5.1 引入: 从 index.db 查询
            "disambiguation": {
                "warnings": self._state.get("disambiguation_warnings", [])[-self.config.export_disambiguation_slice:],
                "pending": self._state.get("disambiguation_pending", [])[-self.config.export_disambiguation_slice:],
            },
        }

    # ==================== 主角同步 ====================

    def get_protagonist_entity_id(self) -> Optional[str]:
        """
        获取主角实体 ID。
        
        通过以下方式查找主角：
        1. 通过 SQLStateManager 查询 is_protagonist 标记
        2. 通过 protagonist_state.name 查找别名匹配的实体
        
        返回:
            Optional[str]: 主角实体的唯一标识符，如果未找到则返回 None。
        """
        # 方式1: 通过 SQLStateManager 查询 (v5.1)
        if self._sql_state_manager:
            protagonist = self._sql_state_manager.get_protagonist()
            if protagonist:
                return protagonist.get("id")

        # 方式2: 通过 protagonist_state.name 查找别名
        protag_name = self._state.get("protagonist_state", {}).get("name")
        if protag_name and self._sql_state_manager:
            entities = self._sql_state_manager._index_manager.get_entities_by_alias(protag_name)
            for entry in entities:
                if entry.get("type") == "角色":
                    return entry.get("id")

        return None

    def sync_protagonist_from_entity(self, entity_id: str = None):
        """
        将主角实体的状态同步到 protagonist_state (v5.1: 从 SQLite 读取)

        用于确保 consistency-checker 等依赖 protagonist_state 的组件获取最新数据
        """
        if entity_id is None:
            entity_id = self.get_protagonist_entity_id()
        if entity_id is None:
            return

        entity = self.get_entity(entity_id, "角色")
        if not entity:
            return

        current = entity.get("current")
        if not isinstance(current, dict):
            current = entity.get("current_json", {})
        if isinstance(current, str):
            try:
                current = json.loads(current) if current else {}
            except (json.JSONDecodeError, TypeError):
                current = {}
        if not isinstance(current, dict):
            current = {}
        protag = self._state.setdefault("protagonist_state", {})

        # 同步境界
        if "realm" in current:
            power = protag.setdefault("power", {})
            power["realm"] = current["realm"]
            if "layer" in current:
                power["layer"] = current["layer"]

        # 同步位置
        if "location" in current:
            loc = protag.setdefault("location", {})
            loc["current"] = current["location"]
            if "last_chapter" in current:
                loc["last_chapter"] = current["last_chapter"]

    def sync_protagonist_to_entity(self, entity_id: str = None):
        """
        将 protagonist_state 同步到实体数据中的主角实体。
        
        用于初始化或手动编辑 protagonist_state 后保持一致性。
        会将 protagonist_state 中的境界、位置等信息同步到实体记录中。
        
        参数:
            entity_id: 主角实体的唯一标识符，可选。如果未指定则自动查找。
        """
        if entity_id is None:
            entity_id = self.get_protagonist_entity_id()
        if entity_id is None:
            return

        protag = self._state.get("protagonist_state", {})
        if not protag:
            return

        updates = {}

        # 同步境界
        power = protag.get("power", {})
        if power.get("realm"):
            updates["realm"] = power["realm"]
        if power.get("layer"):
            updates["layer"] = power["layer"]

        # 同步位置
        loc = protag.get("location", {})
        if loc.get("current"):
            updates["location"] = loc["current"]

        if updates:
            self.update_entity(entity_id, updates, "角色")


# ==================== CLI 接口 ====================

def main():
    import argparse
    import sys
    from pydantic import ValidationError
    from .cli_output import print_success, print_error
    from .cli_args import normalize_global_project_root, load_json_arg
    from .schemas import validate_data_agent_output, format_validation_error, normalize_data_agent_output
    from .index_manager import IndexManager

    parser = argparse.ArgumentParser(description="State Manager CLI (v5.4)")
    parser.add_argument("--project-root", type=str, help="项目根目录")

    subparsers = parser.add_subparsers(dest="command")

    # 读取进度
    subparsers.add_parser("get-progress")

    # 获取实体
    get_entity_parser = subparsers.add_parser("get-entity")
    get_entity_parser.add_argument("--id", required=True)

    # 列出实体
    list_parser = subparsers.add_parser("list-entities")
    list_parser.add_argument("--type", help="按类型过滤")
    list_parser.add_argument("--tier", help="按层级过滤")

    # 处理章节结果
    process_parser = subparsers.add_parser("process-chapter")
    process_parser.add_argument("--chapter", type=int, required=True, help="章节号")
    process_parser.add_argument("--data", required=True, help="JSON 格式的处理结果")

    argv = normalize_global_project_root(sys.argv[1:])
    args = parser.parse_args(argv)
    command_started_at = time.perf_counter()

    # 初始化
    config = None
    if args.project_root:
        # 允许传入“工作区根目录”，统一解析到真正的 book project_root（必须包含 .webnovel/state.json）
        from project_locator import resolve_project_root
        from .config import DataModulesConfig

        resolved_root = resolve_project_root(args.project_root)
        config = DataModulesConfig.from_project_root(resolved_root)

    manager = StateManager(config)
    logger = IndexManager(config)
    tool_name = f"state_manager:{args.command or 'unknown'}"

    def _append_timing(success: bool, *, error_code: str | None = None, error_message: str | None = None, chapter: int | None = None):
        elapsed_ms = int((time.perf_counter() - command_started_at) * 1000)
        safe_append_perf_timing(
            manager.config.project_root,
            tool_name=tool_name,
            success=success,
            elapsed_ms=elapsed_ms,
            chapter=chapter,
            error_code=error_code,
            error_message=error_message,
        )

    def emit_success(data=None, message: str = "ok", chapter: int | None = None):
        print_success(data, message=message)
        safe_log_tool_call(logger, tool_name=tool_name, success=True)
        _append_timing(True, chapter=chapter)

    def emit_error(code: str, message: str, suggestion: str | None = None, chapter: int | None = None):
        print_error(code, message, suggestion=suggestion)
        safe_log_tool_call(
            logger,
            tool_name=tool_name,
            success=False,
            error_code=code,
            error_message=message,
        )
        _append_timing(False, error_code=code, error_message=message, chapter=chapter)

    if args.command == "get-progress":
        emit_success(manager._state.get("progress", {}), message="progress")

    elif args.command == "get-entity":
        entity = manager.get_entity(args.id)
        if entity:
            emit_success(entity, message="entity")
        else:
            emit_error("NOT_FOUND", f"未找到实体: {args.id}")

    elif args.command == "list-entities":
        if args.type:
            entities = manager.get_entities_by_type(args.type)
        elif args.tier:
            entities = manager.get_entities_by_tier(args.tier)
        else:
            entities = manager.get_all_entities()

        payload = [{"id": eid, **e} for eid, e in entities.items()]
        emit_success(payload, message="entities")

    elif args.command == "process-chapter":
        data = load_json_arg(args.data)
        validated = None
        last_exc = None
        for _ in range(3):
            try:
                validated = validate_data_agent_output(data)
                break
            except ValidationError as exc:
                last_exc = exc
                data = normalize_data_agent_output(data)
        if validated is None:
            err = format_validation_error(last_exc) if last_exc else {
                "code": "SCHEMA_VALIDATION_FAILED",
                "message": "数据结构校验失败",
                "details": {"errors": []},
                "suggestion": "请检查 data-agent 输出字段是否完整且类型正确",
            }
            emit_error(err["code"], err["message"], suggestion=err.get("suggestion"))
            return

        warnings = manager.process_chapter_result(args.chapter, validated.model_dump(by_alias=True))
        manager.save_state()
        emit_success({"chapter": args.chapter, "warnings": warnings}, message="chapter_processed", chapter=args.chapter)

    else:
        emit_error("UNKNOWN_COMMAND", "未指定有效命令", suggestion="请查看 --help")


if __name__ == "__main__":
    if sys.platform == "win32":
        enable_windows_utf8_stdio()
    main()
