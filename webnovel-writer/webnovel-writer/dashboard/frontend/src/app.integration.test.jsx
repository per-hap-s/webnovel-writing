import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const fetchJSONMock = vi.fn()
const subscribeSSEMock = vi.fn(() => () => {})
let tasksResponse = []

vi.mock('./api.js', () => ({
    fetchJSON: (...args) => fetchJSONMock(...args),
    postJSON: vi.fn(),
    normalizeError: (error) => ({ message: error?.message || String(error) }),
    subscribeSSE: (...args) => subscribeSSEMock(...args),
}))

vi.mock('./supervisorPage.jsx', () => ({
    SupervisorPage: ({ onTaskCreated }) => (
        <button onClick={() => onTaskCreated({
            id: 'task-new',
            task_type: 'write',
            status: 'queued',
            current_step: 'draft',
            request: { chapter: 9 },
            runtime_status: { target_label: '第 9 章' },
        })}
        >
            create-from-supervisor
        </button>
    ),
}))

vi.mock('./supervisorAuditPage.jsx', () => ({
    SupervisorAuditPage: () => <div>mock-audit-page</div>,
}))

vi.mock('./appSections.jsx', async () => {
    const actual = await vi.importActual('./appSections.jsx')
    const { buildWritingTaskListSummary } = await vi.importActual('./writingTaskListSummary.js')
    return {
        ...actual,
        TaskLauncherSection: ({ template, onCreated }) => (
            <button
                onClick={() => onCreated({
                    id: 'task-overview',
                    task_type: 'write',
                    status: 'completed',
                    current_step: 'data-sync',
                    updated_at: '2026-03-20T10:00:00Z',
                    request: { chapter: 9, require_manual_approval: true },
                    artifacts: {
                        writeback: {
                            story_alignment: { satisfied: ['主线推进'], missed: [], deferred: [] },
                            director_alignment: { satisfied: ['兑现钩子'], missed: [], deferred: [] },
                        },
                    },
                    operatorActions: [
                        { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: '继续第 10 章', variant: 'primary' },
                    ],
                })}
            >
                {`launch-${template.key}`}
            </button>
        ),
        TaskCenterPageSection: ({ tasks, selectedTask }) => {
            const summary = selectedTask ? buildWritingTaskListSummary({ task: selectedTask }) : null
            return <div>{`selected:${selectedTask?.id || 'none'};count:${tasks.length};summary:${summary?.continuationLabel || 'none'}|${summary?.primaryActionLabel || 'none'}`}</div>
        },
    }
})

import App from './App.jsx'

afterEach(() => {
    cleanup()
})

beforeEach(() => {
    fetchJSONMock.mockReset()
    subscribeSSEMock.mockClear()
    tasksResponse = []
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/project/info') return Promise.resolve({ progress: { current_chapter: 8, total_words: 12000 } })
        if (path === '/api/tasks') return Promise.resolve(tasksResponse)
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        throw new Error(`unexpected fetch path: ${path}`)
    })
    window.history.replaceState({}, '', '/?page=supervisor')
})

test('app refreshes task state and jumps to task detail after page-level task creation', async () => {
    const user = userEvent.setup()

    render(<App />)

    tasksResponse = [{
        id: 'task-new',
        task_type: 'write',
        status: 'queued',
        current_step: 'draft',
        request: { chapter: 9 },
        runtime_status: { target_label: '第 9 章' },
    }]
    await user.click(await screen.findByRole('button', { name: 'create-from-supervisor' }))

    expect(await screen.findByText('selected:task-new;count:1;summary:等待完成|none')).not.toBeNull()
})

test('overview task creation refreshes into tasks page with derived explanation state', async () => {
    const user = userEvent.setup()

    window.history.replaceState({}, '', '/')
    tasksResponse = [{
        id: 'task-overview',
        task_type: 'write',
        status: 'completed',
        current_step: 'data-sync',
        updated_at: '2026-03-20T10:00:00Z',
        request: { chapter: 9, require_manual_approval: true },
        artifacts: {
            writeback: {
                story_alignment: { satisfied: ['主线推进'], missed: [], deferred: [] },
                director_alignment: { satisfied: ['兑现钩子'], missed: [], deferred: [] },
            },
        },
        operatorActions: [
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: '继续第 10 章', variant: 'primary' },
        ],
    }]

    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'launch-write' }))

    expect(await screen.findByText('selected:task-overview;count:1;summary:可以继续|继续第 10 章')).not.toBeNull()
})
