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
                        { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: '继续第 10 章', variant: 'primary' },
                    ],
                })}
            >
                {`launch-${template.key}`}
            </button>
        ),
        TaskCenterPageSection: ({ tasks, selectedTask, onSelectTask }) => {
            const summary = selectedTask ? buildWritingTaskListSummary({ task: selectedTask }) : null
            return (
                <div>
                    {tasks.map((task) => (
                        <button key={task.id} onClick={() => onSelectTask?.(task.id)}>
                            {`select-${task.id}`}
                        </button>
                    ))}
                    <div>{`selected:${selectedTask?.id || 'none'};count:${tasks.length};summary:${summary?.continuationLabel || 'none'}|${summary?.primaryActionLabel || 'none'}`}</div>
                </div>
            )
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
        if (path === '/api/project/director-hub') {
            return Promise.resolve({
                current_chapter: 9,
                current_brief: {
                    chapter: 9,
                    chapter_goal: 'Lead with scene action',
                    primary_conflict: 'The protagonist must decide before the clue disappears.',
                    allowed_reveal_ceiling: 'Only confirm the cost of one rewind.',
                    ending_hook_target: 'Leave a trace that points to chapter 10.',
                    must_advance_threads: ['Archive thread'],
                    must_hold_back_facts: ['Watcher identity'],
                    voice_constraints: ['Keep the prose tactile'],
                    forbidden_terms: ['system panel'],
                },
                story_plan: {
                    anchor_chapter: 9,
                    rationale: 'This story plan uses active foreshadowing, knowledge conflicts and hooks to keep the rain archive line under pressure.',
                    priority_threads: ['Archive thread', 'Memory cost'],
                    chapters: [
                        {
                            chapter: 9,
                            chapter_goal: 'Pressure the archive thread',
                            ending_hook_target: 'Point toward the flooded station',
                        },
                    ],
                },
                continuity: {
                    plot_threads: [{ title: 'Archive thread', urgency: 'high' }],
                    mystery_ledger: [{ name: 'Watcher identity' }],
                    rule_assertions: [{ name: 'One rewind burns one memory' }],
                    trust_map: {
                        'Shen Yan->Bureau': { status: 'fragile', chapter: 8 },
                    },
                    director_decisions: [{ chapter: 9 }],
                },
                voice_bible: {
                    characters: {
                        'Shen Yan': { constraints: ['Keep the prose tactile'] },
                    },
                },
            })
        }
        if (path === '/api/tasks/summary') return Promise.resolve(tasksResponse)
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

test('task center receives deduped completed cards while keeping active tasks visible', async () => {
    tasksResponse = [
        {
            id: 'task-write-9',
            task_type: 'write',
            status: 'completed',
            current_step: 'data-sync',
            updated_at: '2026-03-22T10:00:00Z',
            request: { chapter: 9 },
            runtime_status: { target_label: '第 9 章' },
        },
        {
            id: 'task-resume-9',
            task_type: 'resume',
            status: 'completed',
            current_step: 'resume',
            updated_at: '2026-03-22T10:05:00Z',
            request: { chapter: 9 },
            runtime_status: { target_label: '第 9 章' },
            resume_target_task_id: 'task-write-9',
        },
        {
            id: 'task-review-1',
            task_type: 'review',
            status: 'running',
            current_step: 'continuity-review',
            updated_at: '2026-03-22T10:06:00Z',
            request: { chapter_range: '8-9' },
            runtime_status: { target_label: '第 8-9 章', step_state: 'running' },
        },
    ]
    setProjectModeUrl('tasks')

    render(<App />)

    expect(await screen.findByText('selected:task-review-1;count:2;summary:none|none')).not.toBeNull()
})

test('sse refreshes are debounced and remain single-flight while in progress', async () => {
    vi.useFakeTimers()
    let pendingTaskResolve = null
    let taskFetchCount = 0

    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
        if (path === '/api/project/info') return Promise.resolve({ progress: { current_chapter: 8, total_words: 12000 } })
        if (path === '/api/tasks/summary') {
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
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: '继续第 10 章', variant: 'primary' },
        ],
    }]

    render(<App />)

    await user.click(await screen.findByRole('button', { name: 'launch-write' }))

    expect(await screen.findByText('selected:task-overview;count:1;summary:可以继续|继续第 10 章')).not.toBeNull()
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
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: '继续第 10 章', variant: 'primary' },
        ],
    }]
    postJSONMock.mockResolvedValue({ id: 'task-next', task_type: 'write', status: 'queued', request: { chapter: 10 }, runtime_status: { target_label: '第 10 章' } })

    render(<App />)

    await user.click(await screen.findByRole('button', { name: '继续第 10 章' }))

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
            { kind: 'open-blocked-task', label: '打开阻断子任务', variant: 'primary', disabled: true, reason: 'missing target_task_id' },
        ],
    }]

    render(<App />)

    const actionButton = await screen.findByRole('button', { name: '打开阻断子任务' })
    expect(actionButton.getAttribute('disabled')).not.toBeNull()
    expect(actionButton.getAttribute('title')).toBe('missing target_task_id')
})

test('control overview renders director hub guidance from the backend snapshot', async () => {
    setProjectModeUrl()

    render(<App />)

    expect(await screen.findByText('创作指挥台')).not.toBeNull()
    expect(screen.getByText('章节简报')).not.toBeNull()
    expect(screen.getByText('Lead with scene action')).not.toBeNull()
    expect(screen.getByText('The protagonist must decide before the clue disappears.')).not.toBeNull()
    expect(screen.getByText(/当前多章规划会根据活跃伏笔、知识冲突与最近指挥结果生成/)).not.toBeNull()
    expect(screen.getAllByText('Archive thread').length).toBeGreaterThan(0)
    expect(screen.getByText('One rewind burns one memory')).not.toBeNull()
    expect(screen.queryByText(/story plan/i)).toBeNull()
    expect(screen.queryByText(/active foreshadowing/i)).toBeNull()
    expect(screen.queryByText(/knowledge conflicts/i)).toBeNull()
    expect(screen.queryByText(/\bhooks\b/i)).toBeNull()
})

test('director hub failure degrades only the panel and keeps overview usable', async () => {
    setProjectModeUrl()
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
        if (path === '/api/project/info') {
            return Promise.resolve({
                project_info: { title: 'Night Rain Archive', genre: '都市异能' },
                dashboard_context: { project_initialized: true, project_root: 'C:/novel' },
                progress: { current_chapter: 1, total_words: 3607 },
            })
        }
        if (path === '/api/project/director-hub') {
            return Promise.reject({
                displayMessage: '创作工作台服务暂未返回有效接口数据，请刷新或重新启动工作台。',
                code: 'HTML_RESPONSE',
                rawMessage: '后端返回了页面内容而不是接口数据。',
                details: { path: '/api/project/director-hub' },
            })
        }
        if (path === '/api/tasks/summary') return Promise.resolve([])
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })

    render(<App />)

    expect((await screen.findAllByText('项目总览')).length).toBeGreaterThan(0)
    expect(screen.queryByText('核心数据刷新失败')).toBeNull()
    expect(screen.getByText('创作指挥台暂时无法刷新，请稍后重试。')).not.toBeNull()
    expect(screen.queryByText(/HTML_RESPONSE/)).toBeNull()
    expect(screen.getByText('总字数')).not.toBeNull()
})

test('director hub refresh failure keeps the last successful snapshot visible', async () => {
    setProjectModeUrl()
    let failDirectorHub = false

    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
        if (path === '/api/project/info') {
            return Promise.resolve({
                project_info: { title: 'Night Rain Archive', genre: '都市异能' },
                dashboard_context: { project_initialized: true, project_root: 'C:/novel' },
                progress: { current_chapter: 1, total_words: 3607 },
            })
        }
        if (path === '/api/project/director-hub') {
            if (failDirectorHub) {
                return Promise.reject({
                    displayMessage: '创作工作台服务暂未返回有效接口数据，请刷新或重新启动工作台。',
                    code: 'HTML_RESPONSE',
                    rawMessage: '后端返回了页面内容而不是接口数据。',
                    details: { path: '/api/project/director-hub' },
                })
            }
            return Promise.resolve({
                current_chapter: 9,
                current_brief: {
                    chapter: 9,
                    chapter_goal: 'Lead with scene action',
                    primary_conflict: 'The protagonist must decide before the clue disappears.',
                },
                story_plan: {
                    anchor_chapter: 9,
                    rationale: 'This story plan uses active foreshadowing, knowledge conflicts and hooks to keep the rain archive line under pressure.',
                },
                continuity: {
                    plot_threads: [{ title: 'Archive thread', urgency: 'high' }],
                    rule_assertions: [{ name: 'One rewind burns one memory' }],
                },
                voice_bible: {},
            })
        }
        if (path === '/api/tasks/summary') return Promise.resolve([])
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })

    render(<App />)

    expect(await screen.findByText('Lead with scene action')).not.toBeNull()

    failDirectorHub = true
    const onMessage = subscribeSSEMock.mock.calls[0][0]

    act(() => {
        onMessage({ data: '{"kind":"modified"}' })
    })
    await waitFor(() => {
        expect(screen.getByText('创作指挥台暂时无法刷新，请稍后重试。')).not.toBeNull()
        expect(screen.getByText('Lead with scene action')).not.toBeNull()
        expect(screen.getByText('The protagonist must decide before the clue disappears.')).not.toBeNull()
    })
})

test('sse overflow triggers fallback refresh and keeps the selected task', async () => {
    const user = userEvent.setup()
    let taskFetchCount = 0
    tasksResponse = [
        {
            id: 'task-a',
            task_type: 'write',
            status: 'running',
            current_step: 'draft',
            request: { chapter: 9 },
            runtime_status: { target_label: '第 9 章', step_state: 'running' },
        },
        {
            id: 'task-b',
            task_type: 'review',
            status: 'queued',
            current_step: 'review-summary',
            request: { chapter_range: '9-10' },
            runtime_status: { target_label: '第 9-10 章' },
        },
    ]

    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
        if (path === '/api/project/info') return Promise.resolve({ progress: { current_chapter: 8, total_words: 12000 } })
        if (path === '/api/project/director-hub') return Promise.resolve({ current_chapter: 9, current_brief: {}, story_plan: {}, continuity: {}, voice_bible: {} })
        if (path === '/api/tasks/summary') {
            taskFetchCount += 1
            return Promise.resolve(tasksResponse)
        }
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })
    setProjectModeUrl('tasks')

    render(<App />)

    expect(await screen.findByText('selected:task-a;count:2;summary:等待完成|none')).not.toBeNull()
    await user.click(screen.getByRole('button', { name: 'select-task-b' }))
    expect(await screen.findByText('selected:task-b;count:2;summary:none|none')).not.toBeNull()

    const sseOptions = subscribeSSEMock.mock.calls[0][1]
    act(() => {
        sseOptions.onOverflow?.()
    })

    await waitFor(() => {
        expect(taskFetchCount).toBeGreaterThanOrEqual(2)
        expect(screen.getByText('selected:task-b;count:2;summary:none|none')).not.toBeNull()
        expect(screen.getByText('实时同步已断开')).not.toBeNull()
    })
})

test('polling fallback refreshes active tasks after sse disconnect', async () => {
    vi.useFakeTimers()
    let taskFetchCount = 0
    tasksResponse = [
        {
            id: 'task-poll',
            task_type: 'write',
            status: 'running',
            current_step: 'draft',
            request: { chapter: 12 },
            runtime_status: { target_label: '第 12 章', step_state: 'running' },
        },
    ]

    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
        if (path === '/api/project/info') return Promise.resolve({ progress: { current_chapter: 11, total_words: 16000 } })
        if (path === '/api/project/director-hub') return Promise.resolve({ current_chapter: 12, current_brief: {}, story_plan: {}, continuity: {}, voice_bible: {} })
        if (path === '/api/tasks/summary') {
            taskFetchCount += 1
            return Promise.resolve(tasksResponse)
        }
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })
    setProjectModeUrl('tasks')

    render(<App />)
    await act(async () => {
        await Promise.resolve()
    })
    expect(taskFetchCount).toBe(1)

    const sseOptions = subscribeSSEMock.mock.calls[0][1]
    act(() => {
        sseOptions.onError?.()
    })

    await act(async () => {
        await vi.advanceTimersByTimeAsync(3000)
        await Promise.resolve()
    })

    expect(taskFetchCount).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('selected:task-poll;count:1;summary:等待完成|none')).not.toBeNull()
})

test('workbench tools page uses pure-Chinese labels for user-facing actions', async () => {
    const user = userEvent.setup()

    window.history.replaceState({}, '', '/')
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '工具页' }))

    expect(screen.getByText('登录创作命令行')).not.toBeNull()
    expect(screen.getByText('打开当前项目终端')).not.toBeNull()
    expect(screen.queryByText(/Codex CLI/)).toBeNull()
    expect(screen.queryByText(/PowerShell/)).toBeNull()
})

test('status probe failures stay local to status pills instead of showing a global banner', async () => {
    setProjectModeUrl()
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
        if (path === '/api/project/info') {
            return Promise.resolve({
                project_info: { title: 'Night Rain Archive', genre: '都市异能' },
                dashboard_context: { project_initialized: true, project_root: 'C:/novel' },
                progress: { current_chapter: 1, total_words: 3607 },
            })
        }
        if (path === '/api/project/director-hub') {
            return Promise.resolve({
                current_chapter: 2,
                current_brief: {},
                story_plan: {
                    anchor_chapter: 1,
                    planning_horizon: 4,
                    rationale: 'This story plan uses active foreshadowing, knowledge conflicts and hooks.',
                },
                continuity: {},
                voice_bible: {},
            })
        }
        if (path === '/api/tasks/summary') return Promise.resolve([])
        if (path === '/api/llm/status') {
            return Promise.reject({
                displayMessage: '浏览器等待接口返回超时，后台任务可能仍在继续执行。',
                code: 'CLIENT_TIMEOUT',
            })
        }
        if (path === '/api/rag/status') {
            return Promise.reject({
                displayMessage: '浏览器等待接口返回超时，后台任务可能仍在继续执行。',
                code: 'CLIENT_TIMEOUT',
            })
        }
        return Promise.resolve({})
    })

    render(<App />)

    expect((await screen.findAllByText('项目总览')).length).toBeGreaterThan(0)
    expect(screen.queryByText('引擎状态刷新失败')).toBeNull()
    expect(screen.getByText('写作引擎探活异常，请稍后重试')).not.toBeNull()
    expect(screen.getByText('检索引擎探活异常，请稍后重试')).not.toBeNull()
})

test('rag status only shows healthy when the live probe is actually connected', async () => {
    setProjectModeUrl()
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
        if (path === '/api/project/info') {
            return Promise.resolve({
                project_info: { title: 'Night Rain Archive', genre: '都市异能' },
                dashboard_context: { project_initialized: true, project_root: 'C:/novel' },
                progress: { current_chapter: 1, total_words: 3607 },
            })
        }
        if (path === '/api/project/director-hub') {
            return Promise.resolve({
                current_chapter: 2,
                current_brief: {},
                story_plan: { anchor_chapter: 1, planning_horizon: 4, rationale: 'Story plan' },
                continuity: {},
                voice_bible: {},
            })
        }
        if (path === '/api/tasks/summary') return Promise.resolve([])
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') {
            return Promise.resolve({
                configured: true,
                embed_model: 'BAAI/bge-m3',
                effective_status: 'failed',
                connection_status: 'not_checked',
                connection_error: { code: 'RAG_TIMEOUT', details: { stage: 'embedding' } },
            })
        }
        return Promise.resolve({})
    })

    render(<App />)

    expect((await screen.findAllByText('项目总览')).length).toBeGreaterThan(0)
    expect(screen.getByText('检索引擎连接失败：embedding / RAG_TIMEOUT')).not.toBeNull()
    expect(screen.queryByText('检索引擎已配置 BAAI/bge-m3')).toBeNull()
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
            { kind: 'launch-task', taskType: 'write', payload: { chapter: 10 }, label: '继续第 10 章', variant: 'primary' },
        ],
    }]
    postJSONMock.mockRejectedValue(new Error('launch failed'))

    render(<App />)

    await user.click(await screen.findByRole('button', { name: '继续第 10 章' }))

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
        if (path === '/api/tasks/summary') return Promise.resolve([])
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })

    render(<App />)

    expect(await screen.findByRole('button', { name: '项目总览' })).not.toBeNull()
    expect(window.location.search).toContain('project_root=C%3A%2Fnovel')
    expect(window.location.search).not.toContain('page=')
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
        if (path === '/api/tasks/summary') return Promise.resolve([])
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
                next_recommended_action: '项目已初始化。下一步请先确认规划信息，再运行多章规划。',
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

test('planning profile save flushes project and task summaries immediately', async () => {
    const user = userEvent.setup()
    let projectInfoCalls = 0
    let taskSummaryCalls = 0

    setProjectModeUrl('control')
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/hub') return Promise.resolve(buildHubPayload())
        if (path === '/api/project/info') {
            projectInfoCalls += 1
            return Promise.resolve({
                project_info: { title: 'Night Rain Archive', genre: '都市异能' },
                dashboard_context: { project_initialized: true, project_root: 'C:/novel' },
                progress: { current_chapter: 1, total_words: 1200 },
            })
        }
        if (path === '/api/tasks/summary') {
            taskSummaryCalls += 1
            return Promise.resolve([])
        }
        if (path === '/api/project/planning-profile') {
            return Promise.resolve({
                profile: { story_logline: '旧的概括' },
                field_specs: [
                    { name: 'story_logline', label: '故事一句话', multiline: false, required: true },
                ],
                readiness: { ok: false, completed_fields: 0, total_required_fields: 1, blocking_items: [] },
                last_blocked: null,
            })
        }
        if (path === '/api/llm/status') return Promise.resolve({ installed: false })
        if (path === '/api/rag/status') return Promise.resolve({ configured: false })
        return Promise.resolve({})
    })
    postJSONMock.mockImplementation((path, payload) => {
        if (path === '/api/project/planning-profile') {
            return Promise.resolve({
                profile: payload,
                field_specs: [
                    { name: 'story_logline', label: '故事一句话', multiline: false, required: true },
                ],
                readiness: { ok: true, completed_fields: 1, total_required_fields: 1, blocking_items: [] },
                last_blocked: null,
            })
        }
        return Promise.resolve({})
    })

    render(<App />)

    const input = await screen.findByDisplayValue('旧的概括')
    await user.clear(input)
    await user.type(input, '新的概括')
    await user.click(screen.getByRole('button', { name: '保存规划信息' }))

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/project/planning-profile', { story_logline: '新的概括' })
        expect(projectInfoCalls).toBeGreaterThanOrEqual(2)
        expect(taskSummaryCalls).toBeGreaterThanOrEqual(2)
    })
})

test('opening an uninitialized folder from workbench pre-fills the create form', async () => {
    const user = userEvent.setup()

    window.history.replaceState({}, '', '/')
    postJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/pick-folder') {
            return Promise.resolve({ selected: true, project_root: 'D:\\tmp\\draft-project' })
        }
        if (path === '/api/workbench/open-project') {
            return Promise.resolve({
                opened: false,
                project_initialized: false,
                next_recommended_action: '该目录还没有初始化，可以直接改为新建项目。',
            })
        }
        return Promise.resolve({})
    })

    render(<App />)

    await user.click(await screen.findByRole('button', { name: '打开已有项目' }))

    await waitFor(() => {
        expect(postJSONMock).toHaveBeenCalledWith('/api/workbench/open-project', { project_root: 'D:\\tmp\\draft-project' })
        expect(screen.getByDisplayValue('D:\\tmp\\draft-project')).not.toBeNull()
    })
})

test('opening an existing folder surfaces real open-project errors instead of create fallback', async () => {
    const user = userEvent.setup()

    window.history.replaceState({}, '', '/')
    postJSONMock.mockImplementation((path) => {
        if (path === '/api/workbench/pick-folder') {
            return Promise.resolve({ selected: true, project_root: 'D:\\tmp\\broken-project' })
        }
        if (path === '/api/workbench/open-project') {
            return Promise.reject(new Error('state corrupted'))
        }
        return Promise.resolve({})
    })

    render(<App />)

    await user.click(await screen.findByRole('button', { name: '打开已有项目' }))

    await waitFor(() => {
        expect(screen.getAllByText('state corrupted').length).toBeGreaterThan(0)
        expect(screen.queryByDisplayValue('D:\\tmp\\broken-project')).toBeNull()
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
        if (path === '/api/tasks/summary') return Promise.resolve([])
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


