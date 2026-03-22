import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const fetchJSONMock = vi.fn()
const postJSONMock = vi.fn()

vi.mock('./api.js', () => ({
    fetchJSON: (...args) => fetchJSONMock(...args),
    postJSON: (...args) => postJSONMock(...args),
    normalizeError: (error) => ({
        displayMessage: error?.message || String(error),
        code: error?.code || 'REQUEST_FAILED',
        rawMessage: error?.message || String(error),
        details: error?.details || null,
    }),
}))

import { PlanningProfileSection, ProjectBootstrapSection, TaskLauncherSection } from './appSections.jsx'

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
})

afterEach(() => {
    cleanup()
})

test('planning profile renders blocking items from readiness payload', async () => {
    fetchJSONMock.mockResolvedValue({
        profile: { story_logline: '' },
        field_specs: [
            { name: 'story_logline', label: '故事一句话', multiline: false, required: true },
            { name: 'core_setting', label: '核心设定', multiline: true, required: true },
        ],
        readiness: {
            ok: false,
            completed_fields: 0,
            total_required_fields: 2,
            blocking_items: [
                { field: 'story_logline', label: '故事一句话' },
                { field: 'outline_section::hook', label: '开篇钩子' },
            ],
        },
        last_blocked: {
            reason: 'planning_profile_incomplete',
            blocking_items: [{ field: 'story_logline', label: '故事一句话' }],
        },
    })

    render(<PlanningProfileSection onSaved={vi.fn()} />)

    expect(await screen.findByText('待补信息')).not.toBeNull()
    expect((await screen.findAllByText('故事一句话')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('开篇钩子')).length).toBeGreaterThan(0)
})

test('bootstrap section collapses duplicate create form for initialized current project', async () => {
    const user = userEvent.setup()

    render(
        <ProjectBootstrapSection
            currentProjectRoot="D:\\novels\\night-rain"
            currentTitle="Night Rain Archive"
            currentGenre="都市异能"
            projectInitialized
            onSuccess={vi.fn()}
        />,
    )

    expect(screen.getByText('当前目录已是可用项目')).not.toBeNull()
    expect(screen.queryByLabelText('项目根目录')).toBeNull()

    await user.click(screen.getByRole('button', { name: '改用新目录新建项目' }))

    expect(screen.getByLabelText('项目根目录')).not.toBeNull()
    expect(screen.getByRole('button', { name: '创建项目' }).hasAttribute('disabled')).toBe(true)
})

test('write launcher defaults to auto writeback after brief approval', async () => {
    const user = userEvent.setup()
    postJSONMock.mockResolvedValue({ id: 'task-write-1' })

    render(
        <TaskLauncherSection
            template={{ key: 'write', title: '撰写章节', fields: ['chapter', 'mode', 'require_manual_approval'] }}
            onCreated={vi.fn()}
            MODE_OPTIONS={[{ value: 'standard', label: '标准' }]}
            suggestedChapter={3}
        />,
    )

    const checkbox = screen.getByRole('checkbox')
    expect(checkbox.checked).toBe(false)

    await user.click(screen.getByRole('button', { name: '创建任务' }))

    expect(postJSONMock).toHaveBeenCalledWith('/api/tasks/write', {
        chapter: 3,
        mode: 'standard',
        require_manual_approval: false,
    })
})
