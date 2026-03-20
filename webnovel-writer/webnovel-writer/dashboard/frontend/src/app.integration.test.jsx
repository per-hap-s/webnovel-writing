import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const fetchJSONMock = vi.fn()
const postJSONMock = vi.fn()
const subscribeSSEMock = vi.fn(() => () => {})
let tasksResponse = []

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
    subscribeSSE: (...args) => subscribeSSEMock(...args),
}))

vi.mock('./supervisorPage.jsx', () => ({
    SupervisorPage: ({ onTaskCreated }) => (
        <button
            onClick={() => onTaskCreated({
                id: 'task-new',
                task_type: 'write',
                status: 'queued',
                current_step: 'draft',
                request: { chapter: 9 },
                runtime_status: { target_label: '\u7b2c 9 \u7ae0' },
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
                            story_alignment: { satisfied: ['mainline'], missed: [], deferred: [] },
                            director_alignment: { satisfied: ['hook'], missed: [], deferred: [] },
                        },
                    },
                    operatorActions: [
                        { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: 'Continue chapter 10', variant: 'primary' },
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
    vi.useRealTimers()
    cleanup()
})

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
    subscribeSSEMock.mockClear()
    tasksResponse = []
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/project/info') return Promise.resolve({ progress: { current_chapter: 8, total_words: 12000 } })
        if (path === '/api/tasks') return Promise.resolve(tasksResponse)
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
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
        runtime_status: { target_label: '\u7b2c 9 \u7ae0' },
    }]
    await user.click(await screen.findByRole('button', { name: 'create-from-supervisor' }))

    expect(await screen.findByText('selected:task-new;count:1;summary:\u7b49\u5f85\u5b8c\u6210|none')).not.toBeNull()
})

test('sse refreshes are debounced and remain single-flight while in progress', async () => {
    vi.useFakeTimers()
    let pendingTaskResolve = null
    let taskFetchCount = 0

    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/project/info') return Promise.resolve({ progress: { current_chapter: 8, total_words: 12000 } })
        if (path === '/api/tasks') {
            taskFetchCount += 1
            if (taskFetchCount === 2) {
                return new Promise((resolve) => {
                    pendingTaskResolve = resolve
                })
            }
            return Promise.resolve(tasksResponse)
        }
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })

    render(<App />)
    await act(async () => {
        await Promise.resolve()
    })

    expect(taskFetchCount).toBe(1)
    const onMessage = subscribeSSEMock.mock.calls[0][0]

    act(() => {
        onMessage({ data: '{"kind":"modified"}' })
        onMessage({ data: '{"kind":"modified"}' })
    })
    await act(async () => {
        await vi.advanceTimersByTimeAsync(250)
        await Promise.resolve()
    })
    expect(taskFetchCount).toBe(2)

    act(() => {
        onMessage({ data: '{"kind":"modified"}' })
    })
    await act(async () => {
        await vi.advanceTimersByTimeAsync(250)
        await Promise.resolve()
    })
    expect(taskFetchCount).toBe(2)

    await act(async () => {
        pendingTaskResolve?.(tasksResponse)
        await Promise.resolve()
    })
    await act(async () => {
        await Promise.resolve()
    })

    expect(taskFetchCount).toBe(3)
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
                story_alignment: { satisfied: ['mainline'], missed: [], deferred: [] },
                director_alignment: { satisfied: ['hook'], missed: [], deferred: [] },
            },
        },
        operatorActions: [
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: 'Continue chapter 10', variant: 'primary' },
        ],
    }]

    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'launch-write' }))

    expect(await screen.findByText('selected:task-overview;count:1;summary:\u53ef\u4ee5\u7ee7\u7eed|Continue chapter 10')).not.toBeNull()
})

test('overview primary action button launches the next task through operator runtime', async () => {
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
                story_alignment: { satisfied: ['mainline'], missed: [], deferred: [] },
                director_alignment: { satisfied: ['hook'], missed: [], deferred: [] },
            },
        },
        operatorActions: [
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: 'Continue chapter 10', variant: 'primary' },
        ],
    }]
    postJSONMock.mockResolvedValue({ id: 'task-next', task_type: 'write', status: 'queued', request: { chapter: 10 }, runtime_status: { target_label: '\u7b2c 10 \u7ae0' } })

    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Continue chapter 10' }))

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/tasks/write', { chapter: 10 })
        expect(screen.getByText('selected:task-next;count:2;summary:\u7b49\u5f85\u5b8c\u6210|none')).not.toBeNull()
    })
})

test('overview renders disabled primary action label instead of falling back to view task', async () => {
    window.history.replaceState({}, '', '/')
    tasksResponse = [{
        id: 'task-blocked',
        task_type: 'resume',
        status: 'failed',
        current_step: 'resume',
        updated_at: '2026-03-20T10:00:00Z',
        artifacts: {
            resume: {
                blocking_reason: 'target task missing',
            },
        },
        operatorActions: [
            { kind: 'open-blocked-task', label: 'Open blocked task', variant: 'primary', disabled: true, reason: 'missing target_task_id' },
        ],
    }]

    render(<App />)

    const actionButton = await screen.findByRole('button', { name: 'Open blocked task' })
    expect(actionButton.getAttribute('disabled')).not.toBeNull()
    expect(actionButton.getAttribute('title')).toBe('missing target_task_id')
})

test('overview primary action surfaces request errors', async () => {
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
                story_alignment: { satisfied: ['mainline'], missed: [], deferred: [] },
                director_alignment: { satisfied: ['hook'], missed: [], deferred: [] },
            },
        },
        operatorActions: [
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: 'Continue chapter 10', variant: 'primary' },
        ],
    }]
    postJSONMock.mockRejectedValue(new Error('launch failed'))

    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Continue chapter 10' }))

    expect(await screen.findByText('launch failed')).not.toBeNull()
})

test('bootstrap success surfaces planning guidance on the overview', async () => {
    const user = userEvent.setup()

    window.history.replaceState({}, '', '/')
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/project/info') {
            return Promise.resolve({
                project_info: { title: '', genre: '' },
                dashboard_context: { project_initialized: false, project_root: '' },
                progress: { current_chapter: 0, total_words: 0 },
            })
        }
        if (path === '/api/tasks') return Promise.resolve([])
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        if (path === '/api/project/planning-profile') {
            return Promise.resolve({
                profile: {},
                field_specs: [],
                readiness: { ok: false, completed_fields: 0, total_required_fields: 0, blocking_items: [] },
            })
        }
        return Promise.resolve({})
    })
    postJSONMock.mockResolvedValue({
        created: true,
        project_switch_required: false,
        next_recommended_action: '项目已初始化。下一步请先确认规划信息，再运行 plan。',
    })

    render(<App />)

    await user.type(await screen.findByPlaceholderText('请输入新的项目目录'), 'D:\\tmp\\novel')
    await user.type(screen.getByPlaceholderText('留空则使用目录名'), 'Bootstrap Book')
    await user.clear(screen.getByPlaceholderText('玄幻'))
    await user.type(screen.getByPlaceholderText('玄幻'), '都市异能')
    await user.click(screen.getByRole('button', { name: '创建项目' }))

    expect(await screen.findByText('项目已初始化。下一步先确认并保存规划信息，再运行 `plan`，不需要先手工改总纲。')).not.toBeNull()
})
