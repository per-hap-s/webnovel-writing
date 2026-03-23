import { beforeEach, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

const fetchJSONMock = vi.fn()
const postJSONMock = vi.fn()

vi.mock('./api.js', () => ({
    fetchJSON: (...args) => fetchJSONMock(...args),
    postJSON: (...args) => postJSONMock(...args),
    normalizeError: (error) => ({
        displayMessage: error?.message || String(error),
        code: 'REQUEST_FAILED',
        rawMessage: error?.message || String(error),
        details: null,
    }),
}))

vi.mock('./operatorAction.js', () => ({
    resolveSupervisorItemOperatorActions: (item) => item.operatorActions || [],
}))

vi.mock('./recoverySemantics.js', () => ({
    resolveSupervisorRecoverySemantics: () => null,
}))

import { SupervisorPage } from './supervisorPage.jsx'
import { SupervisorAuditPage } from './supervisorAuditPage.jsx'

beforeEach(() => {
    fetchJSONMock.mockReset()
    postJSONMock.mockReset()
    window.history.replaceState({}, '', '/')
})

test('supervisor page keeps localized recommendation copy Chinese-first', async () => {
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/supervisor/recommendations?include_dismissed=true') {
            return Promise.resolve([
                {
                    stableKey: 'approval:task-1',
                    title: '第 3 章待回写审批',
                    category: 'approval',
                    categoryLabel: '审批',
                    summary: '当前任务正在等待人工确认后再继续回写。',
                    detail: '不先处理这个审批，护栏推进无法安全往后继续。',
                    rationale: '人工审批是硬阻断，优先级高于继续创建任何新章节任务。',
                    actionLabel: '打开待审批任务',
                    trackingStatus: '',
                    operatorActions: [],
                },
                {
                    stableKey: 'review:task-2',
                    title: '第 4 章被审查关卡拦截',
                    category: 'review_block',
                    categoryLabel: '审查阻断',
                    summary: '当前章节存在必须先处理的审查阻断问题。',
                    detail: '先修复审查问题，再考虑继续下一章。',
                    rationale: '审查硬阻断说明本章还不满足安全推进条件。',
                    actionLabel: '打开阻断任务',
                    trackingStatus: '',
                    operatorActions: [],
                },
            ])
        }
        if (path === '/api/supervisor/checklists') {
            return Promise.resolve([
                {
                    relativePath: '.webnovel/supervisor/checklists/checklist-ch0003-20260323-100000.md',
                    chapter: 3,
                    title: '督办 Smoke 清单',
                    savedAt: '2026-03-23T10:00:00Z',
                    content: '# 督办 Smoke 清单',
                    summary: '已保存的督办清单',
                },
            ])
        }
        return Promise.resolve([])
    })

    render(
        <SupervisorPage
            projectInfo={{ progress: { current_chapter: 4, total_words: 24000 } }}
            tasks={[]}
            onTaskCreated={vi.fn()}
            onOpenTask={vi.fn()}
            onTasksMutated={vi.fn()}
        />,
    )

    expect(await screen.findByText('当前任务正在等待人工确认后再继续回写。')).toBeTruthy()
    expect(await screen.findByText('当前章节存在必须先处理的审查阻断问题。')).toBeTruthy()
    expect(screen.queryByText(/approval-gate/i)).toBeNull()
    expect(screen.queryByText(/hard blocking issue/i)).toBeNull()
})

test('supervisor audit page keeps future schema warning Chinese-first', async () => {
    fetchJSONMock.mockImplementation((path) => {
        if (path === '/api/supervisor/recommendations?include_dismissed=true') return Promise.resolve([])
        if (path === '/api/supervisor/checklists') {
            return Promise.resolve([
                {
                    relativePath: '.webnovel/supervisor/checklists/checklist-ch0003-20260323-100000.md',
                    chapter: 3,
                    title: '督办 Smoke 清单',
                    savedAt: '2026-03-23T10:00:00Z',
                    content: '# 督办 Smoke 清单',
                    summary: '已保存的督办清单',
                },
            ])
        }
        if (path === '/api/supervisor/audit-log') {
            return Promise.resolve([
                {
                    stableKey: 'future:task-1',
                    action: 'tracking_updated',
                    title: '未来结构事件',
                    summary: '用于验证未来结构兼容提示。',
                    timestamp: '2026-03-23T10:00:00Z',
                    schemaVersion: 3,
                    schemaState: 'future',
                    schemaWarning: '检测到审计结构版本 v3；当前仅确认兼容到 v2，请人工复核。',
                },
            ])
        }
        if (path === '/api/supervisor/audit-health') {
            return Promise.resolve({
                healthy: false,
                exists: true,
                issue_count: 1,
                issueCounts: { future_schema: 1 },
                schemaStateCounts: { future: 1 },
                schemaVersionCounts: { 3: 1 },
                issues: [
                    {
                        code: 'future_schema',
                        severity: 'warning',
                        message: '检测到审计结构版本 v3；当前仅确认兼容到 v2，请人工复核。',
                    },
                ],
            })
        }
        if (path === '/api/supervisor/audit-repair-preview') {
            return Promise.resolve({
                exists: true,
                nonempty_lines: 1,
                repairable_count: 0,
                manual_review_count: 1,
                proposals: [
                    {
                        line: 1,
                        action: 'manual_review',
                        severity: 'warning',
                        reason: '检测到审计结构版本 v3；当前仅确认兼容到 v2，请人工复核。',
                        issueCodes: ['future_schema'],
                    },
                ],
            })
        }
        if (path === '/api/supervisor/audit-repair-reports') {
            return Promise.resolve([
                {
                    filename: 'repair-report.json',
                    relativePath: '.webnovel/supervisor/audit-repair-reports/repair-report.json',
                    generatedAt: '2026-03-23T10:00:00Z',
                    changed: false,
                    manualReviewCount: 1,
                    content: {},
                },
            ])
        }
        return Promise.resolve([])
    })

    render(
        <SupervisorAuditPage
            projectInfo={{ progress: { current_chapter: 4, total_words: 24000 } }}
            tasks={[]}
            onTaskCreated={vi.fn()}
            onOpenTask={vi.fn()}
            onTasksMutated={vi.fn()}
        />,
    )

    expect(await screen.findAllByText(/检测到审计结构版本 v3；当前仅确认兼容到 v2，请人工复核。/)).not.toHaveLength(0)
    expect(screen.queryByText(/Detected audit schema/i)).toBeNull()
    expect(screen.queryByText(/through v2/i)).toBeNull()
    expect(screen.queryByText(/manual-only/i)).toBeNull()
})
