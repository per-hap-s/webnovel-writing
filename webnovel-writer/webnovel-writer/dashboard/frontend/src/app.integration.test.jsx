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
        ApiSettingsSection: ({ onSaved }) => (
            <button onClick={() => onSaved?.()}>
                save-api-settings
            </button>
        ),
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

function buildHubPayload(overrides = {}) {
    return {
        workspace_root: 'C:/workspace',
        current_project: null,
        projects: [],
        recent_projects: [],
        pinned_projects: [],
        missing_projects: [],
        recommendations: [],
        tools: {
            'login-codex': { enabled: true },
            'open-guide': { enabled: true },
            'open-shell': { enabled: false },
            'start-lan-dashboard': { enabled: false },
        },
        ...overrides,
    }
}

function setProjectModeUrl(page = 'control') {
    const search = new URLSearchParams({ project_root: 'C:/novel' })
    if (page && page !== 'control') {
        search.set('page', page)
    }
    window.history.replaceState({}, '', `/?${search.toString()}`)
}

afterEach(() => {
    vi.useRealTimers()
    cleanup()
})

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
    subscribeSSEMock.mockClear()
    tasksResponse = []
    window.localStorage.clear()
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
        if (path === '/api/project/info') return Promise.resolve({ progress: { current_chapter: 8, total_words: 12000 } })
        if (path === '/api/tasks') return Promise.resolve(tasksResponse)
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })
    setProjectModeUrl('supervisor')
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

test('sse refreshes are debounced and remain single-flight while in progress', async () => {
    vi.useFakeTimers()
    let pendingTaskResolve = null
    let taskFetchCount = 0

    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
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

    setProjectModeUrl()
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

    expect(await screen.findByText('selected:task-overview;count:1;summary:可以继续|Continue chapter 10')).not.toBeNull()
})

test('overview primary action button launches the next task through operator runtime', async () => {
    const user = userEvent.setup()

    setProjectModeUrl()
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
    postJSONMock.mockResolvedValue({ id: 'task-next', task_type: 'write', status: 'queued', request: { chapter: 10 }, runtime_status: { target_label: '第 10 章' } })

    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'Continue chapter 10' }))

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/tasks/write', { chapter: 10 })
        expect(screen.getByText('selected:task-next;count:2;summary:等待完成|none')).not.toBeNull()
    })
})

test('overview renders disabled primary action label instead of falling back to view task', async () => {
    setProjectModeUrl()
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

    setProjectModeUrl()
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

test('app shows workbench and skips project polling when no project root is selected', async () => {
    window.history.replaceState({}, '', '/')

    render(<App />)

    expect(await screen.findByRole('button', { name: '打开已有项目' })).not.toBeNull()
    expect(fetchJSONMock).toHaveBeenCalledWith('/api/workbench/hub', {})
    expect(fetchJSONMock).not.toHaveBeenCalledWith('/api/project/info', expect.anything())
    expect(subscribeSSEMock).not.toHaveBeenCalled()
})

test('project mode sidebar omits duplicate workbench entry from project navigation', async () => {
    render(<App />)

    await screen.findByText('create-from-supervisor')

    const navSections = document.querySelectorAll('.sidebar .nav')
    expect(navSections).toHaveLength(2)
    expect(navSections[0].querySelectorAll('.nav-button')).toHaveLength(2)
    expect(navSections[1].querySelectorAll('.nav-button')).toHaveLength(7)
})

test('auto last preference redirects into the remembered project', async () => {
    window.localStorage.setItem('webnovel.dashboard.landing', 'auto_last')
    window.history.replaceState({}, '', '/')
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') {
            return Promise.resolve(buildHubPayload({
                current_project: {
                    project_root: 'C:/novel',
                    title: 'Remembered Novel',
                    dashboard_url: '/?project_root=C%3A%2Fnovel&page=tasks',
                },
                projects: [{
                    project_root: 'C:/novel',
                    title: 'Remembered Novel',
                    dashboard_url: '/?project_root=C%3A%2Fnovel&page=tasks',
                }],
            }))
        }
        if (path === '/api/project/info') return Promise.resolve({ progress: { current_chapter: 8, total_words: 12000 } })
        if (path === '/api/tasks') return Promise.resolve([])
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })

    render(<App />)

    expect(await screen.findByText('selected:none;count:0;summary:none|none')).not.toBeNull()
    expect(window.location.search).toContain('project_root=C%3A%2Fnovel')
    expect(window.location.search).toContain('page=tasks')
})

test('bootstrap success from workbench opens the new project and keeps planning hint', async () => {
    const user = userEvent.setup()

    window.history.replaceState({}, '', '/')
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') {
            return Promise.resolve(buildHubPayload())
        }
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
    postJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/pick-folder') {
            return Promise.resolve({ selected: true, project_root: 'D:\\tmp\\novel' })
        }
        if (path === '/api/project/bootstrap') {
            return Promise.resolve({
                created: true,
                project_root: 'D:\\tmp\\novel',
                suggested_dashboard_url: '/?project_root=D%3A%5Ctmp%5Cnovel&bootstrap_hint=planning',
                next_recommended_action: '项目已初始化。下一步请先确认规划信息，再运行 plan。',
            })
        }
        return Promise.resolve({})
    })

    render(<App />)

    await user.click(await screen.findByRole('button', { name: '先选项目目录' }))
    await user.type(screen.getByPlaceholderText('留空则使用目录名'), 'Bootstrap Book')
    await user.clear(screen.getByPlaceholderText('玄幻'))
    await user.type(screen.getByPlaceholderText('玄幻'), '都市异能')
    await user.click(screen.getByRole('button', { name: '创建项目' }))

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/workbench/pick-folder', {})
        expect(postJSONMock).toHaveBeenCalledWith('/api/project/bootstrap', {
            project_root: 'D:\\tmp\\novel',
            title: 'Bootstrap Book',
            genre: '都市异能',
        })
        expect(window.location.search).toContain('project_root=D%3A%5Ctmp%5Cnovel')
        expect(window.location.search).toContain('bootstrap_hint=planning')
    })
})

test('api settings save keeps the user on the current project page', async () => {
    const user = userEvent.setup()

    setProjectModeUrl()
    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'save-api-settings' }))

    expect(window.location.search).toContain('project_root=C%3A%2Fnovel')
    expect(subscribeSSEMock).toHaveBeenCalledTimes(1)
})

test('opening a recent project card goes through the workbench open-project API', async () => {
    const user = userEvent.setup()

    window.history.replaceState({}, '', '/')
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') {
            return Promise.resolve(buildHubPayload({
                recent_projects: [{
                    project_root: 'D:/books/novel-a',
                    title: 'Novel A',
                    dashboard_url: '/?project_root=D%3A%2Fbooks%2Fnovel-a',
                }],
            }))
        }
        if (path === '/api/project/info') return Promise.resolve({ progress: { current_chapter: 1, total_words: 100 } })
        if (path === '/api/tasks') return Promise.resolve([])
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })
    postJSONMock.mockImplementation((path, payload) => {
        if (path === '/api/workbench/open-project') {
            return Promise.resolve({
                opened: true,
                project_root: payload.project_root,
                suggested_dashboard_url: '/?project_root=D%3A%2Fbooks%2Fnovel-a',
            })
        }
        return Promise.resolve({})
    })

    render(<App />)

    await user.click(await screen.findByRole('button', { name: /Novel A/ }))

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/workbench/open-project', { project_root: 'D:/books/novel-a' })
        expect(window.location.search).toContain('project_root=D%3A%2Fbooks%2Fnovel-a')
    })
})

test('landing preference segmented toggle persists in localStorage', async () => {
    const user = userEvent.setup()

    window.history.replaceState({}, '', '/')

    render(<App />)

    const autoLastButton = await screen.findByRole('button', { name: '自动进入上次项目' })
    await user.click(autoLastButton)

    expect(window.localStorage.getItem('webnovel.dashboard.landing')).toBe('auto_last')
    expect(autoLastButton.getAttribute('aria-pressed')).toBe('true')
})

test('removing the current project refreshes hub without stale project_root context', async () => {
    const user = userEvent.setup()

    setProjectModeUrl('workbench')
    fetchJSONMock.mockImplementation((path, params) => {
        if (path === '/api/workbench/hub') {
            if (params?.project_root) {
                return Promise.resolve(buildHubPayload({
                    current_project: {
                        project_root: params.project_root,
                        title: 'Current Novel',
                        dashboard_url: '/?project_root=C%3A%2Fnovel',
                    },
                    projects: [{
                        project_root: params.project_root,
                        title: 'Current Novel',
                        dashboard_url: '/?project_root=C%3A%2Fnovel',
                    }],
                }))
            }
            return Promise.resolve(buildHubPayload())
        }
        return Promise.resolve({})
    })
    postJSONMock.mockResolvedValue({ saved: true })

    render(<App />)

    await waitFor(() => {
        expect(document.querySelector('.runtime-badge.success')).not.toBeNull()
    })
    const currentProjectSection = Array.from(document.querySelectorAll('section.panel'))
        .find((section) => section.querySelector('.runtime-badge.success'))
    const card = currentProjectSection.querySelector('.summary-card')
    const buttons = card.querySelectorAll('button')
    await user.click(buttons[2])

    await waitFor(() => {
        const hubCalls = fetchJSONMock.mock.calls.filter(([path]) => path === '/api/workbench/hub')
        expect(hubCalls[hubCalls.length - 1][1]).toEqual({})
        expect(window.location.search).not.toContain('project_root=')
    })
})
