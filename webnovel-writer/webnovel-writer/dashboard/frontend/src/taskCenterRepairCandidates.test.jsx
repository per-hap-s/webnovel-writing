import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
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

vi.mock('./operatorAction.js', async () => {
    const actual = await vi.importActual('./operatorAction.js')
    return {
        ...actual,
        resolveTaskOperatorActions: (task) => task.operatorActions || [],
    }
})

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

test('review summary repair candidate can launch repair task from task detail', async () => {
    const onSelectTask = vi.fn()
    const onMutated = vi.fn()
    const user = userEvent.setup()
    const task = {
        id: 'task-review-1',
        task_type: 'review',
        status: 'completed',
        current_step: 'review-summary',
        updated_at: '2026-03-21T12:00:00Z',
        runtime_status: {},
        request: { chapter_range: '1-3', mode: 'standard' },
        artifacts: {
            review_summary: {
                overall_score: 88,
                blocking: false,
                reviewers: ['continuity-review'],
                issues: [
                    { title: 'B1 到封存柜 47 的过渡不清', type: 'TRANSITION_CLARITY' },
                ],
                repairable_issue_count: 1,
                repair_candidates: [
                    {
                        chapter: 2,
                        issue_type: 'TRANSITION_CLARITY',
                        issue_title: 'B1 到封存柜 47 的过渡不清',
                        rewrite_goal: '补足空间与动作过渡，使读者可直接验证移动路径。',
                        guardrails: ['仅修复当前章节局部连续性问题'],
                        auto_rewrite_eligible: true,
                        operator_action: {
                            kind: 'launch-task',
                            task_type: 'repair',
                            label: '启动自动修稿',
                            payload: {
                                chapter: 2,
                                mode: 'standard',
                                require_manual_approval: false,
                                options: {
                                    source_task_id: 'task-review-1',
                                    issue_type: 'TRANSITION_CLARITY',
                                    issue_title: 'B1 到封存柜 47 的过渡不清',
                                    rewrite_goal: '补足空间与动作过渡，使读者可直接验证移动路径。',
                                    guardrails: ['仅修复当前章节局部连续性问题'],
                                },
                            },
                        },
                    },
                ],
            },
        },
        operatorActions: [],
    }

    postJSONMock.mockResolvedValue({ id: 'task-repair-2', task_type: 'repair' })

    renderTaskCenter([task], task, { onSelectTask, onMutated })

    await user.click(screen.getByRole('button', { name: '启动自动修稿' }))

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/tasks/repair', {
            chapter: 2,
            mode: 'standard',
            require_manual_approval: false,
            options: {
                source_task_id: 'task-review-1',
                issue_type: 'TRANSITION_CLARITY',
                issue_title: 'B1 到封存柜 47 的过渡不清',
                rewrite_goal: '补足空间与动作过渡，使读者可直接验证移动路径。',
                guardrails: ['仅修复当前章节局部连续性问题'],
            },
        })
        expect(onSelectTask).toHaveBeenCalledWith('task-repair-2')
        expect(onMutated).toHaveBeenCalled()
    })
})
