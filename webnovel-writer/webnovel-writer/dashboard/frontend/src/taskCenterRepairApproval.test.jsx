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
    normalizeError: (error) => ({
        displayMessage: error?.message || String(error),
        code: 'REQUEST_FAILED',
        rawMessage: error?.message || String(error),
        details: null,
    }),
}))

vi.mock('./operatorAction.js', () => ({
    resolveTaskOperatorActions: (task) => task.operatorActions || [],
    normalizeOperatorActions: (actions) => (Array.isArray(actions) ? actions : []),
}))

import { TaskCenterPageSection } from './appSections.jsx'

function renderTaskCenter(tasks, selectedTask) {
    return render(
        <TaskCenterPageSection
            tasks={tasks}
            selectedTask={selectedTask}
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
}

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
    fetchJSONMock.mockResolvedValue([])
})

afterEach(() => {
    cleanup()
})

test('repair task awaiting approval shows repair target and writeback actions', async () => {
    const user = userEvent.setup()
    const task = {
        id: 'task-repair-approval-1',
        task_type: 'repair',
        status: 'awaiting_writeback_approval',
        approval_status: 'pending',
        current_step: 'approval-gate',
        updated_at: '2026-03-21T10:10:00Z',
        runtime_status: {},
        request: { chapter: 2, require_manual_approval: true },
        artifacts: {
            review_summary: { overall_score: 92, blocking: false, reviewers: [], issues: [] },
        },
    }

    postJSONMock.mockResolvedValue({ id: task.id, status: 'queued' })

    renderTaskCenter([task], task)

    expect(screen.getAllByText('第 2 章局部修稿').length).toBeGreaterThan(0)
    expect(screen.getByText('等待你确认回写')).not.toBeNull()

    await user.click(screen.getByRole('button', { name: '批准回写' }))

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/review/approve', { task_id: task.id, reason: '由仪表盘批准回写' })
    })

    expect(screen.getByRole('button', { name: '拒绝回写' })).not.toBeNull()
})
