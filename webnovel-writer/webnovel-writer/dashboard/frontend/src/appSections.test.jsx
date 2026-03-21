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

import { PlanningProfileSection, ProjectBootstrapSection } from './appSections.jsx'

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
            { name: 'story_logline', label: '鏁呬簨涓€鍙ヨ瘽', multiline: false, required: true },
            { name: 'core_setting', label: '鏍稿績璁惧畾', multiline: true, required: true },
        ],
        readiness: {
            ok: false,
            completed_fields: 0,
            total_required_fields: 2,
            blocking_items: [
                { field: 'story_logline', label: '鏁呬簨涓€鍙ヨ瘽' },
                { field: 'outline_section::## 鍔垮姏', label: '鍔垮姏' },
            ],
        },
        last_blocked: {
            reason: 'planning_profile_incomplete',
            blocking_items: [{ field: 'story_logline', label: '鏁呬簨涓€鍙ヨ瘽' }],
        },
    })

    render(<PlanningProfileSection onSaved={vi.fn()} />)

    expect(await screen.findByText('待补信息')).not.toBeNull()
    expect((await screen.findAllByText('鏁呬簨涓€鍙ヨ瘽')).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('鍔垮姏')).length).toBeGreaterThan(0)
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
