import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import {
    MetricCard,
    resolveApprovalStatusLabel,
    resolveCurrentStepLabel,
    resolveTaskStatusLabel,
    resolveTaskTargetLabel,
    translateEventLevel,
    translateEventMessage,
    translateStepName,
    translateTaskStatus,
    translateTaskType,
} from './dashboardPageCommon.jsx'

const fetchJSONMock = vi.fn()
const postJSONMock = vi.fn()

vi.mock('./api.js', () => ({
    fetchJSON: (...args) => fetchJSONMock(...args),
    postJSON: (...args) => postJSONMock(...args),
    normalizeError: (error) => {
        if (error?.displayMessage) return error
        return {
            displayMessage: error?.message || String(error),
            code: 'REQUEST_FAILED',
            rawMessage: error?.message || String(error),
            details: null,
        }
    },
}))

vi.mock('./operatorAction.js', () => ({
    resolveTaskOperatorActions: (task) => task.operatorActions || [],
}))

import { TaskCenterPageSection } from './appSections.jsx'

function renderTaskCenter(tasks, selectedTask, overrides = {}) {
    return render(
        <TaskCenterPageSection
            tasks={tasks}
            selectedTask={selectedTask}
            onSelectTask={overrides.onSelectTask || vi.fn()}
            onMutated={overrides.onMutated || vi.fn()}
            onNavigateOverview={overrides.onNavigateOverview || vi.fn()}
            MetricCard={MetricCard}
            translateTaskType={translateTaskType}
            translateTaskStatus={translateTaskStatus}
            translateStepName={translateStepName}
            translateEventLevel={translateEventLevel}
            translateEventMessage={translateEventMessage}
            resolveTaskStatusLabel={resolveTaskStatusLabel}
            resolveCurrentStepLabel={resolveCurrentStepLabel}
            resolveApprovalStatusLabel={resolveApprovalStatusLabel}
            resolveTargetLabel={resolveTaskTargetLabel}
        />,
    )
}

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
    fetchJSONMock.mockResolvedValue([])
})

afterEach(() => {
    cleanup()
})

test('task list and detail share the same continuation outcome and primary action label', async () => {
    const onSelectTask = vi.fn()
    const onMutated = vi.fn()
    const user = userEvent.setup()
    const task = {
        id: 'task-1',
        task_type: 'write',
        status: 'completed',
        current_step: 'draft',
        updated_at: '2026-03-20T10:00:00Z',
        runtime_status: {},
        request: { chapter: 8, require_manual_approval: true },
        artifacts: {
            writeback: {
                story_alignment: { satisfied: ['mainline'], missed: [], deferred: [] },
                director_alignment: { satisfied: ['hook'], missed: [], deferred: [] },
            },
        },
        operatorActions: [
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 9 }, label: 'Launch continuation', variant: 'primary' },
        ],
    }

    postJSONMock.mockResolvedValue({ id: 'task-2' })

    renderTaskCenter([task], task, { onSelectTask, onMutated })

    const taskItem = screen.getByRole('button', { name: /\u64b0\u5199\u7ae0\u8282/ })
    expect(within(taskItem).getByText('\u53ef\u4ee5\u7ee7\u7eed')).not.toBeNull()
    expect(screen.getByText(/\u5f53\u524d\u53ef\u7ee7\u7eed\u4e0b\u4e00\u7ae0/)).not.toBeNull()
    expect(screen.getAllByText('Launch continuation').length).toBeGreaterThanOrEqual(2)

    await user.click(screen.getAllByRole('button', { name: 'Launch continuation' })[0])

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/tasks/write', { chapter: 9 })
        expect(onSelectTask).toHaveBeenCalledWith('task-2')
        expect(onMutated).toHaveBeenCalled()
    })
})

test('guarded review block renders the same blocked reason in task list and detail', () => {
    const task = {
        id: 'task-guarded-1',
        task_type: 'guarded-write',
        status: 'completed',
        current_step: 'review-summary',
        updated_at: '2026-03-20T10:00:00Z',
        runtime_status: {},
        request: { chapter: 8 },
        artifacts: {
            guarded_runner: {
                outcome: 'blocked_by_review',
                review_summary: {
                    issues: [{ title: '节奏失衡' }, { title: '动机不足' }],
                },
            },
        },
        operatorActions: [
            { kind: 'open-task', taskId: 'task-child-1', label: '打开阻断子任务', variant: 'primary' },
        ],
    }

    renderTaskCenter([task], task)

    const taskItem = screen.getByRole('button', { name: /\u62a4\u680f\u63a8\u8fdb/ })
    expect(within(taskItem).getByText('\u4e0d\u53ef\u7ee7\u7eed')).not.toBeNull()
    expect(within(taskItem).getByText(/\u8bb0\u5f55\u4e86 2 \u4e2a\u95ee\u9898/)).not.toBeNull()
    expect(screen.getByText('\u7ee7\u7eed\u524d\u5fc5\u987b\u5904\u7406\u5ba1\u67e5\u963b\u65ad')).not.toBeNull()
    expect(screen.getAllByText(/\u8bb0\u5f55\u4e86 2 \u4e2a\u95ee\u9898/).length).toBeGreaterThanOrEqual(2)
})

test('guarded batch child failure renders blocked batch summary in task list', () => {
    const task = {
        id: 'task-batch-1',
        task_type: 'guarded-batch-write',
        status: 'completed',
        current_step: 'guarded-batch-runner',
        updated_at: '2026-03-20T10:00:00Z',
        runtime_status: {},
        request: { start_chapter: 8, max_chapters: 3 },
        artifacts: {
            guarded_batch_runner: {
                outcome: 'child_task_failed',
                completed_chapters: 1,
                runs: [],
            },
        },
        operatorActions: [
            { kind: 'open-task', taskId: 'task-child-2', label: '打开失败子任务', variant: 'primary' },
        ],
    }

    renderTaskCenter([task], task)

    const taskItem = screen.getByRole('button', { name: /\u62a4\u680f\u6279\u91cf\u63a8\u8fdb/ })
    const taskCard = taskItem.closest('.task-item')
    expect(within(taskItem).getByText('\u4e0d\u53ef\u7ee7\u7eed')).not.toBeNull()
    expect(within(taskItem).getByText(/\u5b50\u4efb\u52a1\u5931\u8d25\u505c\u6b62/)).not.toBeNull()
    expect(taskCard).not.toBeNull()
    expect(within(taskCard).getByRole('button', { name: '打开失败子任务' })).not.toBeNull()
})

test('clicking task list action button does not trigger card selection for the current item', async () => {
    const onSelectTask = vi.fn()
    const user = userEvent.setup()
    const task = {
        id: 'task-open-1',
        task_type: 'guarded-write',
        status: 'completed',
        current_step: 'review-summary',
        updated_at: '2026-03-20T10:00:00Z',
        runtime_status: {},
        request: { chapter: 8 },
        artifacts: {
            guarded_runner: {
                outcome: 'blocked_by_review',
                review_summary: { issues: [{ title: '节奏失衡' }] },
            },
        },
        operatorActions: [
            { kind: 'open-task', taskId: 'task-child-1', label: '打开阻断子任务', variant: 'primary' },
        ],
    }

    renderTaskCenter([task], task, { onSelectTask })

    const taskItem = screen.getByRole('button', { name: /\u62a4\u680f\u63a8\u8fdb/ })
    const taskCard = taskItem.closest('.task-item')
    expect(taskCard).not.toBeNull()

    await user.click(within(taskCard).getByRole('button', { name: '打开阻断子任务' }))

    expect(onSelectTask).toHaveBeenCalledTimes(1)
    expect(onSelectTask).toHaveBeenCalledWith('task-child-1')
})

test('disabled primary action keeps label and renders as disabled in task list', () => {
    const task = {
        id: 'task-disabled-1',
        task_type: 'resume',
        status: 'failed',
        current_step: 'resume',
        updated_at: '2026-03-20T10:00:00Z',
        runtime_status: {},
        artifacts: {
            resume: {
                blocking_reason: 'target task missing',
            },
        },
        operatorActions: [
            { kind: 'open-blocked-task', label: 'Open blocked task', variant: 'primary', disabled: true, reason: 'missing target_task_id' },
        ],
    }

    renderTaskCenter([task], task)

    const taskItem = screen.getByRole('button', { name: /\u6062\u590d\u4efb\u52a1/ })
    const taskCard = taskItem.closest('.task-item')
    expect(taskCard).not.toBeNull()
    const actionButton = within(taskCard).getByRole('button', { name: 'Open blocked task' })
    expect(actionButton.getAttribute('disabled')).not.toBeNull()
    expect(actionButton.getAttribute('title')).toBe('missing target_task_id')
})
