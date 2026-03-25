import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'
import {
    AUDIT_REPAIR_REPORT_SORT_OPTIONS,
    buildSupervisorAuditQueryString,
    buildInitialSupervisorAuditViewState,
} from './supervisorAuditState.js'
import {
    SupervisorAuditChecklistArchivePanel,
    SupervisorAuditFilterPanel,
    SupervisorAuditHealthPanel,
    SupervisorAuditRepairArchivePanel,
    SupervisorAuditRepairPreviewPanel,
    SupervisorAuditTimelinePanel,
} from './supervisorAuditPanels.jsx'
import { resolveSupervisorItemOperatorActions } from './operatorAction.js'
import { executeOperatorAction as executeRuntimeOperatorAction } from './operatorActionRuntime.js'
import { MetricCard, downloadTextFile, formatNumber, formatTimestampShort } from './dashboardPageCommon.jsx'
import { renderOperatorActionButtons } from './operatorActionButtons.jsx'
import { ErrorNotice } from './appSections.jsx'
import {
    AUDIT_GROUP_FOCUS_OPTIONS,
    SUPERVISOR_STATUS_FILTER_OPTIONS,
    buildAuditTaskRuntimeSummary,
    buildSupervisorAuditGroupAnchorId,
    buildSupervisorAuditHealthMarkdown,
    buildSupervisorAuditMarkdown,
    buildSupervisorAuditRepairPreviewMarkdown,
    buildSupervisorAuditSchemaLabel,
    buildSupervisorAuditViewModel,
    formatAuditRepairReportSummary,
    formatSupervisorAuditAction,
    formatSupervisorAuditHealthIssueLabel,
    formatSupervisorAuditRepairActionLabel,
    formatSupervisorAuditStatusSnapshot,
    formatSupervisorDismissReason,
    formatSupervisorTrackingStatus,
} from './supervisorAuditDerived.js'
import {
    readSupervisorAuditPreferences,
    readSupervisorAuditQueryState,
    writeSupervisorAuditPreferences,
    writeSupervisorAuditQueryState,
} from './supervisorAuditPageState.js'

const DASHBOARD_PAGE_QUERY_KEY = 'page'

export function SupervisorAuditPage({ projectInfo, tasks, onTaskCreated, onOpenTask, onTasksMutated }) {
    const [auditError, setAuditError] = useState(null)
    const [auditLoadError, setAuditLoadError] = useState(null)
    const [auditSubmitting, setAuditSubmitting] = useState(false)
    const [auditItems, setAuditItems] = useState([])
    const [auditLogEntries, setAuditLogEntries] = useState([])
    const [auditHealth, setAuditHealth] = useState(null)
    const [auditRepairPreview, setAuditRepairPreview] = useState(null)
    const [auditRepairReports, setAuditRepairReports] = useState([])
    const [auditChecklists, setAuditChecklists] = useState([])
    const [auditRefreshToken, setAuditRefreshToken] = useState(0)
    const initialAuditViewState = useMemo(
        () => buildInitialSupervisorAuditViewState({
            persisted: readSupervisorAuditPreferences(),
            query: readSupervisorAuditQueryState(),
        }),
        [],
    )
    const [auditCategoryFilter, setAuditCategoryFilter] = useState(initialAuditViewState.category)
    const [auditActionFilter, setAuditActionFilter] = useState(initialAuditViewState.action)
    const [auditStatusFilter, setAuditStatusFilter] = useState(initialAuditViewState.status)
    const [auditChapterFilter, setAuditChapterFilter] = useState(initialAuditViewState.chapter)
    const [auditViewMode, setAuditViewMode] = useState(initialAuditViewState.view_mode)
    const [auditGroupFocus, setAuditGroupFocus] = useState(initialAuditViewState.group_focus)
    const [auditFocusedStableKey, setAuditFocusedStableKey] = useState(initialAuditViewState.stable_key)
    const [auditRepairReportFilter, setAuditRepairReportFilter] = useState(initialAuditViewState.report_filter)
    const [auditRepairReportSortMode, setAuditRepairReportSortMode] = useState(initialAuditViewState.report_sort)
    const [selectedAuditRepairReportPath, setSelectedAuditRepairReportPath] = useState(initialAuditViewState.report_path)
    const [selectedAuditChecklistPath, setSelectedAuditChecklistPath] = useState('')
    const loadSeqRef = useRef(0)

    const auditViewState = {
        category: auditCategoryFilter,
        action: auditActionFilter,
        status: auditStatusFilter,
        chapter: auditChapterFilter,
        view_mode: auditViewMode,
        group_focus: auditGroupFocus,
        stable_key: auditFocusedStableKey,
        report_filter: auditRepairReportFilter,
        report_sort: auditRepairReportSortMode,
        report_path: selectedAuditRepairReportPath,
    }

    useEffect(() => {
        writeSupervisorAuditPreferences(auditViewState)
    }, [
        auditCategoryFilter,
        auditActionFilter,
        auditStatusFilter,
        auditChapterFilter,
        auditViewMode,
        auditGroupFocus,
        auditRepairReportFilter,
        auditRepairReportSortMode,
        selectedAuditRepairReportPath,
    ])

    useEffect(() => {
        writeSupervisorAuditQueryState({
            viewState: auditViewState,
            dashboardPageKey: DASHBOARD_PAGE_QUERY_KEY,
            dashboardPageValue: 'supervisor-audit',
        })
    }, [
        auditCategoryFilter,
        auditActionFilter,
        auditStatusFilter,
        auditChapterFilter,
        auditViewMode,
        auditGroupFocus,
        auditFocusedStableKey,
        auditRepairReportFilter,
        auditRepairReportSortMode,
        selectedAuditRepairReportPath,
    ])

    useEffect(() => {
        const loadSeq = ++loadSeqRef.current
        let cancelled = false

        Promise.allSettled([
            fetchJSON('/api/supervisor/recommendations?include_dismissed=true'),
            fetchJSON('/api/supervisor/checklists', { limit: 20 }),
            fetchJSON('/api/supervisor/audit-log', { limit: 200 }),
            fetchJSON('/api/supervisor/audit-health', { issue_limit: 20 }),
            fetchJSON('/api/supervisor/audit-repair-preview', { proposal_limit: 20 }),
            fetchJSON('/api/supervisor/audit-repair-reports', { limit: 20 }),
        ])
            .then(([itemsResult, checklistsResult, logEntriesResult, healthResult, repairPreviewResult, repairReportsResult]) => {
                if (cancelled || loadSeq !== loadSeqRef.current) return

                const errors = []
                if (itemsResult.status === 'fulfilled') {
                    setAuditItems(Array.isArray(itemsResult.value) ? itemsResult.value : [])
                } else {
                    errors.push(normalizeError(itemsResult.reason))
                }

                if (checklistsResult.status === 'fulfilled') {
                    setAuditChecklists(Array.isArray(checklistsResult.value) ? checklistsResult.value : [])
                } else {
                    errors.push(normalizeError(checklistsResult.reason))
                }

                if (logEntriesResult.status === 'fulfilled') {
                    setAuditLogEntries(Array.isArray(logEntriesResult.value) ? logEntriesResult.value : [])
                } else {
                    errors.push(normalizeError(logEntriesResult.reason))
                }

                if (healthResult.status === 'fulfilled') {
                    setAuditHealth(healthResult.value || null)
                } else {
                    errors.push(normalizeError(healthResult.reason))
                }

                if (repairPreviewResult.status === 'fulfilled') {
                    setAuditRepairPreview(repairPreviewResult.value || null)
                } else {
                    errors.push(normalizeError(repairPreviewResult.reason))
                }

                if (repairReportsResult.status === 'fulfilled') {
                    setAuditRepairReports(Array.isArray(repairReportsResult.value) ? repairReportsResult.value : [])
                } else {
                    errors.push(normalizeError(repairReportsResult.reason))
                }

                setAuditLoadError(errors[0] || null)
            })
            .catch((err) => {
                if (cancelled || loadSeq !== loadSeqRef.current) return
                setAuditLoadError(normalizeError(err))
            })
        return () => {
            cancelled = true
            loadSeqRef.current += 1
        }
    }, [tasks, projectInfo?.progress?.current_chapter, auditRefreshToken])

    const auditDerived = useMemo(
        () => buildSupervisorAuditViewModel({
            auditItems,
            auditLogEntries,
            auditRepairReports,
            auditChecklists,
            selectedAuditRepairReportPath,
            selectedAuditChecklistPath,
            viewState: auditViewState,
        }),
        [
            auditItems,
            auditLogEntries,
            auditRepairReports,
            auditChecklists,
            selectedAuditRepairReportPath,
            selectedAuditChecklistPath,
            auditCategoryFilter,
            auditActionFilter,
            auditStatusFilter,
            auditChapterFilter,
            auditViewMode,
            auditGroupFocus,
            auditFocusedStableKey,
            auditRepairReportFilter,
            auditRepairReportSortMode,
        ],
    )

    const {
        auditCategoryOptions,
        auditActionOptions,
        auditChapterOptions,
        auditItemsByStableKey,
        filteredAuditLogEntries,
        filteredGroupedAuditLogEntries,
        auditRepairReportSummary,
        sortedAuditRepairReports,
        nextVisiblePath,
        selectedVisibleAuditRepairReport,
        auditSummary,
        checklistLookup,
        selectedAuditChecklist,
        auditFocusState,
    } = auditDerived

    useEffect(() => {
        if (selectedAuditRepairReportPath !== nextVisiblePath) {
            setSelectedAuditRepairReportPath(nextVisiblePath)
        }
    }, [selectedAuditRepairReportPath, nextVisiblePath])

    async function executeAuditOperatorAction(action) {
        if (!action || auditSubmitting || action.disabled) return
        setAuditSubmitting(true)
        setAuditError(null)
        try {
            await executeRuntimeOperatorAction({
                action,
                postJSON,
                onOpenTask,
                onTaskCreated: (response, nextAction) => {
                    if (typeof onTaskCreated === 'function') {
                        onTaskCreated(response, nextAction)
                        return
                    }
                    if (response?.id) {
                        onOpenTask(response.id)
                    }
                },
                onTasksMutated: () => {
                    if (typeof onTasksMutated === 'function') {
                        onTasksMutated()
                    }
                },
            })
        } catch (err) {
            setAuditError(normalizeError(err))
        } finally {
            setAuditSubmitting(false)
        }
    }

    async function handleAuditGroupAction(item, action) {
        const operatorAction = action || resolveSupervisorItemOperatorActions(item)[0] || null
        await executeAuditOperatorAction(operatorAction)
    }

    async function handleAuditGroupTracking(item, status) {
        if (!item?.stableKey || auditSubmitting) return
        setAuditSubmitting(true)
        setAuditError(null)
        try {
            await postJSON('/api/supervisor/tracking', {
                stable_key: item.stableKey,
                fingerprint: item.fingerprint || item.stableKey,
                status,
                note: item.trackingNote || '',
                linked_task_id: item.linkedTaskId || '',
                linked_checklist_path: item.linkedChecklistPath || '',
            })
            setAuditItems((current) => current.map((candidate) => (
                candidate.stableKey === item.stableKey
                    ? { ...candidate, trackingStatus: status, trackingLabel: formatSupervisorTrackingStatus(status), trackingUpdatedAt: new Date().toISOString() }
                    : candidate
            )))
            setAuditRefreshToken((current) => current + 1)
        } catch (err) {
            setAuditError(normalizeError(err))
        } finally {
            setAuditSubmitting(false)
        }
    }

    async function handleAuditGroupUndismiss(item) {
        if (!item?.stableKey || auditSubmitting) return
        setAuditSubmitting(true)
        setAuditError(null)
        try {
            await postJSON('/api/supervisor/undismiss', {
                stable_key: item.stableKey,
                fingerprint: item.fingerprint || item.stableKey,
            })
            setAuditItems((current) => current.map((candidate) => (
                candidate.stableKey === item.stableKey
                    ? { ...candidate, dismissed: false, dismissedAt: null, dismissalReason: '', dismissalNote: '' }
                    : candidate
            )))
            setAuditRefreshToken((current) => current + 1)
        } catch (err) {
            setAuditError(normalizeError(err))
        } finally {
            setAuditSubmitting(false)
        }
    }

    async function handleAuditGroupTrackingClear(item) {
        if (!item?.stableKey || auditSubmitting) return
        setAuditSubmitting(true)
        setAuditError(null)
        try {
            await postJSON('/api/supervisor/tracking/clear', {
                stable_key: item.stableKey,
                fingerprint: item.fingerprint || item.stableKey,
            })
            setAuditItems((current) => current.map((candidate) => (
                candidate.stableKey === item.stableKey
                    ? { ...candidate, trackingStatus: '', trackingLabel: '', trackingNote: '', linkedTaskId: '', linkedChecklistPath: '', trackingUpdatedAt: null }
                    : candidate
            )))
            setAuditRefreshToken((current) => current + 1)
        } catch (err) {
            setAuditError(normalizeError(err))
        } finally {
            setAuditSubmitting(false)
        }
    }

    async function handleCopyAuditGroupLink(stableKey) {
        const nextState = { ...auditViewState, view_mode: 'grouped', stable_key: stableKey }
        const query = buildSupervisorAuditQueryString({
            search: window.location.search || '',
            viewState: nextState,
            dashboardPageKey: DASHBOARD_PAGE_QUERY_KEY,
            dashboardPageValue: 'supervisor-audit',
        })
        writeSupervisorAuditQueryState({
            viewState: nextState,
            dashboardPageKey: DASHBOARD_PAGE_QUERY_KEY,
            dashboardPageValue: 'supervisor-audit',
        })
        const nextUrl = `${window.location.origin}${window.location.pathname}${query ? `?${query}` : ''}`
        try {
            await navigator.clipboard.writeText(nextUrl)
            setAuditFocusedStableKey(stableKey)
        } catch (err) {
            setAuditError(normalizeError(err))
        }
    }

    function handleResetAuditEventFilters() {
        setAuditCategoryFilter('all')
        setAuditActionFilter('all')
        setAuditStatusFilter('all')
        setAuditChapterFilter('all')
    }

    function handleResetAuditGroupFilters() {
        setAuditGroupFocus('all')
        setAuditFocusedStableKey('')
    }

    function runAuditDownload(action) {
        try {
            setAuditError(null)
            action()
        } catch (err) {
            setAuditError(normalizeError(err))
        }
    }

    function handleDownloadAuditMarkdown() {
        runAuditDownload(() => {
            downloadTextFile(
                `supervisor-audit-ch${String(projectInfo?.progress?.current_chapter || 0).padStart(4, '0')}.md`,
                buildSupervisorAuditMarkdown({
                    projectInfo,
                    entries: filteredAuditLogEntries,
                    tasks,
                    filters: {
                        category: auditCategoryFilter,
                        action: auditActionFilter,
                        status: auditStatusFilter,
                        chapter: auditChapterFilter,
                        view_mode: auditViewMode,
                        group_focus: auditGroupFocus,
                    },
                }),
                'text/markdown;charset=utf-8',
            )
        })
    }

    function handleDownloadAuditJson() {
        runAuditDownload(() => {
            downloadTextFile('supervisor-audit.json', JSON.stringify(filteredAuditLogEntries, null, 2), 'application/json;charset=utf-8')
        })
    }

    function handleDownloadAuditHealthMarkdown() {
        runAuditDownload(() => {
            downloadTextFile('supervisor-audit-health.md', buildSupervisorAuditHealthMarkdown({ projectInfo, health: auditHealth }), 'text/markdown;charset=utf-8')
        })
    }

    function handleDownloadAuditHealthJson() {
        runAuditDownload(() => {
            downloadTextFile('supervisor-audit-health.json', JSON.stringify(auditHealth || {}, null, 2), 'application/json;charset=utf-8')
        })
    }

    function handleDownloadAuditRepairPreviewMarkdown() {
        runAuditDownload(() => {
            downloadTextFile('supervisor-audit-repair-preview.md', buildSupervisorAuditRepairPreviewMarkdown({ projectInfo, preview: auditRepairPreview }), 'text/markdown;charset=utf-8')
        })
    }

    function handleDownloadAuditRepairPreviewJson() {
        runAuditDownload(() => {
            downloadTextFile('supervisor-audit-repair-preview.json', JSON.stringify(auditRepairPreview || {}, null, 2), 'application/json;charset=utf-8')
        })
    }

    function handleDownloadAuditRepairReport(item) {
        if (!item) return
        runAuditDownload(() => {
            downloadTextFile(item.filename || 'repair-report.json', JSON.stringify(item.content || item, null, 2), 'application/json;charset=utf-8')
        })
    }

    function handleDownloadAuditChecklist(item) {
        if (!item?.content) return
        runAuditDownload(() => {
            downloadTextFile(item.filename || 'supervisor-checklist.md', item.content, 'text/markdown;charset=utf-8')
        })
    }

    return (
        <div className="page-grid">
            <section className="panel hero-panel">
                <div className="panel-title">督办审计视图</div>
                <div className="tiny">建议时间线与原始事件流在这里统一查看。</div>
                <div className="metric-grid">
                    <MetricCard label="建议总数" value={formatNumber(auditSummary.total)} />
                    <MetricCard label="已处理" value={formatNumber(auditSummary.completedCount)} />
                    <MetricCard label="已忽略" value={formatNumber(auditSummary.dismissedCount)} />
                    <MetricCard label="关联任务" value={formatNumber(auditSummary.linkedTaskCount)} />
                    <MetricCard label="关联清单" value={formatNumber(auditSummary.linkedChecklistCount)} />
                    <MetricCard label="已保存清单" value={formatNumber(auditChecklists.length)} />
                </div>
            </section>
            <ErrorNotice error={auditLoadError} title="督办审计数据刷新失败" />
            <SupervisorAuditFilterPanel
                auditCategoryFilter={auditCategoryFilter}
                setAuditCategoryFilter={setAuditCategoryFilter}
                auditCategoryOptions={auditCategoryOptions}
                auditActionFilter={auditActionFilter}
                setAuditActionFilter={setAuditActionFilter}
                auditActionOptions={auditActionOptions}
                auditStatusFilter={auditStatusFilter}
                setAuditStatusFilter={setAuditStatusFilter}
                SUPERVISOR_STATUS_FILTER_OPTIONS={SUPERVISOR_STATUS_FILTER_OPTIONS}
                auditChapterFilter={auditChapterFilter}
                setAuditChapterFilter={setAuditChapterFilter}
                auditChapterOptions={auditChapterOptions}
                auditViewMode={auditViewMode}
                setAuditViewMode={setAuditViewMode}
                auditGroupFocus={auditGroupFocus}
                setAuditGroupFocus={setAuditGroupFocus}
                auditGroupFocusOptions={AUDIT_GROUP_FOCUS_OPTIONS}
                auditFocusedStableKey={auditFocusedStableKey}
                setAuditFocusedStableKey={setAuditFocusedStableKey}
                handleDownloadAuditMarkdown={handleDownloadAuditMarkdown}
                handleDownloadAuditJson={handleDownloadAuditJson}
            />
            <SupervisorAuditTimelinePanel
                auditFocusState={auditFocusState}
                setAuditViewMode={setAuditViewMode}
                handleResetAuditEventFilters={handleResetAuditEventFilters}
                handleResetAuditGroupFilters={handleResetAuditGroupFilters}
                setAuditFocusedStableKey={setAuditFocusedStableKey}
                auditViewMode={auditViewMode}
                filteredGroupedAuditLogEntries={filteredGroupedAuditLogEntries}
                filteredAuditLogEntries={filteredAuditLogEntries}
                auditItemsByStableKey={auditItemsByStableKey}
                tasks={tasks}
                checklistLookup={checklistLookup}
                selectedAuditChecklist={selectedAuditChecklist}
                auditFocusedStableKey={auditFocusedStableKey}
                auditSubmitting={auditSubmitting}
                formatNumber={formatNumber}
                formatTimestampShort={formatTimestampShort}
                formatSupervisorAuditStatusSnapshot={formatSupervisorAuditStatusSnapshot}
                formatSupervisorDismissReason={formatSupervisorDismissReason}
                formatSupervisorTrackingStatus={formatSupervisorTrackingStatus}
                formatSupervisorAuditAction={formatSupervisorAuditAction}
                buildSupervisorAuditSchemaLabel={buildSupervisorAuditSchemaLabel}
                buildSupervisorAuditGroupAnchorId={buildSupervisorAuditGroupAnchorId}
                buildAuditTaskRuntimeSummary={buildAuditTaskRuntimeSummary}
                renderOperatorActionButtons={renderOperatorActionButtons}
                handleCopyAuditGroupLink={handleCopyAuditGroupLink}
                onOpenTask={onOpenTask}
                setSelectedAuditChecklistPath={setSelectedAuditChecklistPath}
                handleAuditGroupAction={handleAuditGroupAction}
                handleAuditGroupTracking={handleAuditGroupTracking}
                handleAuditGroupUndismiss={handleAuditGroupUndismiss}
                handleAuditGroupTrackingClear={handleAuditGroupTrackingClear}
                handleDownloadAuditChecklist={handleDownloadAuditChecklist}
                auditError={auditError}
            />
            <SupervisorAuditHealthPanel
                auditHealth={auditHealth}
                formatNumber={formatNumber}
                formatTimestampShort={formatTimestampShort}
                formatSupervisorAuditHealthIssueLabel={formatSupervisorAuditHealthIssueLabel}
                handleDownloadAuditHealthMarkdown={handleDownloadAuditHealthMarkdown}
                handleDownloadAuditHealthJson={handleDownloadAuditHealthJson}
            />
            <SupervisorAuditRepairPreviewPanel
                auditRepairPreview={auditRepairPreview}
                formatNumber={formatNumber}
                formatSupervisorAuditRepairActionLabel={formatSupervisorAuditRepairActionLabel}
                formatSupervisorAuditHealthIssueLabel={formatSupervisorAuditHealthIssueLabel}
                handleDownloadAuditRepairPreviewMarkdown={handleDownloadAuditRepairPreviewMarkdown}
                handleDownloadAuditRepairPreviewJson={handleDownloadAuditRepairPreviewJson}
            />
            <SupervisorAuditRepairArchivePanel
                auditRepairReportFilter={auditRepairReportFilter}
                setAuditRepairReportFilter={setAuditRepairReportFilter}
                auditRepairReportSortMode={auditRepairReportSortMode}
                setAuditRepairReportSortMode={setAuditRepairReportSortMode}
                AUDIT_REPAIR_REPORT_SORT_OPTIONS={AUDIT_REPAIR_REPORT_SORT_OPTIONS}
                auditRepairReportSummary={auditRepairReportSummary}
                auditRepairReports={auditRepairReports}
                sortedAuditRepairReports={sortedAuditRepairReports}
                selectedVisibleAuditRepairReport={selectedVisibleAuditRepairReport}
                setSelectedAuditRepairReportPath={setSelectedAuditRepairReportPath}
                handleDownloadAuditRepairReport={handleDownloadAuditRepairReport}
                formatTimestampShort={formatTimestampShort}
                formatNumber={formatNumber}
                formatAuditRepairReportSummary={formatAuditRepairReportSummary}
            />
            <SupervisorAuditChecklistArchivePanel
                auditChecklists={auditChecklists}
                selectedAuditChecklist={selectedAuditChecklist}
                setSelectedAuditChecklistPath={setSelectedAuditChecklistPath}
                handleDownloadAuditChecklist={handleDownloadAuditChecklist}
                formatTimestampShort={formatTimestampShort}
            />
        </div>
    )
}

