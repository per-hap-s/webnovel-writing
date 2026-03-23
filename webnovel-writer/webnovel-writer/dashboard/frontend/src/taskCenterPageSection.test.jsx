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
    normalizeOperatorActions: (actions) => (Array.isArray(actions) ? actions : []),
}))

import { TaskCenterPageSection } from './appSections.jsx'

function renderTaskCenter(tasks, selectedTask, overrides = {}) {
    return render(
        <TaskCenterPageSection
            tasks={tasks}
            selectedTask={selectedTask}
            selectedTaskId={overrides.selectedTaskId ?? selectedTask?.id ?? null}
            currentProjectRoot={overrides.currentProjectRoot || ''}
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

test('task detail fetch includes explicit project_root in shell mode', async () => {
    const task = {
        id: 'task-shell-1',
        task_type: 'review',
        status: 'awaiting_writeback_approval',
        current_step: 'approval-gate',
        updated_at: '2026-03-21T10:05:00Z',
        runtime_status: {},
        request: { chapter_range: '1-3' },
    }

    fetchJSONMock.mockResolvedValueOnce({
        task,
        events: [],
    })

    renderTaskCenter([task], task, { currentProjectRoot: 'C:/novel-shell' })

    await waitFor(() => {
        expect(fetchJSONMock).toHaveBeenCalledWith('/api/tasks/task-shell-1/detail', { project_root: 'C:/novel-shell' })
    })
})

test('task detail re-fetches when the selected summary state changes for the same task id', async () => {
    const task = {
        id: 'task-refresh-1',
        task_type: 'write',
        status: 'running',
        current_step: 'draft',
        approval_status: 'not_required',
        updated_at: '2026-03-21T10:05:00Z',
        runtime_status: { step_state: 'running', last_event_message: 'request_dispatched' },
        request: { chapter: 1 },
    }

    fetchJSONMock
        .mockResolvedValueOnce({ task, events: [] })
        .mockResolvedValueOnce({
            task: {
                ...task,
                status: 'awaiting_writeback_approval',
                current_step: 'approval-gate',
                runtime_status: { step_state: 'waiting_approval', last_event_message: 'step_waiting_approval' },
            },
            events: [{ id: 'event-2', message: 'step_waiting_approval' }],
        })

    const view = renderTaskCenter([task], task)

    await waitFor(() => {
        expect(fetchJSONMock).toHaveBeenCalledTimes(1)
    })

    view.rerender(
        <TaskCenterPageSection
            tasks={[{
                ...task,
                status: 'awaiting_writeback_approval',
                current_step: 'approval-gate',
                runtime_status: { step_state: 'waiting_approval', last_event_message: 'step_waiting_approval' },
            }]}
            selectedTask={{
                ...task,
                status: 'awaiting_writeback_approval',
                current_step: 'approval-gate',
                runtime_status: { step_state: 'waiting_approval', last_event_message: 'step_waiting_approval' },
            }}
            selectedTaskId={task.id}
            currentProjectRoot=""
            onSelectTask={vi.fn()}
            onMutated={vi.fn()}
            onNavigateOverview={vi.fn()}
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

    await waitFor(() => {
        expect(fetchJSONMock).toHaveBeenCalledTimes(2)
        expect(fetchJSONMock).toHaveBeenLastCalledWith('/api/tasks/task-refresh-1/detail', {})
    })
})

test('task detail does not re-fetch when only runtime heartbeat metadata changes', async () => {
    const task = {
        id: 'task-heartbeat-1',
        task_type: 'write',
        status: 'running',
        current_step: 'draft',
        approval_status: 'not_required',
        updated_at: '2026-03-21T10:05:00Z',
        runtime_status: { step_state: 'running', last_event_message: 'request_dispatched', last_event_at: '2026-03-21T10:05:00Z' },
        request: { chapter: 1 },
    }

    fetchJSONMock.mockResolvedValueOnce({ task, events: [] })

    const view = renderTaskCenter([task], task)

    await waitFor(() => {
        expect(fetchJSONMock).toHaveBeenCalledTimes(1)
    })

    view.rerender(
        <TaskCenterPageSection
            tasks={[{
                ...task,
                runtime_status: { step_state: 'running', last_event_message: 'step_heartbeat', last_event_at: '2026-03-21T10:05:03Z' },
            }]}
            selectedTask={{
                ...task,
                runtime_status: { step_state: 'running', last_event_message: 'step_heartbeat', last_event_at: '2026-03-21T10:05:03Z' },
            }}
            selectedTaskId={task.id}
            currentProjectRoot=""
            onSelectTask={vi.fn()}
            onMutated={vi.fn()}
            onNavigateOverview={vi.fn()}
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

    await new Promise((resolve) => window.setTimeout(resolve, 0))
    expect(fetchJSONMock).toHaveBeenCalledTimes(1)
})

test('approval action includes explicit project_root in shell mode', async () => {
    const user = userEvent.setup()
    const onMutated = vi.fn()
    const task = {
        id: 'task-approval-1',
        task_type: 'review',
        status: 'awaiting_writeback_approval',
        current_step: 'approval-gate',
        updated_at: '2026-03-21T10:05:00Z',
        runtime_status: {},
        request: { chapter_range: '1-3' },
    }

    fetchJSONMock.mockResolvedValueOnce({
        task,
        events: [],
    })
    postJSONMock.mockResolvedValueOnce({ approved: true })

    renderTaskCenter([task], task, { currentProjectRoot: 'C:/novel-shell', onMutated })

    await user.click(await screen.findByRole('button', { name: '批准回写' }))

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith(
            '/api/review/approve',
            { task_id: 'task-approval-1', reason: '由仪表盘批准回写' },
            { params: { project_root: 'C:/novel-shell' } },
        )
        expect(onMutated).toHaveBeenCalled()
    })
})

test('chapter brief approval tasks surface approve and reject actions in the first screen', async () => {
    const task = {
        id: 'task-brief-1',
        task_type: 'write',
        status: 'awaiting_chapter_brief_approval',
        current_step: 'chapter-brief-approval',
        approval_status: 'pending',
        updated_at: '2026-03-21T10:05:00Z',
        runtime_status: {},
        request: { chapter: 3, require_manual_approval: false },
        artifacts: {
            step_results: {
                'chapter-director': {
                    structured_output: {
                        chapter: 3,
                        chapter_goal: 'Push the bureau clue forward.',
                        primary_conflict: 'Shen Yan must act before the memory cost escalates.',
                    },
                },
            },
        },
    }

    fetchJSONMock.mockResolvedValueOnce({
        task,
        events: [],
    })

    renderTaskCenter([task], task)

    expect(await screen.findByRole('button', { name: '批准开写' })).not.toBeNull()
    expect(screen.getByRole('button', { name: '驳回重做章节简报' })).not.toBeNull()
})


test('central translation helpers expose final pure-Chinese writing terms', () => {
    expect(translateTaskStatus('awaiting_chapter_brief_approval')).toBe('等待确认开写')
    expect(translateStepName('story-director')).toBe('多章规划')
    expect(translateStepName('chapter-director')).toBe('单章指挥')
    expect(translateStepName('chapter-brief-approval')).toBe('章节简报确认')
    expect(translateEventMessage('Waiting for chapter brief approval')).toBe('等待确认章节简报')
    expect(translateEventMessage('Chapter brief approved')).toBe('章节简报已批准，可开始正文写作')
    expect(resolveApprovalStatusLabel({
        task_type: 'write',
        status: 'awaiting_chapter_brief_approval',
        approval_status: 'pending',
        request: { require_manual_approval: false },
    })).toBe('等待确认章节简报')
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
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 9 }, label: '继续第 9 章', variant: 'primary' },
        ],
    }

    postJSONMock.mockResolvedValue({ id: 'task-2' })

    renderTaskCenter([task], task, { onSelectTask, onMutated })

    const taskItem = screen.getByRole('button', { name: /撰写章节/ })
    expect(within(taskItem).getByText(WRITING_CONTINUATION.continuable)).not.toBeNull()
    expect(screen.getByText(/当前可继续下一章/)).not.toBeNull()
    expect(screen.getAllByText('继续第 9 章').length).toBeGreaterThanOrEqual(2)

    await user.click(screen.getAllByRole('button', { name: '继续第 9 章' })[0])

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/tasks/write', { chapter: 9 }, {})
        expect(onSelectTask).toHaveBeenCalledWith('task-2')
        expect(onMutated).toHaveBeenCalled()
    })
})

test('completed resume helper task is deduped behind its resumed target in task list', async () => {
    const resumedTask = {
        id: 'task-write-9',
        task_type: 'write',
        status: 'completed',
        current_step: 'data-sync',
        updated_at: '2026-03-22T10:00:00Z',
        runtime_status: {},
        request: { chapter: 9 },
    }
    const resumeTask = {
        id: 'task-resume-9',
        task_type: 'resume',
        status: 'completed',
        current_step: 'resume',
        updated_at: '2026-03-22T10:05:00Z',
        runtime_status: {},
        resume_target_task_id: 'task-write-9',
        request: { chapter: 9 },
        artifacts: {
            resume: {
                target_task_id: 'task-write-9',
            },
        },
    }

    const view = renderTaskCenter([resumeTask, resumedTask], resumeTask)

    await waitFor(() => {
        expect(view.container.querySelectorAll('.task-item')).toHaveLength(1)
    })
    expect(screen.getByRole('button', { name: /撰写章节/ })).not.toBeNull()
    expect(screen.queryByRole('button', { name: /恢复任务/ })).toBeNull()
    expect(screen.getByText('任务详情')).not.toBeNull()
})

test('completed tasks sharing one root task keep only the latest business card in task list', async () => {
    const rootTask = {
        id: 'task-root-1',
        task_type: 'guarded-batch-write',
        status: 'completed',
        current_step: 'guarded-batch-runner',
        updated_at: '2026-03-22T09:30:00Z',
        runtime_status: {},
        root_task_id: 'task-root-1',
        request: { start_chapter: 8, max_chapters: 2 },
    }
    const childOlder = {
        id: 'task-child-older',
        task_type: 'write',
        status: 'completed',
        current_step: 'data-sync',
        updated_at: '2026-03-22T09:40:00Z',
        runtime_status: {},
        parent_task_id: 'task-root-1',
        root_task_id: 'task-root-1',
        request: { chapter: 8 },
    }
    const childLatest = {
        id: 'task-child-latest',
        task_type: 'write',
        status: 'completed',
        current_step: 'data-sync',
        updated_at: '2026-03-22T09:50:00Z',
        runtime_status: {},
        parent_task_id: 'task-root-1',
        root_task_id: 'task-root-1',
        request: { chapter: 9 },
    }
    const activeTask = {
        id: 'task-running-1',
        task_type: 'review',
        status: 'running',
        current_step: 'continuity-review',
        updated_at: '2026-03-22T09:55:00Z',
        runtime_status: { step_state: 'running' },
        request: { chapter_range: '8-9' },
    }

    const view = renderTaskCenter([rootTask, childOlder, childLatest, activeTask], childLatest)

    await waitFor(() => {
        expect(view.container.querySelectorAll('.task-item')).toHaveLength(2)
    })
    expect(screen.getAllByRole('button', { name: /撰写章节|执行审查/ }).length).toBeGreaterThan(0)
    expect(screen.getByText('任务详情')).not.toBeNull()
    expect(screen.getByRole('button', { name: /执行审查/ })).not.toBeNull()
    expect(screen.getByRole('button', { name: /撰写章节/ })).not.toBeNull()
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

    const taskItem = screen.getByRole('button', { name: /护栏推进单章/ })
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

    const taskItem = screen.getByRole('button', { name: /护栏推进单章/ })
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

    expect(screen.getAllByText('待补资料 / 已暂停').length).toBeGreaterThan(0)
    expect(screen.getByText('规划任务已停止，当前输入不足。请先补齐规划信息，再重新运行规划任务。')).not.toBeNull()
    expect(screen.getByText('故事一句话')).not.toBeNull()
    expect(screen.getByText('第 1 卷核心冲突')).not.toBeNull()
})

test('recoverable invalid step output task renders system fluctuation guidance from runtime status', () => {
    const task = {
        id: 'task-review-retryable-1',
        task_type: 'review',
        status: 'failed',
        current_step: 'continuity-review',
        updated_at: '2026-03-21T10:05:00Z',
        runtime_status: {
            phase_label: '连续性审查',
            phase_detail: '系统波动导致步骤结构化输出无效，建议从连续性审查重试。当前解析阶段：json_truncated。',
            error_code: 'INVALID_STEP_OUTPUT',
            retryable: true,
            suggested_resume_step: 'continuity-review',
        },
        request: { chapter_range: '1-3' },
        error: {
            code: 'INVALID_STEP_OUTPUT',
            message: '步骤输出中不包含有效 JSON 对象。',
            details: {
                parse_stage: 'json_truncated',
                recoverability: 'retriable',
                suggested_resume_step: 'continuity-review',
            },
        },
    }

    renderTaskCenter([task], task)

    expect(screen.getAllByText(/系统波动导致步骤结构化输出无效/).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: '按当前阶段重跑' })).not.toBeNull()
})


