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
import { WRITING_CONTINUATION } from './writingTaskCopy.js'

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

    const taskItem = screen.getByRole('button', { name: /撰写章节/ })
    expect(within(taskItem).getByText(WRITING_CONTINUATION.continuable)).not.toBeNull()
    expect(screen.getByText(/当前可继续下一章/)).not.toBeNull()
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

    const taskItem = screen.getByRole('button', { name: /护栏推进/ })
    expect(within(taskItem).getByText(WRITING_CONTINUATION.blocked)).not.toBeNull()
    expect(within(taskItem).getByText(/记录了 2 个问题/)).not.toBeNull()
    expect(screen.getByText('继续前必须处理审查阻断')).not.toBeNull()
    expect(screen.getAllByText(/记录了 2 个问题/).length).toBeGreaterThanOrEqual(2)
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

    const taskItem = screen.getByRole('button', { name: /护栏批量推进/ })
    const taskCard = taskItem.closest('.task-item')
    expect(within(taskItem).getByText(WRITING_CONTINUATION.blocked)).not.toBeNull()
    expect(within(taskItem).getByText(/子任务失败停止/)).not.toBeNull()
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

    const taskItem = screen.getByRole('button', { name: /护栏推进/ })
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

    const taskItem = screen.getByRole('button', { name: /恢复任务/ })
    const taskCard = taskItem.closest('.task-item')
    expect(taskCard).not.toBeNull()
    const actionButton = within(taskCard).getByRole('button', { name: 'Open blocked task' })
    expect(actionButton.getAttribute('disabled')).not.toBeNull()
    expect(actionButton.getAttribute('title')).toBe('missing target_task_id')
})

test('plan blocked task renders dedicated stopped-for-input copy', () => {
    const task = {
        id: 'task-plan-blocked-1',
        task_type: 'plan',
        status: 'failed',
        current_step: 'plan',
        updated_at: '2026-03-21T10:00:00Z',
        runtime_status: { phase_label: '待补信息', error_code: 'PLAN_INPUT_BLOCKED' },
        request: { volume: 1 },
        error: {
            code: 'PLAN_INPUT_BLOCKED',
            message: '规划输入不完整，无法生成可执行卷规划。',
        },
        artifacts: {
            plan_blocked: true,
            blocking_items: [
                { field: 'story_logline', label: '故事一句话' },
                { field: 'volume_1_conflict', label: '第 1 卷核心冲突' },
            ],
        },
    }

    renderTaskCenter([task], task)

    expect(screen.getAllByText('待补资料 / 已停止').length).toBeGreaterThan(0)
    expect(screen.getByText('规划任务已停止，当前输入不足。请先补齐规划信息，再重新运行 plan。')).not.toBeNull()
    expect(screen.getByText('故事一句话')).not.toBeNull()
    expect(screen.getByText('第 1 卷核心冲突')).not.toBeNull()
})
