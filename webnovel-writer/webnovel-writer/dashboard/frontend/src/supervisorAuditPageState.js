import {
    SUPERVISOR_AUDIT_PREFERENCES_KEY,
    buildSupervisorAuditPreferencePayload,
    buildSupervisorAuditQueryString,
    readSupervisorAuditQueryStateFromSearch,
} from './supervisorAuditState.js'

export function readSupervisorAuditPreferences() {
    if (typeof window === 'undefined' || !window.localStorage) return {}
    try {
        const raw = window.localStorage.getItem(SUPERVISOR_AUDIT_PREFERENCES_KEY)
        if (!raw) return {}
        return buildSupervisorAuditPreferencePayload(JSON.parse(raw))
    } catch {
        return {}
    }
}

export function writeSupervisorAuditPreferences(viewState) {
    if (typeof window === 'undefined' || !window.localStorage) return
    const payload = buildSupervisorAuditPreferencePayload(viewState)
    window.localStorage.setItem(SUPERVISOR_AUDIT_PREFERENCES_KEY, JSON.stringify(payload))
}

export function readSupervisorAuditQueryState() {
    if (typeof window === 'undefined') return {}
    return readSupervisorAuditQueryStateFromSearch(window.location.search || '')
}

export function writeSupervisorAuditQueryState({
    viewState,
    dashboardPageKey = 'page',
    dashboardPageValue = 'supervisor-audit',
}) {
    if (typeof window === 'undefined') return
    const query = buildSupervisorAuditQueryString({
        search: window.location.search || '',
        viewState,
        dashboardPageKey,
        dashboardPageValue,
    })
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`
    window.history.replaceState({}, '', nextUrl)
}
