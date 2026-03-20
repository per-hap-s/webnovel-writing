import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

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

import { PlanningProfileSection } from './appSections.jsx'

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
                { field: 'outline_section::## 势力', label: '势力' },
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
    expect((await screen.findAllByText('势力')).length).toBeGreaterThan(0)
})
