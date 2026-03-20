import { beforeEach, expect, test, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
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
    normalizeError: (error) => ({ message: error?.message || String(error) }),
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
                story_alignment: { satisfied: ['主线推进'], missed: [], deferred: [] },
                director_alignment: { satisfied: ['兑现钩子'], missed: [], deferred: [] },
            },
        },
        operatorActions: [
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 9 }, label: 'Launch continuation', variant: 'primary' },
        ],
    }

    postJSONMock.mockResolvedValue({ id: 'task-2' })

    renderTaskCenter([task], task, { onSelectTask, onMutated })

    const taskButton = screen.getByRole('button', { name: /撰写章节/ })
    expect(within(taskButton).getByText('可以继续')).not.toBeNull()
    expect(within(taskButton).getByText('Launch continuation')).not.toBeNull()
    expect(screen.getByText('当前可继续下一章')).not.toBeNull()
    expect(screen.getAllByText('Launch continuation').length).toBeGreaterThanOrEqual(2)

    await user.click(screen.getByRole('button', { name: 'Launch continuation' }))

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

    const taskButton = screen.getByRole('button', { name: /护栏推进/ })
    expect(within(taskButton).getByText('不可继续')).not.toBeNull()
    expect(within(taskButton).getByText(/记录了 2 个问题/)).not.toBeNull()
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

    const taskButton = screen.getByRole('button', { name: /护栏批量推进/ })
    expect(within(taskButton).getByText('不可继续')).not.toBeNull()
    expect(within(taskButton).getByText(/子任务失败停止/)).not.toBeNull()
    expect(within(taskButton).getByText('打开失败子任务')).not.toBeNull()
})
