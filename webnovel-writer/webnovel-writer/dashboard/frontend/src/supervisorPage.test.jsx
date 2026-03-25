import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const fetchJSONMock = vi.fn()
const postJSONMock = vi.fn()
const downloadTextFileMock = vi.fn()

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
    resolveSupervisorItemOperatorActions: (item) => item.operatorActions || [],
}))

vi.mock('./recoverySemantics.js', () => ({
    resolveSupervisorRecoverySemantics: () => null,
}))

vi.mock('./dashboardPageCommon.jsx', async () => {
    const actual = await vi.importActual('./dashboardPageCommon.jsx')
    return {
        ...actual,
        downloadTextFile: (...args) => downloadTextFileMock(...args),
    }
})

import { SupervisorPage } from './supervisorPage.jsx'

afterEach(() => {
    cleanup()
})

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
    downloadTextFileMock.mockReset()
    Object.defineProperty(window.navigator, 'clipboard', {
        configurable: true,
        value: { writeText: vi.fn().mockResolvedValue() },
    })
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

test('saving supervisor checklist failure keeps the current checklist visible', async () => {
    const user = userEvent.setup()

    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/supervisor/recommendations?include_dismissed=true') {
            return Promise.resolve([
                {
                    stableKey: 'stable-1',
                    title: 'Checklist Candidate',
                    category: 'approval',
                    categoryLabel: 'Approval',
                    trackingStatus: '',
                    summary: 'needs follow-up',
                },
            ])
        }
        if (path === '/api/supervisor/checklists') return Promise.resolve([])
        return Promise.resolve([])
    })
    postJSONMock.mockRejectedValue(new Error('save checklist failed'))

    render(
        <SupervisorPage
            projectInfo={{ progress: { current_chapter: 6, total_words: 9000 } }}
            tasks={[]}
            onTaskCreated={vi.fn()}
            onOpenTask={vi.fn()}
            onTasksMutated={vi.fn()}
        />,
    )

    expect((await screen.findAllByText('Checklist Candidate')).length).toBeGreaterThan(0)
    await user.click(screen.getByRole('button', { name: '保存到项目' }))

    await waitFor(() => {
        expect(screen.getByRole('alert').textContent || '').toContain('save checklist failed')
        expect(screen.getAllByText('Checklist Candidate').length).toBeGreaterThan(0)
        expect(screen.getByText('本轮处理清单')).not.toBeNull()
    })
})

test('download checklist failure surfaces an error without clearing supervisor content', async () => {
    const user = userEvent.setup()

    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/supervisor/recommendations?include_dismissed=true') {
            return Promise.resolve([
                {
                    stableKey: 'stable-1',
                    title: 'Download Candidate',
                    category: 'approval',
                    categoryLabel: 'Approval',
                    trackingStatus: '',
                    summary: 'needs follow-up',
                },
            ])
        }
        if (path === '/api/supervisor/checklists') return Promise.resolve([])
        return Promise.resolve([])
    })
    downloadTextFileMock.mockImplementation(() => {
        throw new Error('download failed')
    })

    render(
        <SupervisorPage
            projectInfo={{ progress: { current_chapter: 6, total_words: 9000 } }}
            tasks={[]}
            onTaskCreated={vi.fn()}
            onOpenTask={vi.fn()}
            onTasksMutated={vi.fn()}
        />,
    )

    expect((await screen.findAllByText('Download Candidate')).length).toBeGreaterThan(0)
    const checklistDownloadButton = screen.getAllByRole('button').find((button) => button.textContent?.includes('下载清单'))
    expect(checklistDownloadButton).toBeTruthy()
    await user.click(checklistDownloadButton)

    await waitFor(() => {
        expect(screen.getByRole('alert').textContent || '').toContain('download failed')
        expect(screen.getAllByText('Download Candidate').length).toBeGreaterThan(0)
    })
})
