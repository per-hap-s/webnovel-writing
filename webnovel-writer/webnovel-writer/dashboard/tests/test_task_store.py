"""
dashboard/task_store.py 的测试用例

测试任务存储的核心功能，包括任务创建、状态更新、事件追加、并发访问和数据持久化。
"""

import json
import multiprocessing
import threading
import time
from pathlib import Path

import pytest

from dashboard.task_store import TaskStore


def _update_task_process(task_id_str: str, project_root_str: str, index: int):
    """
    多进程测试辅助函数
    
    必须在模块级别定义以支持 Windows 上的 pickle 序列化。
    """
    from pathlib import Path
    from dashboard.task_store import TaskStore
    
    store = TaskStore(Path(project_root_str))
    max_retries = 10
    for attempt in range(max_retries):
        try:
            store.update_task(task_id_str, **{f"process_field_{index}": index})
            return
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.05)


@pytest.fixture
def task_store(tmp_path: Path) -> TaskStore:
    """
    创建隔离的任务存储实例

    使用临时目录作为项目根目录，确保测试之间相互隔离。
    """
    project_root = tmp_path / "novel"
    return TaskStore(project_root)


@pytest.fixture
def sample_workflow() -> dict:
    """
    创建示例工作流配置

    包含多个步骤的工作流定义，用于测试任务创建。
    """
    return {
        "name": "write",
        "version": 1,
        "steps": [
            {"name": "context", "type": "llm"},
            {"name": "draft", "type": "llm"},
            {"name": "polish", "type": "llm"},
        ],
    }


class TestTaskCreation:
    """
    测试任务创建功能
    """

    def test_create_task_basic(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试基本任务创建

        验证任务 ID 生成、初始状态设置和持久化。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)

        assert task["id"] is not None
        assert len(task["id"]) == 32
        assert task["task_type"] == "write"
        assert task["status"] == "queued"
        assert task["approval_status"] == "not_required"
        assert task["created_at"] is not None
        assert task["updated_at"] is not None
        assert task["started_at"] is None
        assert task["finished_at"] is None
        assert task["error"] is None

    def test_create_task_with_workflow_info(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试任务创建时保存工作流信息

        验证工作流名称、版本和步骤顺序被正确保存。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)

        assert task["workflow_name"] == "write"
        assert task["workflow_version"] == 1
        assert task["step_order"] == ["context", "draft", "polish"]

    def test_create_task_with_request_payload(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试任务创建时保存请求载荷

        验证请求数据被完整保存到任务记录中。
        """
        request = {"chapter": 5, "mode": "fast", "options": {"skip_review": True}}
        task = task_store.create_task("write", request, sample_workflow)

        assert task["request"]["chapter"] == 5
        assert task["request"]["mode"] == "fast"
        assert task["request"]["options"]["skip_review"] is True

    def test_create_task_persists_to_disk(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试任务持久化到磁盘

        验证任务数据被正确写入 JSON 文件。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)

        task_path = task_store._task_path(task["id"])
        assert task_path.is_file()

        loaded = json.loads(task_path.read_text(encoding="utf-8"))
        assert loaded["id"] == task["id"]
        assert loaded["task_type"] == "write"

    def test_create_task_appends_initial_event(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试任务创建时追加初始事件

        验证任务入队事件被正确记录。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)

        events = task_store.get_events(task["id"])
        assert len(events) == 1
        assert events[0]["level"] == "info"
        assert "队列" in events[0]["message"]


class TestTaskStatusUpdate:
    """
    测试任务状态更新功能
    """

    def test_mark_running(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试标记任务为运行中状态

        验证状态变更和时间戳更新。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        updated = task_store.mark_running(task["id"], "context")

        assert updated["status"] == "running"
        assert updated["current_step"] == "context"
        assert updated["started_at"] is not None

    def test_mark_running_preserves_started_at(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试重复标记运行中时保留原始开始时间

        验证 started_at 只在第一次设置。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        first = task_store.mark_running(task["id"], "context")
        second = task_store.mark_running(task["id"], "draft")

        assert first["started_at"] == second["started_at"]

    def test_mark_completed(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试标记任务为已完成状态

        验证完成状态和结束时间设置。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_store.mark_running(task["id"], "context")
        updated = task_store.mark_completed(task["id"])

        assert updated["status"] == "completed"
        assert updated["current_step"] is None
        assert updated["finished_at"] is not None

    def test_mark_failed(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试标记任务为失败状态

        验证失败状态、错误信息和结束时间设置。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_store.mark_running(task["id"], "context")
        error = {"code": "STEP_FAILED", "message": "步骤执行失败"}
        updated = task_store.mark_failed(task["id"], "context", error)

        assert updated["status"] == "failed"
        assert updated["current_step"] == "context"
        assert updated["finished_at"] is not None
        assert updated["error"]["code"] == "STEP_FAILED"

    def test_mark_rejected(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试标记任务为已拒绝状态

        验证拒绝状态、原因和审批状态设置。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        updated = task_store.mark_rejected(task["id"], "内容不符合要求")

        assert updated["status"] == "rejected"
        assert updated["approval_status"] == "rejected"
        assert updated["finished_at"] is not None
        assert updated["error"]["code"] == "WRITEBACK_REJECTED"
        assert "内容不符合要求" in updated["error"]["message"]

    def test_mark_waiting_for_approval(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试标记任务为等待审批状态

        验证审批状态和审批信息设置。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        approval = {
            "status": "pending",
            "requested_at": task["updated_at"],
            "summary": {"overall_score": 85},
        }
        updated = task_store.mark_waiting_for_approval(task["id"], "approval-gate", approval)

        assert updated["status"] == "awaiting_writeback_approval"
        assert updated["approval_status"] == "pending"
        assert updated["current_step"] == "approval-gate"
        assert updated["artifacts"]["approval"]["summary"]["overall_score"] == 85

    def test_mark_cancelled(self, task_store: TaskStore, sample_workflow: dict):
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_store.mark_running(task["id"], "draft")

        updated = task_store.mark_cancelled(task["id"], "draft", "任务已由用户停止。")

        assert updated["status"] == "interrupted"
        assert updated["current_step"] == "draft"
        assert updated["error"]["code"] == "TASK_CANCELLED"
        assert updated["error"]["retryable"] is False
        assert updated["finished_at"] is not None


class TestEventAppend:
    """
    测试事件追加功能
    """

    def test_append_event_basic(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试基本事件追加

        验证事件被正确创建和持久化。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        event = task_store.append_event(task["id"], "info", "步骤开始")

        assert event["id"] is not None
        assert event["task_id"] == task["id"]
        assert event["level"] == "info"
        assert event["message"] == "步骤开始"
        assert event["timestamp"] is not None

    def test_append_event_with_step_name(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试带步骤名称的事件追加

        验证步骤名称被正确记录。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        event = task_store.append_event(
            task["id"],
            "info",
            "步骤完成",
            step_name="context",
        )

        assert event["step_name"] == "context"

    def test_append_event_with_payload(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试带载荷的事件追加

        验证事件载荷被正确保存。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        payload = {"timing_ms": 1500, "tokens": 500}
        event = task_store.append_event(
            task["id"],
            "info",
            "步骤完成",
            payload=payload,
        )

        assert event["payload"]["timing_ms"] == 1500
        assert event["payload"]["tokens"] == 500

    def test_get_events_returns_in_order(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试事件按时间顺序返回

        验证事件列表按时间顺序排列。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_store.append_event(task["id"], "info", "事件1")
        task_store.append_event(task["id"], "info", "事件2")
        task_store.append_event(task["id"], "info", "事件3")

        events = task_store.get_events(task["id"])

        assert len(events) == 4
        assert events[1]["message"] == "事件1"
        assert events[2]["message"] == "事件2"
        assert events[3]["message"] == "事件3"

    def test_get_events_respects_limit(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试事件列表限制

        验证事件列表正确应用限制参数。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        for i in range(10):
            task_store.append_event(task["id"], "info", f"事件{i}")

        events = task_store.get_events(task["id"], limit=5)

        assert len(events) == 5


class TestStepResult:
    """
    测试步骤结果保存功能
    """

    def test_save_step_result(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试保存步骤结果

        验证步骤结果被正确保存到任务 artifacts 中。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        result = {"success": True, "output": "章节内容"}
        updated = task_store.save_step_result(task["id"], "context", result)

        assert updated["artifacts"]["step_results"]["context"]["success"] is True
        assert updated["artifacts"]["step_results"]["context"]["output"] == "章节内容"

    def test_save_multiple_step_results(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试保存多个步骤结果

        验证多个步骤结果被正确保存。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_store.save_step_result(task["id"], "context", {"success": True})
        task_store.save_step_result(task["id"], "draft", {"success": True, "word_count": 2000})

        loaded = task_store.get_task(task["id"])

        assert loaded["artifacts"]["step_results"]["context"]["success"] is True
        assert loaded["artifacts"]["step_results"]["draft"]["word_count"] == 2000


class TestTaskRetrieval:
    """
    测试任务检索功能
    """

    def test_get_task_existing(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试获取存在的任务

        验证任务数据被正确加载。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        loaded = task_store.get_task(task["id"])

        assert loaded is not None
        assert loaded["id"] == task["id"]
        assert loaded["task_type"] == "write"

    def test_get_task_nonexistent(self, task_store: TaskStore):
        """
        测试获取不存在的任务

        验证返回 None。
        """
        loaded = task_store.get_task("nonexistent-task-id")

        assert loaded is None

    def test_list_tasks(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试列出任务

        验证任务列表按创建时间倒序排列。
        """
        task1 = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        time.sleep(0.01)
        task2 = task_store.create_task("write", {"chapter": 2}, sample_workflow)
        time.sleep(0.01)
        task3 = task_store.create_task("plan", {"volume": "1"}, sample_workflow)

        tasks = task_store.list_tasks()

        assert len(tasks) == 3
        assert tasks[0]["id"] == task3["id"]
        assert tasks[1]["id"] == task2["id"]
        assert tasks[2]["id"] == task1["id"]

    def test_list_tasks_sorts_mixed_legacy_and_utc_timestamps(self, task_store: TaskStore, sample_workflow: dict):
        legacy = task_store.create_task("plan", {"volume": "1"}, sample_workflow)
        utc_task = task_store.create_task("write", {"chapter": 1}, sample_workflow)

        task_store.update_task(legacy["id"], created_at="2026-03-18T17:47:59", updated_at="2026-03-18T17:47:59")
        task_store.update_task(utc_task["id"], created_at="2026-03-18T09:53:14+00:00", updated_at="2026-03-18T09:53:14+00:00")

        tasks = task_store.list_tasks()

        assert tasks[0]["id"] == utc_task["id"]
        assert tasks[1]["id"] == legacy["id"]

    def test_list_tasks_with_limit(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试带限制的任务列表

        验证限制参数被正确应用。
        """
        created_tasks = []
        for i in range(10):
            created_tasks.append(task_store.create_task("write", {"chapter": i}, sample_workflow))

        tasks = task_store.list_tasks(limit=5)

        assert len(tasks) == 5
        assert [task["request"]["chapter"] for task in tasks] == [9, 8, 7, 6, 5]
        assert [task["id"] for task in tasks] == [item["id"] for item in reversed(created_tasks[-5:])]

    def test_list_tasks_empty(self, task_store: TaskStore):
        """
        测试空任务列表

        验证没有任务时返回空列表。
        """
        tasks = task_store.list_tasks()

        assert tasks == []


class TestUpdateTask:
    """
    测试任务更新功能
    """

    def test_update_task_basic(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试基本任务更新

        验证任务属性被正确更新。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        time.sleep(0.01)
        updated = task_store.update_task(task["id"], status="running", current_step="draft")

        assert updated["status"] == "running"
        assert updated["current_step"] == "draft"
        assert updated["updated_at"] != task["updated_at"]

    def test_update_task_nonexistent_raises_keyerror(self, task_store: TaskStore):
        """
        测试更新不存在的任务抛出 KeyError

        验证错误处理。
        """
        with pytest.raises(KeyError):
            task_store.update_task("nonexistent", status="running")

    def test_reset_for_retry(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试重置任务以供重试

        验证任务状态被正确重置。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_store.mark_running(task["id"], "context")
        task_store.save_step_result(task["id"], "context", {"success": False, "error": {"code": "ERROR"}})
        task_store.save_step_result(task["id"], "draft", {"success": True})
        task_store.mark_failed(task["id"], "context", {"code": "ERROR"})

        reset = task_store.reset_for_retry(task["id"])

        assert reset["status"] == "queued"
        assert reset["approval_status"] == "not_required"
        assert reset["current_step"] is None
        assert reset["finished_at"] is None
        assert reset["error"] is None
        assert "context" not in reset["artifacts"]["step_results"]
        assert reset["artifacts"]["step_results"]["draft"]["success"] is True
        assert reset["artifacts"]["approval"] == {}


class TestConcurrentAccess:
    """
    测试并发访问功能
    """

    def test_concurrent_task_creation(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试并发任务创建

        验证多线程环境下任务创建的正确性。
        """
        created_ids = []
        lock = threading.Lock()

        def create_task():
            task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
            with lock:
                created_ids.append(task["id"])

        threads = [threading.Thread(target=create_task) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(created_ids) == 10
        assert len(set(created_ids)) == 10

    def test_concurrent_event_append(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试并发事件追加

        验证多线程环境下事件追加的正确性。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)

        def append_event(i):
            task_store.append_event(task["id"], "info", f"事件{i}")

        threads = [threading.Thread(target=append_event, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        events = task_store.get_events(task["id"])
        assert len(events) == 51


class TestDataPersistence:
    """
    测试数据持久化功能
    """

    def test_task_persistence_across_restarts(self, tmp_path: Path, sample_workflow: dict):
        """
        测试任务在存储实例重启后持久化

        验证任务数据在重新创建存储实例后仍然可用。
        """
        project_root = tmp_path / "novel"
        store1 = TaskStore(project_root)
        task = store1.create_task("write", {"chapter": 1}, sample_workflow)
        store1.save_step_result(task["id"], "context", {"success": True})

        store2 = TaskStore(project_root)
        loaded = store2.get_task(task["id"])

        assert loaded is not None
        assert loaded["artifacts"]["step_results"]["context"]["success"] is True

    def test_event_persistence_across_restarts(self, tmp_path: Path, sample_workflow: dict):
        """
        测试事件在存储实例重启后持久化

        验证事件数据在重新创建存储实例后仍然可用。
        """
        project_root = tmp_path / "novel"
        store1 = TaskStore(project_root)
        task = store1.create_task("write", {"chapter": 1}, sample_workflow)
        store1.append_event(task["id"], "info", "测试事件")

        store2 = TaskStore(project_root)
        events = store2.get_events(task["id"])

        assert len(events) == 2
        assert events[1]["message"] == "测试事件"


class TestEdgeCases:
    """
    测试边界条件
    """

    def test_create_task_with_empty_workflow(self, task_store: TaskStore):
        """
        测试使用空工作流创建任务

        验证空工作流的处理。
        """
        task = task_store.create_task("custom", {}, {})

        assert task["workflow_name"] == "custom"
        assert task["step_order"] == []

    def test_create_task_with_none_values_in_request(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试请求中包含 None 值

        验证 None 值被正确处理。
        """
        request = {"chapter": None, "volume": None, "options": None}
        task = task_store.create_task("write", request, sample_workflow)

        assert task["request"]["chapter"] is None
        assert task["request"]["volume"] is None

    def test_get_events_for_nonexistent_task(self, task_store: TaskStore):
        """
        测试获取不存在任务的事件

        验证返回空列表。
        """
        events = task_store.get_events("nonexistent")

        assert events == []

    def test_append_event_with_empty_message(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试追加空消息事件

        验证空消息被正确处理。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        event = task_store.append_event(task["id"], "info", "")

        assert event["message"] == ""

    def test_update_task_with_empty_dict(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试使用空字典更新任务

        验证只更新时间戳。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        original_status = task["status"]
        time.sleep(0.01)
        updated = task_store.update_task(task["id"])

        assert updated["status"] == original_status
        assert updated["updated_at"] != task["updated_at"]

    def test_corrupted_task_file_handling(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试损坏的任务文件处理

        验证损坏的 JSON 文件被正确跳过。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_path = task_store._task_path(task["id"])
        task_path.write_text("invalid json content", encoding="utf-8")

        loaded = task_store.get_task(task["id"])

        assert loaded is None

    def test_corrupted_event_file_handling(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试损坏的事件文件处理

        验证损坏的 JSON 行被正确跳过。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        events_path = task_store._events_path(task["id"])
        events_path.write_text(
            '{"id": "1", "message": "valid"}\ninvalid line\n{"id": "2", "message": "also valid"}\n',
            encoding="utf-8",
        )

        events = task_store.get_events(task["id"])

        assert len(events) == 2


class TestConcurrentWriteSafety:
    """
    测试并发写入安全性
    """

    def test_concurrent_task_updates_no_data_loss(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试并发任务更新不会导致数据丢失
        
        验证多线程同时更新同一任务时，所有更新都能正确保存。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_id = task["id"]
        
        update_count = 20
        errors = []
        lock = threading.Lock()
        
        def update_task_with_retry(index: int):
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    task_store.update_task(task_id, **{f"custom_field_{index}": index})
                    return
                except Exception as e:
                    if attempt == max_retries - 1:
                        with lock:
                            errors.append((index, str(e)))
                    time.sleep(0.01)
        
        threads = [threading.Thread(target=update_task_with_retry, args=(i,)) for i in range(update_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"更新失败: {errors}"
        
        final_task = task_store.get_task(task_id)
        for i in range(update_count):
            assert final_task.get(f"custom_field_{i}") == i, f"字段 custom_field_{i} 丢失或值不正确"

    def test_concurrent_step_result_saves(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试并发步骤结果保存
        
        验证多线程同时保存不同步骤结果时，所有结果都能正确保存。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_id = task["id"]
        
        step_count = 10
        errors = []
        lock = threading.Lock()
        
        def save_step(index: int):
            try:
                result = {"step_index": index, "data": f"step_data_{index}"}
                task_store.save_step_result(task_id, f"step_{index}", result)
            except Exception as e:
                with lock:
                    errors.append((index, str(e)))
        
        threads = [threading.Thread(target=save_step, args=(i,)) for i in range(step_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"保存失败: {errors}"
        
        final_task = task_store.get_task(task_id)
        step_results = final_task.get("artifacts", {}).get("step_results", {})
        assert len(step_results) == step_count, f"期望 {step_count} 个步骤结果，实际 {len(step_results)} 个"

    def test_high_concurrency_event_append(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试高并发事件追加
        
        验证大量并发事件追加时不会丢失事件。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_id = task["id"]
        
        event_count = 100
        errors = []
        lock = threading.Lock()
        
        def append_event(index: int):
            try:
                task_store.append_event(task_id, "info", f"事件_{index}")
            except Exception as e:
                with lock:
                    errors.append((index, str(e)))
        
        threads = [threading.Thread(target=append_event, args=(i,)) for i in range(event_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"事件追加失败: {errors}"
        
        events = task_store.get_events(task_id, limit=500)
        assert len(events) == event_count + 1

    def test_lock_health_check(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试锁健康检查功能
        
        验证锁健康检查能正确报告状态。
        """
        health = task_store.check_lock_health()
        
        assert health["healthy"] is True
        assert health["active_locks_count"] == 0
        assert health["stale_locks"] == []

    def test_lock_health_detects_potential_leak(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试锁健康检查能检测潜在泄漏
        
        验证锁健康检查能识别长时间持有的锁。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_id = task["id"]
        
        lock_path = task_store._locks_dir / f"{task_id}.lock"
        lock_key = f"task:{task_id}:test"
        
        task_store._register_lock_acquire(lock_key, lock_path)
        
        health = task_store.check_lock_health()
        assert health["active_locks_count"] == 1
        
        task_store._register_lock_release(lock_key)
        
        health = task_store.check_lock_health()
        assert health["active_locks_count"] == 0
        assert health["healthy"] is True

    def test_cleanup_stale_locks(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试清理过期锁文件
        
        验证过期锁文件能被正确清理。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        
        stale_lock_path = task_store._locks_dir / "stale_test.lock"
        stale_lock_path.write_text("", encoding="utf-8")
        
        import os
        import time
        old_time = time.time() - 100
        os.utime(stale_lock_path, (old_time, old_time))
        
        cleaned = task_store.cleanup_stale_locks()
        
        assert cleaned >= 1
        assert not stale_lock_path.exists()

    def test_multiprocess_concurrent_write(self, tmp_path: Path, sample_workflow: dict):
        """
        测试多进程并发写入
        
        验证跨进程的文件锁机制能正确工作，确保数据不会损坏。
        """
        project_root = tmp_path / "novel"
        
        store = TaskStore(project_root)
        task = store.create_task("write", {"chapter": 1}, sample_workflow)
        task_id = task["id"]
        
        process_count = 5
        processes = [
            multiprocessing.Process(
                target=_update_task_process,
                args=(task_id, str(project_root), i)
            )
            for i in range(process_count)
        ]
        
        for p in processes:
            p.start()
        for p in processes:
            p.join()
        
        for p in processes:
            assert p.exitcode == 0, f"进程异常退出: exitcode={p.exitcode}"
        
        final_task = store.get_task(task_id)
        assert final_task is not None, "任务数据丢失"
        assert final_task["id"] == task_id, "任务ID不匹配"
        assert "status" in final_task, "任务数据损坏"
        
        saved_fields = sum(1 for i in range(process_count) if final_task.get(f"process_field_{i}") == i)
        assert saved_fields >= 1, f"至少应该有一个进程的更新被保存，实际保存了 {saved_fields} 个"

    def test_atomic_write_no_partial_data(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试原子写入不会产生部分数据
        
        验证写入过程中如果失败，不会留下损坏的文件。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_id = task["id"]
        
        original_task = task_store.get_task(task_id)
        assert original_task is not None
        
        task_store._write_task({
            **original_task,
            "status": "updated",
            "new_field": "test_value",
        })
        
        updated_task = task_store.get_task(task_id)
        assert updated_task is not None
        assert updated_task["status"] == "updated"
        assert updated_task["new_field"] == "test_value"
        assert updated_task["id"] == original_task["id"]

    def test_temp_file_cleanup_on_success(self, task_store: TaskStore, sample_workflow: dict):
        """
        测试成功写入后临时文件被清理
        
        验证临时文件在写入成功后被正确删除。
        """
        task = task_store.create_task("write", {"chapter": 1}, sample_workflow)
        task_id = task["id"]
        
        task_store.update_task(task_id, status="running")
        
        temp_files = list(task_store.base_dir.glob("*.tmp.*"))
        assert len(temp_files) == 0, f"发现未清理的临时文件: {temp_files}"
