import { beforeEach, expect, test, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { buildSupervisorAuditQueryString } from './supervisorAuditState.js'

const fetchJSONMock = vi.fn()
const postJSONMock = vi.fn()
const resolveSupervisorItemOperatorActionsMock = vi.fn((item) => item.operatorActions || [])

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
    resolveSupervisorItemOperatorActions: (...args) => resolveSupervisorItemOperatorActionsMock(...args),
}))

vi.mock('./recoverySemantics.js', () => ({
    resolveSupervisorRecoverySemantics: () => null,
}))

import { SupervisorAuditPage } from './supervisorAuditPage.jsx'

function mockAuditFetches({ items = [], logEntries = [], checklists = [], health = {}, repairPreview = {}, repairReports = [] } = {}) {
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/supervisor/recommendations?include_dismissed=true') return Promise.resolve(items)
        if (path === '/api/supervisor/checklists') return Promise.resolve(checklists)
        if (path === '/api/supervisor/audit-log') return Promise.resolve(logEntries)
        if (path === '/api/supervisor/audit-health') return Promise.resolve(health)
        if (path === '/api/supervisor/audit-repair-preview') return Promise.resolve(repairPreview)
        if (path === '/api/supervisor/audit-repair-reports') return Promise.resolve(repairReports)
        throw new Error(`unexpected fetch path: ${path}`)
    })
}

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
    resolveSupervisorItemOperatorActionsMock.mockClear()
    Object.defineProperty(window.navigator, 'clipboard', {
        configurable: true,
        value: { writeText: vi.fn().mockResolvedValue() },
    })
    window.history.replaceState({}, '', '/')
})

test('restores audit deep-link focus from query state', async () => {
    const focusKey = 'focus-key'
    const otherKey = 'other-key'
    const query = buildSupervisorAuditQueryString({
        search: '',
        viewState: {
            stable_key: focusKey,
            view_mode: 'grouped',
        },
        dashboardPageKey: 'page',
        dashboardPageValue: 'supervisor-audit',
    })
    window.history.replaceState({}, '', `/?${query}`)

    mockAuditFetches({
        items: [
            { stableKey: focusKey, title: 'Focus Item', category: 'approval', categoryLabel: 'Approval', trackingStatus: '' },
            { stableKey: otherKey, title: 'Other Item', category: 'review', categoryLabel: 'Review', trackingStatus: '' },
        ],
        logEntries: [
            { stableKey: focusKey, action: 'created', timestamp: '2026-03-20T10:00:00Z', title: 'Focus Item' },
            { stableKey: otherKey, action: 'created', timestamp: '2026-03-20T10:01:00Z', title: 'Other Item' },
        ],
    })

    render(
        <SupervisorAuditPage
            projectInfo={{ progress: { current_chapter: 8, total_words: 12000 } }}
            tasks={[]}
            onTaskCreated={vi.fn()}
            onOpenTask={vi.fn()}
            onTasksMutated={vi.fn()}
        />,
    )

    await screen.findByText('Focus Item')
    await waitFor(() => {
        expect(screen.queryByText('Other Item')).toBeNull()
    })
})

test('keeps audit data visible when a later refresh fails', async () => {
    let phase = 0

    fetchJSONMock.mockImplementation((path) => {
        if (phase === 0) {
            if (path === '/api/supervisor/recommendations?include_dismissed=true') {
                return Promise.resolve([
                    {
                        stableKey: 'focus-key',
                        title: 'Stable Audit Item',
                        category: 'approval',
                        categoryLabel: 'Approval',
                        trackingStatus: '',
                    },
                ])
            }
            if (path === '/api/supervisor/checklists') {
                return Promise.resolve([
                    {
                        relativePath: '.webnovel/supervisor/checklists/checklist-ch0001-20260320-100000.md',
                        chapter: 1,
                        title: 'Stable Checklist',
                        savedAt: '2026-03-20T10:00:00Z',
                        content: '# checklist',
                        summary: 'first snapshot',
                    },
                ])
            }
            if (path === '/api/supervisor/audit-log') return Promise.resolve([{ stableKey: 'focus-key', action: 'created', timestamp: '2026-03-20T10:00:00Z', title: 'Stable Audit Item' }])
            if (path === '/api/supervisor/audit-health') return Promise.resolve({ healthy: true, issueCounts: {}, schemaStateCounts: {}, schemaVersionCounts: {}, issues: [] })
            if (path === '/api/supervisor/audit-repair-preview') return Promise.resolve({ exists: true, proposals: [] })
            if (path === '/api/supervisor/audit-repair-reports') return Promise.resolve([
                { filename: 'repair-report.json', relativePath: '.webnovel/supervisor/audit-repair-reports/repair-report.json', generatedAt: '2026-03-20T10:00:00Z', content: {} },
            ])
            return Promise.resolve([])
        }

        return Promise.reject(new Error('network down'))
    })

    const { rerender } = render(
        <SupervisorAuditPage
            projectInfo={{ progress: { current_chapter: 8, total_words: 12000 } }}
            tasks={[]}
            onTaskCreated={vi.fn()}
            onOpenTask={vi.fn()}
            onTasksMutated={vi.fn()}
        />,
    )

    expect((await screen.findAllByText('Stable Audit Item')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('Stable Checklist')).length).toBeGreaterThan(0)

    phase = 1
    rerender(
        <SupervisorAuditPage
            projectInfo={{ progress: { current_chapter: 8, total_words: 12000 } }}
            tasks={[{ id: 'task-1' }]}
            onTaskCreated={vi.fn()}
            onOpenTask={vi.fn()}
            onTasksMutated={vi.fn()}
        />,
    )

    await waitFor(async () => {
        const alert = await screen.findByRole('alert')
        expect(alert.textContent || '').toContain('Supervisor Audit 数据刷新失败')
        expect(alert.textContent || '').toContain('REQUEST_FAILED')
        expect(screen.getAllByText('Stable Audit Item').length).toBeGreaterThan(0)
        expect(screen.getAllByText('Stable Checklist').length).toBeGreaterThan(0)
    })
})

test('executes launch, retry, and open actions from audit groups', async () => {
    const onTaskCreated = vi.fn()
    const onOpenTask = vi.fn()
    const onTasksMutated = vi.fn()
    const user = userEvent.setup()
    const operatorActions = [
        { kind: 'launch-task', taskType: 'write', payload: { chapter: 9 }, label: 'Launch Draft' },
        { kind: 'retry-task', taskId: 'task-9', resumeFromStep: 'story-director', label: 'Retry Task' },
        { kind: 'open-task', taskId: 'task-9', label: 'Open Task' },
    ]

    postJSONMock.mockImplementation((path, body) => {
        if (path === '/api/tasks/write') return Promise.resolve({ id: 'task-new', path, body })
        if (path === '/api/tasks/task-9/retry') return Promise.resolve({ id: 'task-9', path, body })
        throw new Error(`unexpected post path: ${path}`)
    })

    mockAuditFetches({
        items: [
            {
                stableKey: 'focus-key',
                title: 'Launch Item',
                category: 'approval',
                categoryLabel: 'Approval',
                trackingStatus: '',
                actionLabel: 'Execute',
                operatorActions,
            },
        ],
        logEntries: [
            { stableKey: 'focus-key', action: 'created', timestamp: '2026-03-20T10:00:00Z', title: 'Launch Item' },
        ],
    })

    render(
        <SupervisorAuditPage
            projectInfo={{ progress: { current_chapter: 8, total_words: 12000 } }}
            tasks={[{ id: 'task-9', task_type: 'write', status: 'failed', current_step: 'draft', request: { chapter: 9 }, runtime_status: {} }]}
            onTaskCreated={onTaskCreated}
            onOpenTask={onOpenTask}
            onTasksMutated={onTasksMutated}
        />,
    )

    await screen.findByText('Launch Item')

    await user.click(screen.getByRole('button', { name: 'Launch Draft' }))
    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/tasks/write', { chapter: 9 })
        expect(onTaskCreated).toHaveBeenCalledWith(expect.objectContaining({ id: 'task-new' }), operatorActions[0])
    })

    await user.click(screen.getByRole('button', { name: 'Retry Task' }))
    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/tasks/task-9/retry', { resume_from_step: 'story-director' })
        expect(onOpenTask).toHaveBeenCalledWith('task-9')
        expect(onTasksMutated).toHaveBeenCalled()
    })

    await user.click(screen.getByRole('button', { name: 'Open Task' }))
    expect(onOpenTask).toHaveBeenCalledWith('task-9')
})
