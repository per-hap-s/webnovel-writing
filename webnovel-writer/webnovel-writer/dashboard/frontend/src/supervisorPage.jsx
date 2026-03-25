import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'
import { ErrorNotice } from './appSections.jsx'
import { executeOperatorAction as executeRuntimeOperatorAction } from './operatorActionRuntime.js'
import { resolveSupervisorItemOperatorActions } from './operatorAction.js'
import { resolveSupervisorRecoverySemantics } from './recoverySemantics.js'
import { SupervisorActiveCard, SupervisorDismissedCard } from './supervisorCards.jsx'
import { MetricCard, downloadTextFile, formatNumber, formatTimestampShort, parseIsoTimestamp } from './dashboardPageCommon.jsx'
import { renderOperatorActionButtons } from './operatorActionButtons.jsx'

const SUPERVISOR_DISMISS_REASON_OPTIONS = [
    { value: 'defer', label: '暂缓处理' },
    { value: 'waiting_info', label: '等待更多信息' },
    { value: 'batch_later', label: '稍后统一处理' },
    { value: 'manual_override', label: '人工判断暂不优先' },
]

const SUPERVISOR_SORT_OPTIONS = [
    { value: 'priority', label: '按优先级' },
    { value: 'updated_desc', label: '按最近变更' },
    { value: 'chapter_asc', label: '按章节升序' },
]

const SUPERVISOR_TRACKING_STATUS_OPTIONS = [
    { value: 'in_progress', label: '处理中' },
    { value: 'completed', label: '已处理' },
]

const SUPERVISOR_STATUS_FILTER_OPTIONS = [
    { value: 'all', label: '全部状态' },
    { value: 'open', label: '待处理' },
    { value: 'in_progress', label: '处理中' },
    { value: 'completed', label: '已处理' },
    { value: 'dismissed', label: '已忽略' },
]

function formatSupervisorTrackingStatus(value) {
    const matched = SUPERVISOR_TRACKING_STATUS_OPTIONS.find((item) => item.value === value)
    return matched?.label || value || '未记录'
}

function formatSupervisorDismissReason(value) {
    const matched = SUPERVISOR_DISMISS_REASON_OPTIONS.find((item) => item.value === value)
    return matched?.label || value || '未记录'
}

function extractSupervisorChapter(item) {
    const match = String(item?.title || '').match(/第\s*(\d+)\s*章/)
    return match ? Number(match[1]) : 999999
}

function sortSupervisorItems(items, mode) {
    const list = [...(items || [])]
    list.sort((left, right) => {
        if (mode === 'updated_desc') {
            return parseIsoTimestamp(right?.sourceUpdatedAt) - parseIsoTimestamp(left?.sourceUpdatedAt)
        }
        if (mode === 'chapter_asc') {
            const chapterDelta = extractSupervisorChapter(left) - extractSupervisorChapter(right)
            if (chapterDelta !== 0) return chapterDelta
            return Number(left?.priority || 999) - Number(right?.priority || 999)
        }
        const priorityDelta = Number(left?.priority || 999) - Number(right?.priority || 999)
        if (priorityDelta !== 0) return priorityDelta
        return parseIsoTimestamp(right?.sourceUpdatedAt) - parseIsoTimestamp(left?.sourceUpdatedAt)
    })
    return list
}

function buildSupervisorChecklistMarkdown({ projectInfo, items, categoryFilter, sortMode }) {
    const currentChapter = Number(projectInfo?.progress?.current_chapter || 0)
    const totalWords = Number(projectInfo?.progress?.total_words || 0)
    const activeItems = (items || []).filter((item) => !item?.dismissed)
    const dismissedItems = (items || []).filter((item) => item?.dismissed)
    const lines = [
        '# 督办处理清单',
        '',
        `- 当前章节：第 ${currentChapter} 章`,
        `- 项目总字数：${formatNumber(totalWords)}`,
        `- 分类筛选：${categoryFilter === 'all' ? '全部类型' : categoryFilter}`,
        `- 排序方式：${SUPERVISOR_SORT_OPTIONS.find((item) => item.value === sortMode)?.label || sortMode}`,
        `- 导出时间：${formatTimestampShort(new Date().toISOString())}`,
        '',
        '## 待处理建议',
    ]

    if (!activeItems.length) {
        lines.push('- 当前没有待处理建议。')
    } else {
        activeItems.forEach((item, index) => {
            lines.push(`${index + 1}. [${item.categoryLabel || item.category || '-'}] ${item.title}`)
            lines.push(`   - 摘要：${item.summary || '-'}`)
            lines.push(`   - 说明：${item.detail || '-'}`)
            lines.push(`   - 推荐理由：${item.rationale || '-'}`)
            lines.push(`   - 主动作：${item.actionLabel || '-'}`)
            if (item.secondaryLabel) lines.push(`   - 次动作：${item.secondaryLabel}`)
        })
    }

    lines.push('', '## 已忽略建议')
    if (!dismissedItems.length) {
        lines.push('- 当前没有已忽略建议。')
    } else {
        dismissedItems.forEach((item, index) => {
            lines.push(`${index + 1}. [${item.categoryLabel || item.category || '-'}] ${item.title}`)
            lines.push(`   - 忽略时间：${formatTimestampShort(item.dismissedAt)}`)
            lines.push(`   - 忽略原因：${formatSupervisorDismissReason(item.dismissalReason)}`)
            lines.push(`   - 手动备注：${item.dismissalNote || '-'}`)
            lines.push(`   - 恢复后动作：${item.actionLabel || '-'}`)
        })
    }

    return lines.join('\n')
}

export function SupervisorPage({ projectInfo, tasks, onTaskCreated, onOpenTask, onTasksMutated }) {
    const [supervisorError, setSupervisorError] = useState(null)
    const [supervisorLoadError, setSupervisorLoadError] = useState(null)
    const [supervisorSubmitting, setSupervisorSubmitting] = useState(false)
    const [rawSupervisorItems, setRawSupervisorItems] = useState([])
    const [dismissDrafts, setDismissDrafts] = useState({})
    const [trackingDrafts, setTrackingDrafts] = useState({})
    const [selectedSupervisorKeys, setSelectedSupervisorKeys] = useState([])
    const [categoryFilter, setCategoryFilter] = useState('all')
    const [statusFilter, setStatusFilter] = useState('all')
    const [sortMode, setSortMode] = useState('priority')
    const [batchDismissReason, setBatchDismissReason] = useState('')
    const [batchDismissNote, setBatchDismissNote] = useState('')
    const [savedChecklistMeta, setSavedChecklistMeta] = useState(null)
    const [checklistTitle, setChecklistTitle] = useState('')
    const [checklistNote, setChecklistNote] = useState('')
    const [recentChecklists, setRecentChecklists] = useState([])
    const [selectedChecklistPath, setSelectedChecklistPath] = useState('')
    const loadSeqRef = useRef(0)

    const supervisorCategoryOptions = useMemo(() => {
        const seen = new Map()
        rawSupervisorItems.forEach((item) => {
            const key = item?.category || 'unknown'
            if (!seen.has(key)) {
                seen.set(key, item?.categoryLabel || key)
            }
        })
        return [{ value: 'all', label: '全部类型' }, ...[...seen.entries()].map(([value, label]) => ({ value, label }))]
    }, [rawSupervisorItems])

    const filteredSupervisorItems = useMemo(
        () => rawSupervisorItems.filter((item) => {
            if (categoryFilter !== 'all' && item?.category !== categoryFilter) return false
            if (statusFilter === 'all') return true
            if (statusFilter === 'dismissed') return Boolean(item?.dismissed)
            if (item?.dismissed) return false
            if (statusFilter === 'open') return !item?.trackingStatus
            return item?.trackingStatus === statusFilter
        }),
        [rawSupervisorItems, categoryFilter, statusFilter],
    )
    const sortedSupervisorItems = useMemo(() => sortSupervisorItems(filteredSupervisorItems, sortMode), [filteredSupervisorItems, sortMode])
    const supervisorItems = useMemo(() => sortedSupervisorItems.filter((item) => !item?.dismissed), [sortedSupervisorItems])
    const dismissedSupervisorItems = useMemo(() => sortedSupervisorItems.filter((item) => item?.dismissed), [sortedSupervisorItems])
    const supervisorStatusSummary = useMemo(() => {
        const summary = { open: 0, in_progress: 0, completed: 0, dismissed: 0 }
        rawSupervisorItems.forEach((item) => {
            if (item?.dismissed) summary.dismissed += 1
            else if (item?.trackingStatus === 'in_progress') summary.in_progress += 1
            else if (item?.trackingStatus === 'completed') summary.completed += 1
            else summary.open += 1
        })
        return summary
    }, [rawSupervisorItems])
    const checklistItems = useMemo(() => {
        const selectedSet = new Set(selectedSupervisorKeys)
        if (!selectedSet.size) return sortedSupervisorItems
        return sortedSupervisorItems.filter((item) => selectedSet.has(item.stableKey))
    }, [sortedSupervisorItems, selectedSupervisorKeys])
    const checklistMarkdown = useMemo(
        () => buildSupervisorChecklistMarkdown({ projectInfo, items: checklistItems, categoryFilter, sortMode }),
        [projectInfo, checklistItems, categoryFilter, sortMode],
    )

    const selectedChecklist = useMemo(
        () => recentChecklists.find((item) => item.relativePath === selectedChecklistPath) || recentChecklists[0] || null,
        [recentChecklists, selectedChecklistPath],
    )

    async function refreshSupervisorChecklists() {
        try {
            const items = await fetchJSON('/api/supervisor/checklists', { limit: 8 })
            const nextItems = Array.isArray(items) ? items : []
            setRecentChecklists(nextItems)
            setSelectedChecklistPath((current) => {
                if (current && nextItems.some((item) => item.relativePath === current)) return current
                return nextItems[0]?.relativePath || ''
            })
            setSupervisorLoadError(null)
        } catch (err) {
            setSupervisorLoadError(normalizeError(err))
        }
    }

    useEffect(() => {
        const loadSeq = ++loadSeqRef.current
        let cancelled = false

        Promise.allSettled([
            fetchJSON('/api/supervisor/recommendations?include_dismissed=true'),
            fetchJSON('/api/supervisor/checklists', { limit: 8 }),
        ])
            .then(([itemsResult, checklistsResult]) => {
                if (cancelled || loadSeq !== loadSeqRef.current) return

                const errors = []
                if (itemsResult.status === 'fulfilled') {
                    setRawSupervisorItems(Array.isArray(itemsResult.value) ? itemsResult.value : [])
                } else {
                    errors.push(normalizeError(itemsResult.reason))
                }

                if (checklistsResult.status === 'fulfilled') {
                    const nextItems = Array.isArray(checklistsResult.value) ? checklistsResult.value : []
                    setRecentChecklists(nextItems)
                    setSelectedChecklistPath((current) => {
                        if (current && nextItems.some((item) => item.relativePath === current)) return current
                        return nextItems[0]?.relativePath || ''
                    })
                } else {
                    errors.push(normalizeError(checklistsResult.reason))
                }

                setSupervisorLoadError(errors[0] || null)
            })
            .catch((err) => {
                if (cancelled || loadSeq !== loadSeqRef.current) return
                setSupervisorLoadError(normalizeError(err))
            })
        return () => {
            cancelled = true
            loadSeqRef.current += 1
        }
    }, [tasks, projectInfo?.progress?.current_chapter])

    useEffect(() => {
        const visibleKeys = new Set(rawSupervisorItems.map((item) => item.stableKey))
        setSelectedSupervisorKeys((current) => current.filter((key) => visibleKeys.has(key)))
    }, [rawSupervisorItems])

    function resolveDismissDraft(item) {
        return dismissDrafts[item?.stableKey || ''] || { reason: '', note: '' }
    }

    function resolveTrackingDraft(item) {
        return trackingDrafts[item?.stableKey || ''] || {
            status: item?.trackingStatus || '',
            note: item?.trackingNote || '',
            linkedTaskId: item?.linkedTaskId || '',
            linkedChecklistPath: item?.linkedChecklistPath || '',
        }
    }

    function updateDismissDraft(stableKey, patch) {
        setDismissDrafts((current) => ({
            ...current,
            [stableKey]: { ...(current[stableKey] || { reason: '', note: '' }), ...patch },
        }))
    }

    function updateTrackingDraft(stableKey, patch) {
        setTrackingDrafts((current) => ({
            ...current,
            [stableKey]: { ...(current[stableKey] || { status: '', note: '', linkedTaskId: '', linkedChecklistPath: '' }), ...patch },
        }))
    }

    function toggleSupervisorSelection(stableKey) {
        setSelectedSupervisorKeys((current) => (
            current.includes(stableKey)
                ? current.filter((key) => key !== stableKey)
                : [...current, stableKey]
        ))
    }

    function setSelectionForItems(items, selected) {
        const keys = items.map((item) => item.stableKey)
        setSelectedSupervisorKeys((current) => {
            const currentSet = new Set(current)
            keys.forEach((key) => {
                if (selected) currentSet.add(key)
                else currentSet.delete(key)
            })
            return [...currentSet]
        })
    }

    async function handleSupervisorAction(item, overrideAction = null) {
        if (!item || supervisorSubmitting) return
        const action = overrideAction || item.action
        setSupervisorSubmitting(true)
        setSupervisorError(null)
        try {
            await executeRuntimeOperatorAction({
                action,
                postJSON,
                onOpenTask,
                onTaskCreated: (response, nextAction) => onTaskCreated(response, nextAction),
                onTasksMutated: () => onTasksMutated(),
            })
        } catch (err) {
            setSupervisorError(normalizeError(err))
        } finally {
            setSupervisorSubmitting(false)
        }
    }

    async function handleSupervisorDismiss(item) {
        if (!item?.stableKey || supervisorSubmitting) return
        const draft = resolveDismissDraft(item)
        if (!draft.reason) {
            setSupervisorError({ message: '请先选择忽略原因。' })
            return
        }
        setSupervisorSubmitting(true)
        setSupervisorError(null)
        try {
            await postJSON('/api/supervisor/dismiss', {
                stable_key: item.stableKey,
                fingerprint: item.fingerprint || item.stableKey,
                reason: draft.reason,
                note: draft.note || '',
            })
            setRawSupervisorItems((current) => current.map((candidate) => (
                candidate.stableKey === item.stableKey
                    ? { ...candidate, dismissed: true, dismissedAt: new Date().toISOString(), dismissalReason: draft.reason, dismissalNote: draft.note || '' }
                    : candidate
            )))
        } catch (err) {
            setSupervisorError(normalizeError(err))
        } finally {
            setSupervisorSubmitting(false)
        }
    }

    async function handleSupervisorUndismiss(item) {
        if (!item?.stableKey || supervisorSubmitting) return
        setSupervisorSubmitting(true)
        setSupervisorError(null)
        try {
            await postJSON('/api/supervisor/undismiss', { stable_key: item.stableKey, fingerprint: item.fingerprint || item.stableKey })
            setRawSupervisorItems((current) => current.map((candidate) => (
                candidate.stableKey === item.stableKey
                    ? { ...candidate, dismissed: false, dismissedAt: null, dismissalReason: '', dismissalNote: '' }
                    : candidate
            )))
        } catch (err) {
            setSupervisorError(normalizeError(err))
        } finally {
            setSupervisorSubmitting(false)
        }
    }

    async function handleBatchSupervisorDismiss() {
        if (supervisorSubmitting) return
        if (!batchDismissReason) {
            setSupervisorError({ message: '请先选择批量忽略原因。' })
            return
        }
        const selectedItems = supervisorItems.filter((item) => selectedSupervisorKeys.includes(item.stableKey))
        if (!selectedItems.length) return
        setSupervisorSubmitting(true)
        setSupervisorError(null)
        try {
            await postJSON('/api/supervisor/dismiss-batch', {
                items: selectedItems.map((item) => ({ stable_key: item.stableKey, fingerprint: item.fingerprint || item.stableKey })),
                reason: batchDismissReason,
                note: batchDismissNote,
            })
            const dismissedAt = new Date().toISOString()
            const selectedSet = new Set(selectedItems.map((item) => item.stableKey))
            setRawSupervisorItems((current) => current.map((candidate) => (
                selectedSet.has(candidate.stableKey)
                    ? { ...candidate, dismissed: true, dismissedAt, dismissalReason: batchDismissReason, dismissalNote: batchDismissNote }
                    : candidate
            )))
            setSelectedSupervisorKeys((current) => current.filter((key) => !selectedSet.has(key)))
        } catch (err) {
            setSupervisorError(normalizeError(err))
        } finally {
            setSupervisorSubmitting(false)
        }
    }

    async function handleBatchSupervisorUndismiss() {
        if (supervisorSubmitting) return
        const selectedItems = dismissedSupervisorItems.filter((item) => selectedSupervisorKeys.includes(item.stableKey))
        if (!selectedItems.length) return
        setSupervisorSubmitting(true)
        setSupervisorError(null)
        try {
            await postJSON('/api/supervisor/undismiss-batch', { stable_keys: selectedItems.map((item) => item.stableKey) })
            const selectedSet = new Set(selectedItems.map((item) => item.stableKey))
            setRawSupervisorItems((current) => current.map((candidate) => (
                selectedSet.has(candidate.stableKey)
                    ? { ...candidate, dismissed: false, dismissedAt: null, dismissalReason: '', dismissalNote: '' }
                    : candidate
            )))
            setSelectedSupervisorKeys((current) => current.filter((key) => !selectedSet.has(key)))
        } catch (err) {
            setSupervisorError(normalizeError(err))
        } finally {
            setSupervisorSubmitting(false)
        }
    }

    async function handleSupervisorTrackingSave(item) {
        if (!item?.stableKey || supervisorSubmitting) return
        const draft = resolveTrackingDraft(item)
        if (!draft.status) {
            setSupervisorError({ message: '请先选择处理状态。' })
            return
        }
        setSupervisorSubmitting(true)
        setSupervisorError(null)
        try {
            await postJSON('/api/supervisor/tracking', {
                stable_key: item.stableKey,
                fingerprint: item.fingerprint || item.stableKey,
                status: draft.status,
                note: draft.note || '',
                linked_task_id: draft.linkedTaskId || '',
                linked_checklist_path: draft.linkedChecklistPath || '',
            })
            setRawSupervisorItems((current) => current.map((candidate) => (
                candidate.stableKey === item.stableKey
                    ? {
                        ...candidate,
                        trackingStatus: draft.status,
                        trackingLabel: formatSupervisorTrackingStatus(draft.status),
                        trackingNote: draft.note || '',
                        linkedTaskId: draft.linkedTaskId || '',
                        linkedChecklistPath: draft.linkedChecklistPath || '',
                        trackingUpdatedAt: new Date().toISOString(),
                    }
                    : candidate
            )))
        } catch (err) {
            setSupervisorError(normalizeError(err))
        } finally {
            setSupervisorSubmitting(false)
        }
    }

    async function handleSupervisorTrackingClear(item) {
        if (!item?.stableKey || supervisorSubmitting) return
        setSupervisorSubmitting(true)
        setSupervisorError(null)
        try {
            await postJSON('/api/supervisor/tracking/clear', { stable_key: item.stableKey, fingerprint: item.fingerprint || item.stableKey })
            setRawSupervisorItems((current) => current.map((candidate) => (
                candidate.stableKey === item.stableKey
                    ? { ...candidate, trackingStatus: '', trackingLabel: '', trackingNote: '', linkedTaskId: '', linkedChecklistPath: '', trackingUpdatedAt: null }
                    : candidate
            )))
            setTrackingDrafts((current) => ({
                ...current,
                [item.stableKey]: { status: '', note: '', linkedTaskId: '', linkedChecklistPath: '' },
            }))
        } catch (err) {
            setSupervisorError(normalizeError(err))
        } finally {
            setSupervisorSubmitting(false)
        }
    }

    async function handleCopyChecklist() {
        try {
            await navigator.clipboard.writeText(checklistMarkdown)
        } catch (err) {
            setSupervisorError(normalizeError(err))
        }
    }

    function handleDownloadChecklist() {
        try {
            setSupervisorError(null)
            downloadTextFile(`supervisor-checklist-ch${String(projectInfo?.progress?.current_chapter || 0).padStart(4, '0')}.md`, checklistMarkdown, 'text/markdown;charset=utf-8')
        } catch (err) {
            setSupervisorError(normalizeError(err))
        }
    }

    function handleDownloadSavedChecklist(item) {
        if (!item?.content) return
        try {
            setSupervisorError(null)
            downloadTextFile(item.filename || 'supervisor-checklist.md', item.content, 'text/markdown;charset=utf-8')
        } catch (err) {
            setSupervisorError(normalizeError(err))
        }
    }

    async function handleSaveChecklistToProject() {
        if (supervisorSubmitting) return
        setSupervisorSubmitting(true)
        setSupervisorError(null)
        setSavedChecklistMeta(null)
        try {
            const response = await postJSON('/api/supervisor/checklists', {
                content: checklistMarkdown,
                chapter: Number(projectInfo?.progress?.current_chapter || 0),
                selected_keys: selectedSupervisorKeys,
                category_filter: categoryFilter,
                sort_mode: sortMode,
                title: checklistTitle,
                note: checklistNote,
            })
            setSavedChecklistMeta(response)
            await refreshSupervisorChecklists()
        } catch (err) {
            setSupervisorError(normalizeError(err))
        } finally {
            setSupervisorSubmitting(false)
        }
    }

    return (
        <div className="page-grid">
            <section className="panel hero-panel">
                <div className="panel-title">督办台</div>
                <div className="metric-grid">
                    <MetricCard label="待处理建议" value={formatNumber(supervisorStatusSummary.open)} />
                    <MetricCard label="处理中" value={formatNumber(supervisorStatusSummary.in_progress)} />
                    <MetricCard label="已处理" value={formatNumber(supervisorStatusSummary.completed)} />
                    <MetricCard label="已忽略建议" value={formatNumber(supervisorStatusSummary.dismissed)} />
                    <MetricCard label="当前章节" value={`第 ${projectInfo?.progress?.current_chapter || 0} 章`} />
                    <MetricCard label="项目总字数" value={formatNumber(projectInfo?.progress?.total_words || 0)} />
                </div>
            </section>
            <ErrorNotice error={supervisorLoadError} title="督办台数据刷新失败" />
            <section className="panel full-span">
                <div className="panel-title">筛选与排序</div>
                <div className="detail-grid">
                    <label className="field">
                        <span>建议类型</span>
                        <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
                            {supervisorCategoryOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </select>
                    </label>
                    <label className="field">
                        <span>处理状态</span>
                        <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                            {SUPERVISOR_STATUS_FILTER_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </select>
                    </label>
                    <label className="field">
                        <span>排序方式</span>
                        <select value={sortMode} onChange={(event) => setSortMode(event.target.value)}>
                            {SUPERVISOR_SORT_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </select>
                    </label>
                </div>
            </section>
            <section className="panel full-span">
                <div className="panel-title">批量操作</div>
                <div className="detail-grid">
                    <label className="field">
                        <span>批量忽略原因</span>
                        <select value={batchDismissReason} onChange={(event) => setBatchDismissReason(event.target.value)}>
                            <option value="">请选择原因</option>
                            {SUPERVISOR_DISMISS_REASON_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </select>
                    </label>
                    <label className="field">
                        <span>批量备注</span>
                        <textarea value={batchDismissNote} onChange={(event) => setBatchDismissNote(event.target.value)} placeholder="可选，用于记录本轮批量忽略的背景" />
                    </label>
                </div>
                <div className="button-row">
                    <button className="secondary-button" onClick={() => setSelectionForItems(supervisorItems, true)} disabled={supervisorSubmitting || !supervisorItems.length}>全选待处理</button>
                    <button className="secondary-button" onClick={() => setSelectionForItems(dismissedSupervisorItems, true)} disabled={supervisorSubmitting || !dismissedSupervisorItems.length}>全选已忽略</button>
                    <button className="secondary-button" onClick={() => setSelectedSupervisorKeys([])} disabled={supervisorSubmitting || !selectedSupervisorKeys.length}>清空选中</button>
                    <button className="secondary-button" onClick={() => handleBatchSupervisorDismiss()} disabled={supervisorSubmitting || !batchDismissReason || !supervisorItems.filter((item) => selectedSupervisorKeys.includes(item.stableKey)).length}>{supervisorSubmitting ? '处理中...' : '批量忽略'}</button>
                    <button className="secondary-button" onClick={() => handleBatchSupervisorUndismiss()} disabled={supervisorSubmitting || !dismissedSupervisorItems.filter((item) => selectedSupervisorKeys.includes(item.stableKey)).length}>{supervisorSubmitting ? '处理中...' : '批量恢复'}</button>
                </div>
            </section>
            <section className="panel full-span">
                <div className="panel-title">本轮处理清单</div>
                <div className="empty-state">{selectedSupervisorKeys.length > 0 ? '当前导出的是已选中的建议。若没有选中，则导出当前筛选结果。' : '当前未选中具体建议，将导出当前筛选后的全部建议。'}</div>
                <div className="detail-grid">
                    <label className="field">
                        <span>清单标题</span>
                        <input value={checklistTitle} onChange={(event) => setChecklistTitle(event.target.value)} placeholder="可选，比如：第 6 章开写前督办检查" />
                    </label>
                    <label className="field">
                        <span>清单备注</span>
                        <textarea value={checklistNote} onChange={(event) => setChecklistNote(event.target.value)} placeholder="可选，记录这轮清单的用途或背景" />
                    </label>
                </div>
                <div className="button-row">
                    <button className="secondary-button" onClick={() => handleCopyChecklist()}>复制 Markdown</button>
                    <button className="secondary-button" onClick={() => handleDownloadChecklist()}>下载清单</button>
                    <button className="secondary-button" onClick={() => handleSaveChecklistToProject()} disabled={supervisorSubmitting || !checklistMarkdown.trim()}>{supervisorSubmitting ? '保存中...' : '保存到项目'}</button>
                </div>
                {savedChecklistMeta?.relativePath ? <div className="tiny">{`${savedChecklistMeta?.title ? `${savedChecklistMeta.title} / ` : ''}已保存到：${savedChecklistMeta.relativePath}`}</div> : null}
                <pre>{checklistMarkdown}</pre>
            </section>
            <section className="panel full-span">
                <div className="panel-title">最近已保存清单</div>
                <div className="empty-state">这里展示最近几轮已落盘的督办清单，便于回溯和复用。</div>
                {recentChecklists.length === 0 ? (
                    <div className="empty-state">暂时还没有已保存的清单。</div>
                ) : (
                    <>
                        <div className="supervisor-grid">
                            {recentChecklists.map((item) => (
                                <div key={item.relativePath} className={`supervisor-card ${selectedChecklist?.relativePath === item.relativePath ? 'success' : ''}`}>
                                    <div className="supervisor-card-header">
                                        <div className="supervisor-title"><span>{item.title || `第 ${item.chapter || 0} 章清单`}</span></div>
                                        <span className="runtime-badge">{formatTimestampShort(item.savedAt)}</span>
                                    </div>
                                    <div className="tiny">{`路径：${item.relativePath}`}</div>
                                    <div className="tiny">{`筛选：${item.categoryFilter || 'all'} / 排序：${item.sortMode || 'priority'}`}</div>
                                    <div className="tiny">{`选中项：${formatNumber(item.selectedCount || 0)}`}</div>
                                    {item.note ? <div className="tiny">{`备注：${item.note}`}</div> : null}
                                    <div className="supervisor-meta">{item.summary || '已保存的督办清单'}</div>
                                    <div className="button-row">
                                        <button className="secondary-button" onClick={() => setSelectedChecklistPath(item.relativePath)}>{selectedChecklist?.relativePath === item.relativePath ? '已在查看' : '查看内容'}</button>
                                        <button className="secondary-button" onClick={() => handleDownloadSavedChecklist(item)}>下载副本</button>
                                    </div>
                                </div>
                            ))}
                        </div>
                        {selectedChecklist?.title ? <div className="panel-title">{selectedChecklist.title}</div> : null}
                        {selectedChecklist?.note ? <div className="tiny">{`备注：${selectedChecklist.note}`}</div> : null}
                        {selectedChecklist?.content ? <pre>{selectedChecklist.content}</pre> : null}
                    </>
                )}
            </section>
            <section className="panel full-span">
                <div className="panel-title">督办建议</div>
                <div className="empty-state">这里只放当前需要优先处理的建议。忽略时需要填写原因，便于后续追溯。</div>
                <div className="supervisor-grid">
                    {supervisorItems.map((item) => {
                        const draft = resolveDismissDraft(item)
                        const trackingDraft = resolveTrackingDraft(item)
                        const operatorActions = resolveSupervisorItemOperatorActions(item)
                        const recoverySemantics = resolveSupervisorRecoverySemantics(item)
                        return (
                            <SupervisorActiveCard
                                key={item.stableKey}
                                item={item}
                                draft={draft}
                                trackingDraft={trackingDraft}
                                operatorActions={operatorActions}
                                recoverySemantics={recoverySemantics}
                                recentChecklists={recentChecklists}
                                supervisorSubmitting={supervisorSubmitting}
                                selectedSupervisorKeys={selectedSupervisorKeys}
                                toggleSupervisorSelection={toggleSupervisorSelection}
                                updateTrackingDraft={updateTrackingDraft}
                                updateDismissDraft={updateDismissDraft}
                                handleSupervisorTrackingSave={handleSupervisorTrackingSave}
                                handleSupervisorTrackingClear={handleSupervisorTrackingClear}
                                handleSupervisorAction={handleSupervisorAction}
                                handleSupervisorDismiss={handleSupervisorDismiss}
                                renderOperatorActionButtons={renderOperatorActionButtons}
                                formatSupervisorTrackingStatus={formatSupervisorTrackingStatus}
                                formatTimestampShort={formatTimestampShort}
                                SUPERVISOR_TRACKING_STATUS_OPTIONS={SUPERVISOR_TRACKING_STATUS_OPTIONS}
                                SUPERVISOR_DISMISS_REASON_OPTIONS={SUPERVISOR_DISMISS_REASON_OPTIONS}
                            />
                        )
                    })}
                    {!supervisorItems.length ? <div className="empty-state">当前没有需要优先处理的建议。</div> : null}
                </div>
            </section>
            <section className="panel full-span">
                <div className="panel-title">已忽略建议</div>
                <div className="empty-state">这里显示已忽略的建议和忽略理由，可以恢复到待处理列表。</div>
                <div className="supervisor-grid">
                    {dismissedSupervisorItems.map((item) => {
                        const operatorActions = resolveSupervisorItemOperatorActions(item)
                        const recoverySemantics = resolveSupervisorRecoverySemantics(item)
                        return (
                            <SupervisorDismissedCard
                                key={`${item.stableKey}:dismissed`}
                                item={item}
                                operatorActions={operatorActions}
                                recoverySemantics={recoverySemantics}
                                selectedSupervisorKeys={selectedSupervisorKeys}
                                toggleSupervisorSelection={toggleSupervisorSelection}
                                handleSupervisorUndismiss={handleSupervisorUndismiss}
                                handleSupervisorTrackingClear={handleSupervisorTrackingClear}
                                handleSupervisorAction={handleSupervisorAction}
                                renderOperatorActionButtons={renderOperatorActionButtons}
                                supervisorSubmitting={supervisorSubmitting}
                                formatSupervisorTrackingStatus={formatSupervisorTrackingStatus}
                                formatSupervisorDismissReason={formatSupervisorDismissReason}
                                formatTimestampShort={formatTimestampShort}
                            />
                        )
                    })}
                    {!dismissedSupervisorItems.length ? <div className="empty-state">暂时没有已忽略的建议。</div> : null}
                </div>
                {supervisorError ? <ErrorNotice error={supervisorError} /> : null}
            </section>
        </div>
    )
}

