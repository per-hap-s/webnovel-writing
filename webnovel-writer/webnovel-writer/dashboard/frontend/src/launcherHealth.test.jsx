import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const fetchJSONMock = vi.fn()
const postJSONMock = vi.fn()

vi.mock('./api.js', () => ({
    fetchJSON: (...args) => fetchJSONMock(...args),
    postJSON: (...args) => postJSONMock(...args),
    normalizeError: (error) => {
        if (error?.displayMessage) return error
        return {
            displayMessage: error?.message || String(error),
            code: error?.code || 'REQUEST_FAILED',
            rawMessage: error?.message || String(error),
            details: error?.details || null,
            statusCode: error?.statusCode,
        }
    },
}))

import { DataPageSection, ErrorNotice } from './appSections.jsx'

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
})

afterEach(() => {
    cleanup()
})

test('error notice hides internal code until diagnostic details are expanded', async () => {
    const user = userEvent.setup()

    render(
        <ErrorNotice
            title="核心数据刷新失败"
            error={{
                displayMessage: '创作工作台服务暂未返回有效接口数据，请刷新或重新启动工作台。',
                code: 'HTML_RESPONSE',
                rawMessage: '后端返回了页面内容而不是接口数据。',
                statusCode: 200,
                details: { path: '/api/project/director-hub' },
            }}
        />,
    )

    expect(screen.getByText('核心数据刷新失败')).not.toBeNull()
    expect(screen.getByText('创作工作台服务暂未返回有效接口数据，请刷新或重新启动工作台。')).not.toBeNull()
    expect(screen.queryByText(/错误码：/)).toBeNull()
    expect(screen.queryByText(/HTML_RESPONSE/)).toBeNull()

    await user.click(screen.getByText('查看诊断详情'))

    expect(screen.getByText(/HTML_RESPONSE/)).not.toBeNull()
    expect(screen.getByText(/HTTP 状态：200/)).not.toBeNull()
})

test('data page uses localized rolling-plan labels', async () => {
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/entities') return Promise.resolve([])
        if (path === '/api/relationships') return Promise.resolve([])
        if (path === '/api/chapters') {
            return Promise.resolve([{ chapter: 1, title: '第一章', word_count: 3600 }])
        }
        if (path === '/api/story-plans') {
            return Promise.resolve([{
                anchor_chapter: 1,
                planning_horizon: 4,
                updated_at: '2026-03-22T06:40:38Z',
                current_role: 'current-execution',
                current_goal: '推进当前卷主线',
                current_hook: '将压力导向更高风险场景',
                priority_threads: ['推进当前卷主线'],
                risk_flags: ['前期节奏偏低'],
            }])
        }
        return Promise.resolve([])
    })

    const SimpleTable = () => <div>table</div>

    render(<DataPageSection SimpleTable={SimpleTable} refreshToken={0} />)

    expect(await screen.findByText('多章规划摘要')).not.toBeNull()
    expect(screen.getByText('当前定位：当前执行')).not.toBeNull()
    expect(screen.getByText('本轮目标：推进当前卷主线')).not.toBeNull()
    expect(screen.getByText('章末钩子：将压力导向更高风险场景')).not.toBeNull()
    expect(screen.queryByText('Story Plans')).toBeNull()
    expect(screen.queryByText(/Hook/)).toBeNull()
})
