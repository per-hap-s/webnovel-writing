import { describe, expect, test } from 'vitest'

import {
    buildSupervisorAuditHealthMarkdown,
    buildSupervisorAuditRepairPreviewMarkdown,
    buildSupervisorAuditViewModel,
} from './supervisorAuditDerived.js'

describe('supervisor audit derived helpers', () => {
    test('does not synthesize chapter 0 for entries with empty chapter values', () => {
        const viewModel = buildSupervisorAuditViewModel({
            auditItems: [],
            auditLogEntries: [
                { stableKey: 'empty-chapter', chapter: '', title: '无章节字段的建议' },
                { stableKey: 'titled-chapter', title: '第 12 章 审计建议' },
            ],
            auditRepairReports: [],
            auditChecklists: [],
            selectedAuditRepairReportPath: '',
            selectedAuditChecklistPath: '',
            viewState: {
                category: 'all',
                action: 'all',
                status: 'all',
                chapter: 'all',
                view_mode: 'grouped',
                group_focus: 'all',
                stable_key: '',
                report_filter: 'all',
                report_sort: 'latest',
                report_path: '',
            },
        })

        expect(viewModel.auditChapterOptions.map((item) => item.value)).toEqual(['all', '12'])
    })

    test('health markdown exports aggregate sections from camelCase API fields', () => {
        const markdown = buildSupervisorAuditHealthMarkdown({
            projectInfo: { progress: { current_chapter: 8 } },
            health: {
                exists: true,
                healthy: false,
                total_lines: 10,
                nonempty_lines: 9,
                valid_entries: 7,
                issue_count: 2,
                issueCounts: { invalid_json: 1, future_schema: 1 },
                schemaStateCounts: { supported: 6, future: 1 },
                schemaVersionCounts: { 1: 6, 3: 1 },
                issues: [],
            },
        })

        expect(markdown).toContain('非 JSON 行：1')
        expect(markdown).toContain('未来 schema：1')
        expect(markdown).toContain('可兼容：6')
        expect(markdown).toContain('未来版本：1')
        expect(markdown).toContain('v1：6')
        expect(markdown).toContain('v3：1')
    })

    test('repair preview markdown exports action distribution from actionCounts', () => {
        const markdown = buildSupervisorAuditRepairPreviewMarkdown({
            projectInfo: { progress: { current_chapter: 8 } },
            preview: {
                exists: true,
                total_lines: 10,
                nonempty_lines: 9,
                repairable_count: 2,
                manual_review_count: 1,
                actionCounts: {
                    drop_line: 1,
                    rewrite_normalized_event: 1,
                    manual_review: 1,
                },
                proposals: [],
            },
        })

        expect(markdown).toContain('删除坏行：1')
        expect(markdown).toContain('重写为规范事件：1')
        expect(markdown).toContain('仅人工复核：1')
    })
})
