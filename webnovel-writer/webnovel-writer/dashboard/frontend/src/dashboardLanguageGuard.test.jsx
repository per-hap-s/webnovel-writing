import { beforeEach, expect, test, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

const fetchJSONMock = vi.fn()
const fetchTextMock = vi.fn()
const postJSONMock = vi.fn()

vi.mock('./api.js', () => ({
    fetchJSON: (...args) => fetchJSONMock(...args),
    fetchText: (...args) => fetchTextMock(...args),
    postJSON: (...args) => postJSONMock(...args),
    normalizeError: (error) => ({
        displayMessage: error?.message || String(error),
        code: error?.code || 'REQUEST_FAILED',
        rawMessage: error?.message || String(error),
        details: error?.details || null,
    }),
}))

import { QualityPageSection } from './appSections.jsx'
import { TaskCenterTaskList } from './taskCenterTaskList.jsx'
import { WorkbenchPage } from './workbenchPage.jsx'

beforeEach(() => {
    fetchJSONMock.mockReset()
    fetchTextMock.mockReset()
    postJSONMock.mockReset()
})

test('workbench page uses unified Chinese labels for project entry and empty states', () => {
    const { rerender } = render(
        <WorkbenchPage
            hubData={{
                workspace_root: 'D:/workspace',
                current_project: {
                    project_root: 'D:/workspace/project-a',
                    title: '夜雨档案',
                    genre: '都市异能',
                    is_initialized: true,
                },
                missing_projects: [],
            }}
            tab="hub"
            currentProjectRoot="D:/workspace/project-a"
            landingPreferenceKey="dashboard.landing"
            landingPreferences={[{ value: 'hub', label: '优先打开工作台' }]}
            onNavigate={vi.fn()}
            onTabChange={vi.fn()}
            onOpenProject={vi.fn()}
            onRefresh={vi.fn()}
        />,
    )

    expect(screen.getAllByRole('button', { name: '打开已有项目' }).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '进入项目' })).toBeNull()

    rerender(
        <WorkbenchPage
            hubData={{
                workspace_root: 'D:/workspace',
                current_project: null,
                missing_projects: [],
            }}
            tab="hub"
            currentProjectRoot=""
            landingPreferenceKey="dashboard.landing"
            landingPreferences={[{ value: 'hub', label: '优先打开工作台' }]}
            onNavigate={vi.fn()}
            onTabChange={vi.fn()}
            onOpenProject={vi.fn()}
            onRefresh={vi.fn()}
        />,
    )

    expect(screen.getByText('暂无已打开项目。')).not.toBeNull()
    expect(screen.getByText('暂无失效项目记录。')).not.toBeNull()
    expect(screen.queryByText('没有失效项目记录。')).toBeNull()
})

test('quality page keeps empty-state copy Chinese-first', async () => {
    fetchJSONMock.mockResolvedValue([])

    render(
        <QualityPageSection
            refreshToken={0}
            onMutated={vi.fn()}
            SimpleTable={({ rows }) => <div>{rows.length}</div>}
            translateColumnLabel={(value) => value}
            formatCell={(value) => String(value)}
        />,
    )

    await waitFor(() => {
        expect(screen.getByText('暂无审查指标')).not.toBeNull()
    })

    expect(screen.getByText('暂无待处理失效事实')).not.toBeNull()
    expect(screen.getByText('暂无清单评分')).not.toBeNull()
    expect(screen.getByText('暂无检索记录')).not.toBeNull()
    expect(screen.getByText('暂无工具统计')).not.toBeNull()
    expect(screen.queryByText(/overall_score/i)).toBeNull()
    expect(screen.queryByText(/query_type/i)).toBeNull()
    expect(screen.queryByText(/tool_name/i)).toBeNull()
})

test('task center list keeps action labels and empty state Chinese-first', () => {
    const onSelectTask = vi.fn()
    const onTaskPrimaryActionClick = vi.fn()

    const { rerender } = render(
        <TaskCenterTaskList
            tasks={[
                {
                    id: 'task-1',
                    task_type: 'write',
                    status: 'queued',
                    current_step: 'plan',
                    runtime_status: null,
                },
            ]}
            selectedTaskId={null}
            runtimeNow={Date.now()}
            taskActionState={{ pendingActionKey: '' }}
            onSelectTask={onSelectTask}
            onTaskPrimaryActionClick={onTaskPrimaryActionClick}
            translateTaskType={() => '写作任务'}
            translateTaskStatus={() => '排队中'}
            translateStepName={() => '规划'}
            resolveTaskStatusLabel={() => '排队中'}
            resolveCurrentStepLabel={() => '规划'}
            resolveTargetLabel={() => '第 1 章'}
        />,
    )

    expect(screen.getByRole('button', { name: '查看任务' })).not.toBeNull()
    expect(screen.getByRole('button', { name: '执行下一步' })).not.toBeNull()
    expect(screen.queryByText(/queued|running|awaiting|failed|interrupted/i)).toBeNull()

    rerender(
        <TaskCenterTaskList
            tasks={[]}
            selectedTaskId={null}
            runtimeNow={Date.now()}
            taskActionState={{ pendingActionKey: '' }}
            onSelectTask={onSelectTask}
            onTaskPrimaryActionClick={onTaskPrimaryActionClick}
            translateTaskType={() => '写作任务'}
            translateTaskStatus={() => '排队中'}
            translateStepName={() => '规划'}
            resolveTaskStatusLabel={() => '排队中'}
            resolveCurrentStepLabel={() => '规划'}
            resolveTargetLabel={() => '第 1 章'}
        />,
    )

    expect(screen.getByText('暂无任务')).not.toBeNull()
})

test('verification workbench page keeps empty-state copy Chinese-first', async () => {
    fetchJSONMock.mockResolvedValue({
        workspace_root: 'D:/workspace',
        active_execution: null,
        runs: [],
    })

    render(
        <WorkbenchPage
            hubData={{
                workspace_root: 'D:/workspace',
                current_project: null,
                missing_projects: [],
            }}
            tab="verification"
            currentProjectRoot=""
            landingPreferenceKey="dashboard.landing"
            landingPreferences={[{ value: 'hub', label: '优先打开工作台' }]}
            onNavigate={vi.fn()}
            onTabChange={vi.fn()}
            onOpenProject={vi.fn()}
            onRefresh={vi.fn()}
        />,
    )

    await waitFor(() => {
        expect(screen.getByText('当前没有正在运行的多子代理验证。')).not.toBeNull()
    })

    expect(screen.getByText('还没有多子代理验证历史。')).not.toBeNull()
    expect(screen.getByText('当前没有失败步骤日志可查看。')).not.toBeNull()
    expect(screen.queryByText(/Multi-Agent|artifact/i)).toBeNull()
})
