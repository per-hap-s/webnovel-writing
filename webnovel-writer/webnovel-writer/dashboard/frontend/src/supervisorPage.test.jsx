import { beforeEach, expect, test, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

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
    resolveSupervisorItemOperatorActions: (item) => item.operatorActions || [],
}))

vi.mock('./recoverySemantics.js', () => ({
    resolveSupervisorRecoverySemantics: () => null,
}))

import { SupervisorPage } from './supervisorPage.jsx'

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
    window.history.replaceState({}, '', '/')
})

test('keeps supervisor data visible when a later refresh fails', async () => {
    let phase = 0

    fetchJSONMock.mockImplementation((path) => {
        if (phase === 0) {
            if (path === '/api/supervisor/recommendations?include_dismissed=true') {
                return Promise.resolve([
                    {
                        stableKey: 'stable-1',
                        title: 'Stable Item',
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
                        title: 'Initial Checklist',
                        savedAt: '2026-03-20T10:00:00Z',
                        content: '# checklist',
                        summary: 'first snapshot',
                    },
                ])
            }
            return Promise.resolve([])
        }

        return Promise.reject(new Error('network down'))
    })

    const { rerender } = render(
        <SupervisorPage
            projectInfo={{ progress: { current_chapter: 2, total_words: 1000 } }}
            tasks={[]}
            onTaskCreated={vi.fn()}
            onOpenTask={vi.fn()}
            onTasksMutated={vi.fn()}
        />,
    )

    expect((await screen.findAllByText('Stable Item')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('Initial Checklist')).length).toBeGreaterThan(0)

    phase = 1
    rerender(
        <SupervisorPage
            projectInfo={{ progress: { current_chapter: 2, total_words: 1000 } }}
            tasks={[{ id: 'task-1' }]}
            onTaskCreated={vi.fn()}
            onOpenTask={vi.fn()}
            onTasksMutated={vi.fn()}
        />,
    )

    await waitFor(async () => {
        const alert = await screen.findByRole('alert')
        expect(alert.textContent || '').toContain('督办台数据刷新失败')
        expect(alert.textContent || '').not.toContain('REQUEST_FAILED')
        expect(alert.textContent || '').toContain('查看诊断详情')
        expect(screen.getAllByText('Stable Item').length).toBeGreaterThan(0)
        expect(screen.getAllByText('Initial Checklist').length).toBeGreaterThan(0)
    })
})


