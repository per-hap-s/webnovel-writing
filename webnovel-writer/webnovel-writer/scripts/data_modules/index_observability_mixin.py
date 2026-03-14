#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndexObservabilityMixin extracted from IndexManager.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    import sqlite3


logger = logging.getLogger(__name__)


class IndexObservabilityMixin:
    def _row_to_dict(self, row: "sqlite3.Row", parse_json: Optional[List[str]] = None) -> Dict:
        """
        将 SQLite Row 对象转换为字典。
        
        可选择性地将指定字段从 JSON 字符串解析为 Python 对象。
        
        参数:
            row: SQLite Row 对象。
            parse_json: 需要解析为 JSON 的字段名列表，可选。
            
        返回:
            Dict: 转换后的字典。
        """
        d = dict(row)
        if parse_json:
            for key in parse_json:
                if key in d and d[key]:
                    try:
                        d[key] = json.loads(d[key])
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "failed to parse JSON field %s in _row_to_dict: %s",
                            key,
                            exc,
                        )
        return d

    # ==================== 无效事实管理 ====================

    def mark_invalid_fact(
        self,
        source_type: str,
        source_id: str,
        reason: str,
        marked_by: str = "user",
        chapter_discovered: Optional[int] = None,
    ) -> int:
        """
        标记无效事实。
        
        将识别出的无效事实记录到数据库，状态默认为 pending。
        用于追踪需要人工确认的数据问题。
        
        参数:
            source_type: 事实来源类型（如 entity、relationship 等）。
            source_id: 事实的唯一标识符。
            reason: 标记为无效的原因说明。
            marked_by: 标记者标识，默认为 "user"。
            chapter_discovered: 发现问题的章节号，可选。
            
        返回:
            int: 新创建的记录 ID。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO invalid_facts
                (source_type, source_id, reason, status, marked_by, chapter_discovered)
                VALUES (?, ?, ?, 'pending', ?, ?)
            """,
                (source_type, str(source_id), reason, marked_by, chapter_discovered),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def resolve_invalid_fact(self, invalid_id: int, action: str) -> bool:
        """
        确认或撤销无效标记。
        
        对无效事实标记进行处理：确认则更新状态为 confirmed，撤销则删除记录。
        
        参数:
            invalid_id: 无效事实记录的 ID。
            action: 操作类型，可选值为 "confirm"（确认）或 "dismiss"（撤销）。
            
        返回:
            bool: 操作成功返回 True，操作类型无效或记录不存在返回 False。
        """
        action = action.lower()
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if action == "confirm":
                cursor.execute(
                    """
                    UPDATE invalid_facts
                    SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (invalid_id,),
                )
            elif action == "dismiss":
                cursor.execute("DELETE FROM invalid_facts WHERE id = ?", (invalid_id,))
            else:
                return False
            conn.commit()
            return cursor.rowcount > 0

    def list_invalid_facts(self, status: Optional[str] = None) -> List[Dict]:
        """
        列出无效事实记录。
        
        查询所有或指定状态的无效事实标记。
        
        参数:
            status: 状态过滤，可选值为 "pending" 或 "confirmed"。如果未指定则返回所有记录。
            
        返回:
            List[Dict]: 无效事实记录列表，按 ID 降序排列。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT * FROM invalid_facts WHERE status = ? ORDER BY id DESC",
                    (status,),
                )
            else:
                cursor.execute("SELECT * FROM invalid_facts ORDER BY id DESC")
            return [dict(r) for r in cursor.fetchall()]

    def get_invalid_ids(self, source_type: str, status: str = "confirmed") -> set[str]:
        """
        获取无效事实 ID 集合。
        
        查询指定来源类型和状态的所有无效事实 ID，用于过滤无效数据。
        
        参数:
            source_type: 事实来源类型。
            status: 状态过滤，默认为 "confirmed"。
            
        返回:
            set[str]: 无效事实 ID 集合。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT source_id FROM invalid_facts WHERE source_type = ? AND status = ?",
                (source_type, status),
            )
            return {str(r[0]) for r in cursor.fetchall() if r and r[0] is not None}

    # ==================== 日志记录 ====================

    def log_rag_query(
        self,
        query: str,
        query_type: str,
        results_count: int,
        hit_sources: Optional[str] = None,
        latency_ms: Optional[int] = None,
        chapter: Optional[int] = None,
    ) -> None:
        """
        记录 RAG 查询日志。
        
        将检索查询的详细信息写入日志表，用于性能分析和问题排查。
        
        参数:
            query: 查询文本。
            query_type: 查询类型（如 vector、bm25、hybrid 等）。
            results_count: 返回结果数量。
            hit_sources: 命中来源的 JSON 统计，可选。
            latency_ms: 查询耗时（毫秒），可选。
            chapter: 关联的章节号，可选。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO rag_query_log
                (query, query_type, results_count, hit_sources, latency_ms, chapter)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (query, query_type, results_count, hit_sources, latency_ms, chapter),
            )
            conn.commit()

    def log_tool_call(
        self,
        tool_name: str,
        success: bool,
        retry_count: int = 0,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        chapter: Optional[int] = None,
    ) -> None:
        """
        记录工具调用日志。
        
        将工具调用的执行情况写入日志表，用于监控和问题排查。
        
        参数:
            tool_name: 工具名称。
            success: 是否执行成功。
            retry_count: 重试次数，默认为 0。
            error_code: 错误码（如果失败），可选。
            error_message: 错误信息（如果失败），可选。
            chapter: 关联的章节号，可选。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tool_call_stats
                (tool_name, success, retry_count, error_code, error_message, chapter)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (tool_name, int(bool(success)), retry_count, error_code, error_message, chapter),
            )
            conn.commit()

    def get_stats(self) -> Dict[str, int]:
        """
        获取索引统计信息。
        
        返回数据库中各表的记录数量和关键指标，用于监控和诊断。
        
        返回:
            Dict[str, int]: 统计信息字典，包含以下字段：
                - chapters: 章节总数
                - scenes: 场景总数
                - appearances: 出场实体数
                - max_chapter: 最大章节号
                - entities: 实体总数
                - active_entities: 活跃实体数
                - aliases: 别名总数
                - state_changes: 状态变化记录数
                - relationships: 关系记录数
                - relationship_events: 关系事件数
                - override_contracts: Override 合约数
                - pending_overrides: 待偿还 Override 数
                - active_debts: 活跃债务数
                - total_debt: 总债务余额
                - reading_power_records: 追读力记录数
                - review_metrics: 审查记录数
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM chapters")
            chapters = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM scenes")
            scenes = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(DISTINCT entity_id) FROM appearances")
            appearances = cursor.fetchone()[0]

            cursor.execute("SELECT MAX(chapter) FROM chapters")
            max_chapter = cursor.fetchone()[0] or 0

            # v5.1 引入统计
            cursor.execute("SELECT COUNT(*) FROM entities")
            entities = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM entities WHERE is_archived = 0")
            active_entities = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM aliases")
            aliases = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM state_changes")
            state_changes = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM relationships")
            relationships = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM relationship_events")
            relationship_events = cursor.fetchone()[0]

            # v5.3 引入统计
            cursor.execute("SELECT COUNT(*) FROM override_contracts")
            override_contracts = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM override_contracts WHERE status = 'pending'"
            )
            pending_overrides = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM chase_debt WHERE status = 'active'")
            active_debts = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COALESCE(SUM(current_amount), 0) FROM chase_debt WHERE status IN ('active', 'overdue')"
            )
            total_debt = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM chapter_reading_power")
            reading_power_records = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM review_metrics")
            review_metrics = cursor.fetchone()[0]

            return {
                "chapters": chapters,
                "scenes": scenes,
                "appearances": appearances,
                "max_chapter": max_chapter,
                # v5.1 引入
                "entities": entities,
                "active_entities": active_entities,
                "aliases": aliases,
                "state_changes": state_changes,
                "relationships": relationships,
                "relationship_events": relationship_events,
                # v5.3 引入
                "override_contracts": override_contracts,
                "pending_overrides": pending_overrides,
                "active_debts": active_debts,
                "total_debt": total_debt,
                "reading_power_records": reading_power_records,
                "review_metrics": review_metrics,
            }


