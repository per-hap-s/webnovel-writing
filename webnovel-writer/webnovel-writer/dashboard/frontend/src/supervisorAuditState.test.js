import test from 'node:test'
import assert from 'node:assert/strict'

import {
    SUPERVISOR_AUDIT_QUERY_KEYS,
    SUPERVISOR_AUDIT_VIEW_DEFAULTS,
    buildInitialSupervisorAuditViewState,
    buildSupervisorAuditPreferencePayload,
    buildSupervisorAuditQueryPayload,
    buildSupervisorAuditQueryString,
    readSupervisorAuditQueryStateFromSearch,
    resolveVisibleAuditRepairReportPath,
} from './supervisorAuditState.js'

test('buildInitialSupervisorAuditViewState merges persisted and query state with defaults', () => {
    const state = buildInitialSupervisorAuditViewState({
        persisted: {
            category: 'review',
            report_sort: 'manual',
            view_mode: 'raw',
        },
        query: {
            report_filter: 'changed',
            stable_key: 'approval:task-1',
            report_path: '.webnovel/supervisor/audit-repair-reports/repair-report-1.json',
        },
    })

    assert.equal(state.category, 'review')
    assert.equal(state.report_sort, 'manual')
    assert.equal(state.report_filter, 'changed')
    assert.equal(state.stable_key, 'approval:task-1')
    assert.equal(state.report_path, '.webnovel/supervisor/audit-repair-reports/repair-report-1.json')
    assert.equal(state.view_mode, 'grouped')
    assert.equal(state.status, SUPERVISOR_AUDIT_VIEW_DEFAULTS.status)
})

test('readSupervisorAuditQueryStateFromSearch normalizes unsupported values back to defaults', () => {
    const state = readSupervisorAuditQueryStateFromSearch(
        '?sa_reports=invalid&sa_report_sort=weird&sa_view=broken&sa_focus=unknown',
    )

    assert.equal(state.report_filter, SUPERVISOR_AUDIT_VIEW_DEFAULTS.report_filter)
    assert.equal(state.report_sort, SUPERVISOR_AUDIT_VIEW_DEFAULTS.report_sort)
    assert.equal(state.view_mode, SUPERVISOR_AUDIT_VIEW_DEFAULTS.view_mode)
    assert.equal(state.group_focus, SUPERVISOR_AUDIT_VIEW_DEFAULTS.group_focus)
})

test('buildSupervisorAuditPreferencePayload keeps only persisted view-state fields', () => {
    const payload = buildSupervisorAuditPreferencePayload({
        category: 'approval',
        stable_key: 'approval:task-1',
        report_filter: 'manual_only',
        report_sort: 'impact',
        report_path: 'report-a.json',
    })

    assert.deepEqual(payload, {
        category: 'approval',
        action: 'all',
        status: 'all',
        chapter: 'all',
        view_mode: 'grouped',
        group_focus: 'all',
        report_filter: 'manual_only',
        report_sort: 'impact',
        report_path: 'report-a.json',
    })
})

test('buildSupervisorAuditQueryPayload keeps stable key for deep links', () => {
    const payload = buildSupervisorAuditQueryPayload({
        stable_key: 'approval:task-9',
        report_path: 'report-b.json',
    })

    assert.equal(payload.stable_key, 'approval:task-9')
    assert.equal(payload.report_path, 'report-b.json')
})

test('buildSupervisorAuditQueryString omits default values and keeps non-default deep links', () => {
    const query = buildSupervisorAuditQueryString({
        search: '?foo=bar',
        viewState: {
            category: 'approval',
            report_filter: 'manual_only',
            report_sort: 'impact',
            report_path: 'report-c.json',
        },
        dashboardPageKey: 'page',
    })

    const params = new URLSearchParams(query)
    assert.equal(params.get('foo'), 'bar')
    assert.equal(params.get('page'), 'supervisor-audit')
    assert.equal(params.get(SUPERVISOR_AUDIT_QUERY_KEYS.category), 'approval')
    assert.equal(params.get(SUPERVISOR_AUDIT_QUERY_KEYS.report_filter), 'manual_only')
    assert.equal(params.get(SUPERVISOR_AUDIT_QUERY_KEYS.report_sort), 'impact')
    assert.equal(params.get(SUPERVISOR_AUDIT_QUERY_KEYS.report_path), 'report-c.json')
    assert.equal(params.has(SUPERVISOR_AUDIT_QUERY_KEYS.view_mode), false)
})

test('resolveVisibleAuditRepairReportPath prefers selected visible report and falls back safely', () => {
    const reports = [
        { relativePath: 'report-2.json' },
        { relativePath: 'report-1.json' },
    ]

    assert.equal(resolveVisibleAuditRepairReportPath(reports, 'report-1.json'), 'report-1.json')
    assert.equal(resolveVisibleAuditRepairReportPath(reports, 'missing.json'), 'report-2.json')
    assert.equal(resolveVisibleAuditRepairReportPath([], 'missing.json'), '')
})
