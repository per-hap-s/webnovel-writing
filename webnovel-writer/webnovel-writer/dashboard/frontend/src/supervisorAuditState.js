export const SUPERVISOR_AUDIT_PREFERENCES_KEY = 'dashboard.supervisor-audit.preferences'

export const SUPERVISOR_AUDIT_QUERY_KEYS = {
    category: 'sa_category',
    action: 'sa_action',
    status: 'sa_status',
    chapter: 'sa_chapter',
    view_mode: 'sa_view',
    group_focus: 'sa_focus',
    stable_key: 'sa_key',
    report_filter: 'sa_reports',
    report_sort: 'sa_report_sort',
    report_path: 'sa_report',
}

export const AUDIT_REPAIR_REPORT_SORT_OPTIONS = [
    { value: 'latest', label: '\u6700\u65b0\u4f18\u5148' },
    { value: 'impact', label: '\u4fee\u590d\u5f71\u54cd\u4f18\u5148' },
    { value: 'manual', label: '\u4eba\u5de5\u590d\u6838\u4f18\u5148' },
    { value: 'changed', label: '\u5df2\u6539\u52a8\u4f18\u5148' },
]

export const SUPERVISOR_AUDIT_VIEW_DEFAULTS = {
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
}

const ALLOWED_VIEW_MODES = new Set(['grouped', 'raw'])
const ALLOWED_GROUP_FOCUS = new Set(['all', 'actionable', 'open', 'in_progress', 'completed', 'dismissed', 'archived'])
const ALLOWED_REPORT_FILTERS = new Set(['all', 'changed', 'manual_only', 'unchanged'])
const ALLOWED_REPORT_SORTS = new Set(AUDIT_REPAIR_REPORT_SORT_OPTIONS.map((item) => item.value))

function normalizeSupervisorAuditStateValue(field, value) {
    const text = String(value || '').trim()
    if (!text) return SUPERVISOR_AUDIT_VIEW_DEFAULTS[field]
    if (field === 'view_mode') return ALLOWED_VIEW_MODES.has(text) ? text : SUPERVISOR_AUDIT_VIEW_DEFAULTS.view_mode
    if (field === 'group_focus') return ALLOWED_GROUP_FOCUS.has(text) ? text : SUPERVISOR_AUDIT_VIEW_DEFAULTS.group_focus
    if (field === 'report_filter') return ALLOWED_REPORT_FILTERS.has(text) ? text : SUPERVISOR_AUDIT_VIEW_DEFAULTS.report_filter
    if (field === 'report_sort') return ALLOWED_REPORT_SORTS.has(text) ? text : SUPERVISOR_AUDIT_VIEW_DEFAULTS.report_sort
    return text
}

export function normalizeSupervisorAuditViewState(raw = {}) {
    const nextState = {}
    Object.keys(SUPERVISOR_AUDIT_VIEW_DEFAULTS).forEach((field) => {
        nextState[field] = normalizeSupervisorAuditStateValue(field, raw?.[field])
    })
    if (nextState.stable_key) {
        nextState.view_mode = 'grouped'
    }
    return nextState
}

export function buildInitialSupervisorAuditViewState({ persisted = {}, query = {} } = {}) {
    return normalizeSupervisorAuditViewState({
        ...SUPERVISOR_AUDIT_VIEW_DEFAULTS,
        ...(persisted || {}),
        ...(query || {}),
    })
}

export function buildSupervisorAuditPreferencePayload(viewState = {}) {
    const normalized = normalizeSupervisorAuditViewState(viewState)
    return {
        category: normalized.category,
        action: normalized.action,
        status: normalized.status,
        chapter: normalized.chapter,
        view_mode: normalized.view_mode,
        group_focus: normalized.group_focus,
        report_filter: normalized.report_filter,
        report_sort: normalized.report_sort,
        report_path: normalized.report_path,
    }
}

export function buildSupervisorAuditQueryPayload(viewState = {}) {
    const normalized = normalizeSupervisorAuditViewState(viewState)
    return {
        ...buildSupervisorAuditPreferencePayload(normalized),
        stable_key: normalized.stable_key,
    }
}

export function readSupervisorAuditQueryStateFromSearch(search = '') {
    const params = new URLSearchParams(search || '')
    return normalizeSupervisorAuditViewState(
        Object.fromEntries(Object.entries(SUPERVISOR_AUDIT_QUERY_KEYS).map(([field, key]) => [field, String(params.get(key) || '').trim()])),
    )
}

export function buildSupervisorAuditQueryString({
    search = '',
    viewState = {},
    dashboardPageKey = 'page',
    dashboardPageValue = 'supervisor-audit',
} = {}) {
    const params = new URLSearchParams(search || '')
    const normalized = buildSupervisorAuditQueryPayload(viewState)
    params.set(dashboardPageKey, dashboardPageValue)
    Object.entries(SUPERVISOR_AUDIT_QUERY_KEYS).forEach(([field, key]) => {
        const value = normalized[field]
        if (
            !value
            || value === 'all'
            || (field === 'view_mode' && value === SUPERVISOR_AUDIT_VIEW_DEFAULTS.view_mode)
            || (field === 'report_sort' && value === SUPERVISOR_AUDIT_VIEW_DEFAULTS.report_sort)
        ) {
            params.delete(key)
            return
        }
        params.set(key, value)
    })
    return params.toString()
}

export function resolveVisibleAuditRepairReportPath(reports = [], selectedPath = '') {
    const normalizedSelectedPath = String(selectedPath || '').trim()
    if (normalizedSelectedPath && reports.some((item) => item?.relativePath === normalizedSelectedPath)) {
        return normalizedSelectedPath
    }
    return String(reports[0]?.relativePath || '').trim()
}
