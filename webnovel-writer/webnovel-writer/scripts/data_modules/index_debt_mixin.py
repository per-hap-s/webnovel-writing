#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndexDebtMixin extracted from IndexManager.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from .index_manager import ChaseDebtMeta, OverrideContractMeta


class IndexDebtMixin:
    def create_override_contract(self, contract: "OverrideContractMeta") -> int:
        """
        创建或更新 Override Contract

        使用 SQLite 的 INSERT ... ON CONFLICT ... DO UPDATE 实现原子 UPSERT：
        - 并发安全，无需显式锁
        - 保持 id 不变，避免 chase_debt.override_contract_id 悬挂
        - 完全冻结终态：已 fulfilled/cancelled 的合约所有字段都不会被修改

        兼容性：支持 SQLite 3.24+（ON CONFLICT 语法），不依赖 RETURNING（3.35+）

        返回合约 ID
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 使用 ON CONFLICT 实现原子 UPSERT（SQLite 3.24+）
            # 终态完全冻结：fulfilled/cancelled 状态下所有字段都保持不变
            cursor.execute(
                """
                INSERT INTO override_contracts
                (chapter, constraint_type, constraint_id, rationale_type,
                 rationale_text, payback_plan, due_chapter, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chapter, constraint_type, constraint_id) DO UPDATE SET
                    rationale_type = CASE
                        WHEN override_contracts.status IN ('fulfilled', 'cancelled')
                        THEN override_contracts.rationale_type
                        ELSE excluded.rationale_type
                    END,
                    rationale_text = CASE
                        WHEN override_contracts.status IN ('fulfilled', 'cancelled')
                        THEN override_contracts.rationale_text
                        ELSE excluded.rationale_text
                    END,
                    payback_plan = CASE
                        WHEN override_contracts.status IN ('fulfilled', 'cancelled')
                        THEN override_contracts.payback_plan
                        ELSE excluded.payback_plan
                    END,
                    due_chapter = CASE
                        WHEN override_contracts.status IN ('fulfilled', 'cancelled')
                        THEN override_contracts.due_chapter
                        ELSE excluded.due_chapter
                    END,
                    status = CASE
                        WHEN override_contracts.status IN ('fulfilled', 'cancelled')
                        THEN override_contracts.status
                        ELSE excluded.status
                    END
            """,
                (
                    contract.chapter,
                    contract.constraint_type,
                    contract.constraint_id,
                    contract.rationale_type,
                    contract.rationale_text,
                    contract.payback_plan,
                    contract.due_chapter,
                    contract.status,
                ),
            )

            # 不使用 RETURNING（需要 SQLite 3.35+），改用查询获取 id
            cursor.execute(
                """
                SELECT id FROM override_contracts
                WHERE chapter = ? AND constraint_type = ? AND constraint_id = ?
            """,
                (contract.chapter, contract.constraint_type, contract.constraint_id),
            )
            row = cursor.fetchone()
            if not row:
                # UPSERT 后查不到记录是异常情况，不应发生
                raise RuntimeError(
                    f"Override Contract UPSERT 后无法获取 id: "
                    f"chapter={contract.chapter}, type={contract.constraint_type}, "
                    f"id={contract.constraint_id}"
                )
            contract_id = row[0]

            conn.commit()
            return contract_id

    def get_pending_overrides(self, before_chapter: int = None) -> List[Dict]:
        """
        获取待偿还的 Override Contracts。
        
        查询状态为 pending 的合约，可选择只返回截止章节在指定章节之前的合约。
        
        参数:
            before_chapter: 截止章节上限，可选。如果指定，只返回 due_chapter <= before_chapter 的合约。
            
        返回:
            List[Dict]: 待偿还合约列表，按截止章节升序排列。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            if before_chapter:
                cursor.execute(
                    """
                    SELECT * FROM override_contracts
                    WHERE status = 'pending' AND due_chapter <= ?
                    ORDER BY due_chapter ASC
                """,
                    (before_chapter,),
                )
            else:
                cursor.execute("""
                    SELECT * FROM override_contracts
                    WHERE status = 'pending'
                    ORDER BY due_chapter ASC
                """)
            return [dict(row) for row in cursor.fetchall()]

    def get_overdue_overrides(self, current_chapter: int) -> List[Dict]:
        """
        获取已逾期的 Override Contracts。
        
        查询状态为 pending 且截止章节小于当前章节的合约。
        
        参数:
            current_chapter: 当前章节号。
            
        返回:
            List[Dict]: 逾期合约列表，按截止章节升序排列。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM override_contracts
                WHERE status = 'pending' AND due_chapter < ?
                ORDER BY due_chapter ASC
            """,
                (current_chapter,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def fulfill_override(self, contract_id: int) -> bool:
        """
        标记 Override Contract 为已偿还。
        
        将合约状态更新为 fulfilled，并记录偿还时间。
        
        参数:
            contract_id: 合约 ID。
            
        返回:
            bool: 更新成功返回 True，合约不存在返回 False。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE override_contracts SET
                    status = 'fulfilled',
                    fulfilled_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (contract_id,),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_chapter_overrides(self, chapter: int) -> List[Dict]:
        """
        获取某章创建的 Override Contracts。
        
        查询指定章节中创建的所有合约记录。
        
        参数:
            chapter: 章节号。
            
        返回:
            List[Dict]: 合约列表。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM override_contracts WHERE chapter = ?
            """,
                (chapter,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ==================== v5.3 追读力债务操作 ====================

    def create_debt(self, debt: "ChaseDebtMeta") -> int:
        """
        创建追读力债务

        返回债务 ID
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO chase_debt
                (debt_type, original_amount, current_amount, interest_rate,
                 source_chapter, due_chapter, override_contract_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    debt.debt_type,
                    debt.original_amount,
                    debt.current_amount,
                    debt.interest_rate,
                    debt.source_chapter,
                    debt.due_chapter,
                    debt.override_contract_id if debt.override_contract_id else None,
                    debt.status,
                ),
            )
            conn.commit()
            debt_id = cursor.lastrowid

            # 记录创建事件
            self._record_debt_event(
                cursor,
                debt_id,
                "created",
                debt.original_amount,
                debt.source_chapter,
                f"创建债务: {debt.debt_type}",
            )
            conn.commit()
            return debt_id

    def get_active_debts(self) -> List[Dict]:
        """
        获取所有活跃债务。
        
        查询状态为 active 的债务记录，按截止章节升序排列。
        
        返回:
            List[Dict]: 活跃债务列表。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM chase_debt
                WHERE status = 'active'
                ORDER BY due_chapter ASC
            """)
            return [dict(row) for row in cursor.fetchall()]

    def get_overdue_debts(self, current_chapter: int) -> List[Dict]:
        """
        获取已逾期的债务。
        
        查询状态为 overdue 的债务，以及状态为 active 但截止章节已过的债务。
        
        参数:
            current_chapter: 当前章节号。
            
        返回:
            List[Dict]: 逾期债务列表，按截止章节升序排列。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM chase_debt
                WHERE (status = 'overdue')
                   OR (status = 'active' AND due_chapter < ?)
                ORDER BY due_chapter ASC
            """,
                (current_chapter,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_total_debt_balance(self) -> float:
        """
        获取总债务余额。
        
        计算所有 active 和 overdue 状态债务的当前金额总和。
        
        返回:
            float: 总债务余额。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(current_amount), 0) FROM chase_debt
                WHERE status IN ('active', 'overdue')
            """)
            return cursor.fetchone()[0]

    def accrue_interest(self, current_chapter: int) -> Dict[str, Any]:
        """
        计算利息（每章调用一次）。
        
        对 active 和 overdue 状态的债务计算利息，使用 debt_events 表防止同一章重复计息。
        同时检查债务是否逾期并更新状态。
        
        参数:
            current_chapter: 当前章节号。
            
        返回:
            Dict[str, Any]: 计息结果，包含以下字段：
                - debts_processed: 处理的债务数量
                - total_interest: 总利息金额
                - new_overdues: 新逾期的债务数量
                - skipped_already_processed: 跳过的已计息债务数量
        """
        result = {
            "debts_processed": 0,
            "total_interest": 0.0,
            "new_overdues": 0,
            "skipped_already_processed": 0,
        }

        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 获取所有未偿还债务（active + overdue 都继续计息）
            cursor.execute("""
                SELECT * FROM chase_debt WHERE status IN ('active', 'overdue')
            """)
            debts = cursor.fetchall()

            for debt in debts:
                debt_id = debt["id"]
                current_amount = debt["current_amount"]
                interest_rate = debt["interest_rate"]
                due_chapter = debt["due_chapter"]
                debt_status = debt["status"]

                # 检查本章是否已计息（防止重复调用）
                cursor.execute(
                    """
                    SELECT 1 FROM debt_events
                    WHERE debt_id = ? AND chapter = ? AND event_type = 'interest_accrued'
                """,
                    (debt_id, current_chapter),
                )
                if cursor.fetchone():
                    result["skipped_already_processed"] += 1
                    continue

                # 计算利息
                interest = current_amount * interest_rate
                new_amount = current_amount + interest

                # 更新债务
                cursor.execute(
                    """
                    UPDATE chase_debt SET
                        current_amount = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (new_amount, debt_id),
                )

                # 记录利息事件
                self._record_debt_event(
                    cursor,
                    debt_id,
                    "interest_accrued",
                    interest,
                    current_chapter,
                    f"利息: {interest:.2f} (利率: {interest_rate * 100:.0f}%)",
                )

                result["debts_processed"] += 1
                result["total_interest"] += interest

                # 检查是否逾期（仅对 active 状态的债务）
                if debt_status == "active" and current_chapter > due_chapter:
                    cursor.execute(
                        """
                        UPDATE chase_debt SET status = 'overdue'
                        WHERE id = ? AND status = 'active'
                    """,
                        (debt_id,),
                    )
                    if cursor.rowcount > 0:
                        result["new_overdues"] += 1
                        self._record_debt_event(
                            cursor,
                            debt_id,
                            "overdue",
                            new_amount,
                            current_chapter,
                            f"债务逾期 (截止: 第{due_chapter}章)",
                        )

            conn.commit()

        return result

    def pay_debt(self, debt_id: int, amount: float, chapter: int) -> Dict[str, Any]:
        """
        偿还债务。
        
        支持部分偿还和完全偿还。完全偿还时，使用原子 UPDATE 检查并标记关联 Override 为 fulfilled。
        并发安全：用 NOT EXISTS 子查询确保所有债务都已清零。
        
        参数:
            debt_id: 债务 ID。
            amount: 偿还金额，必须大于 0。
            chapter: 偿还发生的章节号。
            
        返回:
            Dict[str, Any]: 偿还结果，包含以下字段：
                - remaining: 剩余债务金额
                - fully_paid: 是否完全偿还
                - override_fulfilled: 关联的 Override 是否被标记为 fulfilled
                - error: 错误信息（如果发生错误）
        """
        # 校验偿还金额
        if amount <= 0:
            return {
                "remaining": 0,
                "fully_paid": False,
                "error": "偿还金额必须大于0",
            }

        with self._get_conn() as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT current_amount, override_contract_id FROM chase_debt WHERE id = ?",
                (debt_id,),
            )
            row = cursor.fetchone()
            if not row:
                return {"remaining": 0, "fully_paid": False, "error": "债务不存在"}

            current = row["current_amount"]
            override_contract_id = row["override_contract_id"]
            remaining = max(0, current - amount)
            override_fulfilled = False

            if remaining == 0:
                # 完全偿还
                cursor.execute(
                    """
                    UPDATE chase_debt SET
                        current_amount = 0,
                        status = 'paid',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (debt_id,),
                )
                self._record_debt_event(
                    cursor, debt_id, "full_payment", amount, chapter, "债务已完全偿还"
                )

                # 原子检查并标记 Override 为 fulfilled
                # 使用 NOT EXISTS 子查询确保并发安全：只有当确实没有未清债务时才更新
                if override_contract_id:
                    cursor.execute(
                        """
                        UPDATE override_contracts SET
                            status = 'fulfilled',
                            fulfilled_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                          AND status = 'pending'
                          AND NOT EXISTS (
                              SELECT 1 FROM chase_debt
                              WHERE override_contract_id = ?
                                AND status IN ('active', 'overdue')
                          )
                    """,
                        (override_contract_id, override_contract_id),
                    )
                    if cursor.rowcount > 0:
                        override_fulfilled = True
            else:
                # 部分偿还
                cursor.execute(
                    """
                    UPDATE chase_debt SET
                        current_amount = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """,
                    (remaining, debt_id),
                )
                self._record_debt_event(
                    cursor,
                    debt_id,
                    "partial_payment",
                    amount,
                    chapter,
                    f"部分偿还，剩余: {remaining:.2f}",
                )

            conn.commit()
            return {
                "remaining": remaining,
                "fully_paid": remaining == 0,
                "override_fulfilled": override_fulfilled,
            }

    def _record_debt_event(
        self,
        cursor,
        debt_id: int,
        event_type: str,
        amount: float,
        chapter: int,
        note: str = "",
    ):
        """记录债务事件（内部方法）"""
        cursor.execute(
            """
            INSERT INTO debt_events (debt_id, event_type, amount, chapter, note)
            VALUES (?, ?, ?, ?, ?)
        """,
            (debt_id, event_type, amount, chapter, note),
        )

    def get_debt_history(self, debt_id: int) -> List[Dict]:
        """
        获取债务的事件历史。
        
        查询指定债务的所有事件记录，包括创建、计息、偿还等。
        
        参数:
            debt_id: 债务 ID。
            
        返回:
            List[Dict]: 事件记录列表，按创建时间升序排列。
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM debt_events
                WHERE debt_id = ?
                ORDER BY created_at ASC
            """,
                (debt_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ==================== v5.3 章节追读力元数据操作 ====================

    def get_debt_summary(self) -> Dict[str, Any]:
        """
        获取债务汇总信息。
        
        统计活跃债务、逾期债务的数量和金额，以及待偿还的 Override 数量。
        
        返回:
            Dict[str, Any]: 汇总信息字典，包含以下字段：
                - active_debts: 活跃债务数量
                - active_total: 活跃债务总金额
                - overdue_debts: 逾期债务数量
                - overdue_total: 逾期债务总金额
                - pending_overrides: 待偿还 Override 数量
                - total_balance: 总债务余额
        """
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 活跃债务
            cursor.execute("""
                SELECT COUNT(*) as count, COALESCE(SUM(current_amount), 0) as total
                FROM chase_debt WHERE status = 'active'
            """)
            active = cursor.fetchone()

            # 逾期债务
            cursor.execute("""
                SELECT COUNT(*) as count, COALESCE(SUM(current_amount), 0) as total
                FROM chase_debt WHERE status = 'overdue'
            """)
            overdue = cursor.fetchone()

            # 待偿还Override
            cursor.execute("""
                SELECT COUNT(*) FROM override_contracts WHERE status = 'pending'
            """)
            pending_overrides = cursor.fetchone()[0]

            return {
                "active_debts": active["count"],
                "active_total": active["total"],
                "overdue_debts": overdue["count"],
                "overdue_total": overdue["total"],
                "pending_overrides": pending_overrides,
                "total_balance": active["total"] + overdue["total"],
            }

    # ==================== 批量操作 ====================

