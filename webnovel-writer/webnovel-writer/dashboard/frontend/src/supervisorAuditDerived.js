import {
    formatNumber,
    formatTimestampShort,
    parseIsoTimestamp,
    resolveCurrentStepLabel,
    resolveTaskStatusLabel,
    resolveTaskTargetLabel,
    translateTaskType,
} from './dashboardPageCommon.jsx'
import { resolveVisibleAuditRepairReportPath } from './supervisorAuditState.js'

export const SUPERVISOR_TRACKING_STATUS_OPTIONS = [
    { value: 'in_progress', label: '处理中' },
    { value: 'completed', label: '已处理' },
]

export const SUPERVISOR_STATUS_FILTER_OPTIONS = [
    { value: 'all', label: '全部状态' },
    { value: 'open', label: '待处理' },
    { value: 'in_progress', label: '处理中' },
    { value: 'completed', label: '已处理' },
    { value: 'dismissed', label: '已忽略' },
]

export const AUDIT_GROUP_FOCUS_OPTIONS = [
    { value: 'all', label: '全部分组' },
    { value: 'actionable', label: '可直接执行' },
    { value: 'open', label: '待处理' },
    { value: 'in_progress', label: '处理中' },
    { value: 'completed', label: '已处理' },
    { value: 'dismissed', label: '已从建议列表移除' },
    { value: 'archived', label: '仅历史归档' },
]

const SUPERVISOR_DISMISS_REASON_OPTIONS = [
    { value: 'defer', label: '暂缓处理' },
    { value: 'waiting_info', label: '等待更多信息' },
    { value: 'batch_later', label: '稍后统一处理' },
    { value: 'manual_override', label: '人工判断暂不优先' },
]

function formatSupervisorAuditSchemaState(value) {
    const labels = {
        supported: '可兼容',
        future: '未来版本',
        legacy: '旧版本',
        unknown: '未知',
    }
    return labels[value] || value || '未知'
}

export function formatSupervisorDismissReason(value) {
    const matched = SUPERVISOR_DISMISS_REASON_OPTIONS.find((item) => item.value === value)
    return matched?.label || value || '未记录'
}

export function formatSupervisorTrackingStatus(value) {
    const matched = SUPERVISOR_TRACKING_STATUS_OPTIONS.find((item) => item.value === value)
    return matched?.label || value || '未记录'
}

export function formatSupervisorAuditAction(action) {
    const labels = {
        created: '建议新建',
        dismissed: '已忽略',
        undismissed: '已恢复',
        tracking_updated: '跟踪状态更新',
        tracking_cleared: '跟踪状态已清除',
        checklist_saved: '清单已保存',
        linked_task_updated: '关联任务更新',
    }
    return labels[action] || action || '未记录'
}

export function formatSupervisorAuditStatusSnapshot(value) {
    const labels = {
        open: '待处理',
        in_progress: '处理中',
        completed: '已处理',
        dismissed: '已从建议列表移除',
        archived: '仅历史归档',
    }
    return labels[value] || formatSupervisorTrackingStatus(value)
}

export function buildSupervisorAuditSchemaLabel(item) {
    const schemaVersion = Number(item?.schemaVersion || item?.schema_version || 0)
    const schemaState = String(item?.schemaState || item?.schema_state || 'supported').trim() || 'supported'
    return schemaVersion > 0 ? `Schema v${schemaVersion} / ${formatSupervisorAuditSchemaState(schemaState)}` : formatSupervisorAuditSchemaState(schemaState)
}

export function formatSupervisorAuditHealthIssueLabel(code) {
    const labels = {
        invalid_json: '非 JSON 行',
        invalid_timestamp: '时间戳非法',
        missing_action: '缺少 action',
        missing_stable_key: '缺少 stable key',
        future_schema: '未来 schema',
    }
    return labels[code] || code || '未记录'
}

export function formatSupervisorAuditRepairActionLabel(action) {
    const labels = {
        drop_line: '删除坏行',
        rewrite_normalized_event: '重写为规范事件',
        manual_review: '仅人工复核',
    }
    return labels[action] || action || '未记录'
}

export function buildAuditTaskRuntimeSummary(task) {
    if (!task) return []
    const lines = [`：${translateTaskType(task.task_type)} / ${resolveTaskStatusLabel(task)}`]
    const targetLabel = resolveTaskTargetLabel(task)
    if (targetLabel && targetLabel !== '-') {
        lines.push(`目标：${targetLabel}`)
    }
    const stepLabel = resolveCurrentStepLabel(task)
    if (stepLabel && stepLabel !== '-') {
        lines.push(`当前步骤：${stepLabel}`)
    }
    return lines
}

export function buildSupervisorAuditGroupAnchorId(stableKey) {
    return `audit-group:${String(stableKey || 'unknown').replace(/[^a-zA-Z0-9:_-]+/g, '-')}`
}

export function extractSupervisorChapter(item) {
    const rawChapter = item?.chapter
    if (rawChapter !== null && rawChapter !== undefined && String(rawChapter).trim() !== '') {
        const normalizedChapter = Number(rawChapter)
        if (Number.isFinite(normalizedChapter)) return normalizedChapter
    }
    const match = String(item?.title || '').match(/第\s*(\d+)\s*章/)
    return match ? Number(match[1]) : 999999
}

function buildAuditRepairReportImpactScore(item) {
    return Number(item?.droppedCount || 0) + Number(item?.rewrittenCount || 0) + Number(item?.manualReviewCount || 0)
}

export function formatAuditRepairReportSummary(item) {
    const appliedCount = Number(item?.appliedCount || 0)
    const manualReviewCount = Number(item?.manualReviewCount || 0)
    const keptCount = Number(item?.keptCount || 0)
    return `自动处理 ${formatNumber(appliedCount)} 项 / 人工复核 ${formatNumber(manualReviewCount)} 项 / 保留 ${formatNumber(keptCount)} 项`
}

function isAuditGroupActionable(item) {
    return Boolean(item && !item.dismissed && item.trackingStatus !== 'completed')
}

export function resolveCurrentAuditGroupState(item) {
    if (!item) return 'archived'
    if (item.dismissed) return 'dismissed'
    if (item.trackingStatus === 'completed') return 'completed'
    if (item.trackingStatus === 'in_progress') return 'in_progress'
    return 'open'
}

function compactSupervisorAuditGroupEntries(entries) {
    const compactedEntries = []
    ;(entries || []).forEach((entry) => {
        const previous = compactedEntries[compactedEntries.length - 1]
        const sameTrackingUpdate = previous
            && previous.action === entry?.action
            && previous.status_snapshot === entry?.status_snapshot
            && previous.dismissal_reason === entry?.dismissal_reason
            && previous.dismissal_note === entry?.dismissal_note
            && previous.tracking_note === entry?.tracking_note
        if (sameTrackingUpdate) {
            previous.mergedCount = Number(previous.mergedCount || 1) + 1
            previous.timestamp = entry?.timestamp || previous.timestamp
            return
        }
        compactedEntries.push({ ...entry, mergedCount: Number(entry?.mergedCount || 1) })
    })
    return compactedEntries
}

function rankSupervisorAuditGroup(group) {
    const stateRank = { open: 0, in_progress: 1, completed: 2, dismissed: 3, archived: 4 }
    return [
        Number(stateRank[group?.currentState] ?? 9),
        Number(group?.priority || 999),
        -parseIsoTimestamp(group?.latestTimestamp),
    ]
}

export function buildSupervisorAuditGroups(entries, auditItems) {
    const auditItemsByStableKey = new Map((auditItems || []).map((item) => [item?.stableKey, item]))
    const groups = new Map()
    ;(entries || []).forEach((entry, index) => {
        const stableKey = String(entry?.stableKey || entry?.stable_key || `event:${index}`).trim()
        if (!groups.has(stableKey)) {
            groups.set(stableKey, [])
        }
        groups.get(stableKey).push(entry)
    })
    return [...groups.entries()].map(([stableKey, groupEntries], index) => {
        const orderedEntries = [...groupEntries].sort((left, right) => parseIsoTimestamp(left?.timestamp) - parseIsoTimestamp(right?.timestamp))
        const compactedEntries = compactSupervisorAuditGroupEntries(orderedEntries)
        const latestEntry = orderedEntries[orderedEntries.length - 1] || {}
        const currentAuditItem = auditItemsByStableKey.get(stableKey) || null
        const schemaWarning = latestEntry.schemaWarning || latestEntry.schema_warning || ''
        const schemaState = latestEntry.schemaState || latestEntry.schema_state || 'supported'
        const latestStatusSnapshot = latestEntry.status_snapshot || resolveCurrentAuditGroupState(currentAuditItem)
        return {
            stableKey,
            groupKey: `${stableKey}:${index}`,
            title: currentAuditItem?.title || latestEntry.title || stableKey,
            summary: currentAuditItem?.summary || latestEntry.summary || latestEntry.detail || '',
            categoryLabel: currentAuditItem?.categoryLabel || latestEntry.categoryLabel || latestEntry.category || '',
            chapter: extractSupervisorChapter(currentAuditItem || latestEntry),
            priority: Number(currentAuditItem?.priority || latestEntry.priority || 999),
            schemaVersion: latestEntry.schemaVersion || latestEntry.schema_version || 0,
            schemaState,
            schemaWarning,
            latestStatusSnapshot,
            latestTimestamp: latestEntry.timestamp || '',
            earliestTimestamp: orderedEntries[0]?.timestamp || '',
            latestEntry,
            eventCount: orderedEntries.length,
            compactedEntries,
            compactedEventCount: compactedEntries.length,
            currentState: resolveCurrentAuditGroupState(currentAuditItem),
            actionable: isAuditGroupActionable(currentAuditItem),
        }
    }).sort((left, right) => {
        const leftRank = rankSupervisorAuditGroup(left)
        const rightRank = rankSupervisorAuditGroup(right)
        for (let index = 0; index < Math.max(leftRank.length, rightRank.length); index += 1) {
            const delta = Number(leftRank[index] || 0) - Number(rightRank[index] || 0)
            if (delta !== 0) return delta
        }
        return String(left?.stableKey || '').localeCompare(String(right?.stableKey || ''))
    })
}

export function buildSupervisorAuditViewModel({
    auditItems,
    auditLogEntries,
    auditRepairReports,
    auditChecklists,
    selectedAuditRepairReportPath,
    selectedAuditChecklistPath,
    viewState,
}) {
    const auditItemsByStableKey = new Map()
    ;(auditItems || []).forEach((item) => {
        if (item?.stableKey) auditItemsByStableKey.set(item.stableKey, item)
    })
    const auditCategoryOptionsMap = new Map()
    ;[...(auditItems || []), ...(auditLogEntries || [])].forEach((item) => {
        const key = item?.category || 'unknown'
        if (!auditCategoryOptionsMap.has(key)) {
            auditCategoryOptionsMap.set(key, item?.categoryLabel || key)
        }
    })
    const auditCategoryOptions = [{ value: 'all', label: '全部类型' }, ...[...auditCategoryOptionsMap.entries()].map(([value, label]) => ({ value, label }))]
    const auditActionOptionsMap = new Map()
    ;(auditLogEntries || []).forEach((entry) => {
        const value = String(entry?.action || '').trim()
        if (value && !auditActionOptionsMap.has(value)) {
            auditActionOptionsMap.set(value, formatSupervisorAuditAction(value))
        }
    })
    const auditActionOptions = [{ value: 'all', label: '全部动作' }, ...[...auditActionOptionsMap.entries()].map(([value, label]) => ({ value, label }))]
    const chapters = [...new Set(
        [...(auditItems || []), ...(auditLogEntries || [])]
            .map((item) => extractSupervisorChapter(item))
            .filter((value) => Number.isFinite(value) && value < 999999),
    )]
    chapters.sort((left, right) => left - right)
    const auditChapterOptions = [{ value: 'all', label: '全部章节' }, ...chapters.map((chapter) => ({ value: String(chapter), label: `第 ${chapter} 章` }))]
    const filteredAuditLogEntries = (auditLogEntries || []).filter((entry) => {
        const currentAuditItem = auditItemsByStableKey.get(entry?.stableKey) || null
        const statusValue = resolveCurrentAuditGroupState(currentAuditItem)
        const chapterValue = extractSupervisorChapter(entry?.chapter ? entry : currentAuditItem || entry)
        if (viewState.category !== 'all' && (entry?.category || currentAuditItem?.category) !== viewState.category) return false
        if (viewState.action !== 'all' && String(entry?.action || '').trim() !== viewState.action) return false
        if (viewState.status !== 'all' && statusValue !== viewState.status) return false
        if (viewState.chapter !== 'all' && String(chapterValue) !== viewState.chapter) return false
        return true
    })
    const groupedAuditLogEntries = buildSupervisorAuditGroups(filteredAuditLogEntries, auditItems)
    const filteredGroupedAuditLogEntries = groupedAuditLogEntries.filter((group) => {
        if (viewState.stable_key && group.stableKey !== viewState.stable_key) return false
        if (viewState.group_focus === 'all' || viewState.stable_key) return true
        if (viewState.group_focus === 'actionable') return Boolean(group.actionable)
        return group.currentState === viewState.group_focus
    })
    const filteredAuditRepairReports = (auditRepairReports || []).filter((item) => {
        if (viewState.report_filter === 'changed') return Boolean(item?.changed)
        if (viewState.report_filter === 'manual_only') return !item?.changed && Number(item?.manualReviewCount || 0) > 0
        if (viewState.report_filter === 'unchanged') return !item?.changed
        return true
    })
    const auditRepairReportSummary = {
        visible: filteredAuditRepairReports.length,
        changed: filteredAuditRepairReports.filter((item) => item?.changed).length,
        manualOnly: filteredAuditRepairReports.filter((item) => !item?.changed && Number(item?.manualReviewCount || 0) > 0).length,
        unchanged: filteredAuditRepairReports.filter((item) => !item?.changed).length,
    }
    const sortedAuditRepairReports = [...filteredAuditRepairReports].sort((left, right) => {
        if (viewState.report_sort === 'impact') return buildAuditRepairReportImpactScore(right) - buildAuditRepairReportImpactScore(left)
        if (viewState.report_sort === 'manual') return Number(right?.manualReviewCount || 0) - Number(left?.manualReviewCount || 0)
        if (viewState.report_sort === 'changed') return Number(Boolean(right?.changed)) - Number(Boolean(left?.changed))
        return parseIsoTimestamp(right?.generatedAt) - parseIsoTimestamp(left?.generatedAt)
    })
    const nextVisiblePath = resolveVisibleAuditRepairReportPath(sortedAuditRepairReports, selectedAuditRepairReportPath)
    const selectedVisibleAuditRepairReport = sortedAuditRepairReports.find((item) => item?.relativePath === nextVisiblePath) || null
    const auditSummary = {
        total: (auditItems || []).length,
        linkedTaskCount: (auditItems || []).filter((item) => item?.linkedTaskId).length,
        linkedChecklistCount: (auditItems || []).filter((item) => item?.linkedChecklistPath).length,
        completedCount: (auditItems || []).filter((item) => item?.trackingStatus === 'completed').length,
        dismissedCount: (auditItems || []).filter((item) => item?.dismissed).length,
    }
    const checklistLookup = new Map()
    ;(auditChecklists || []).forEach((item) => checklistLookup.set(item.relativePath, item))
    const selectedAuditChecklist = (auditChecklists || []).find((item) => item.relativePath === selectedAuditChecklistPath) || (auditChecklists || [])[0] || null
    let auditFocusState = null
    if (viewState.stable_key) {
        if (viewState.view_mode !== 'grouped') {
            auditFocusState = { kind: 'view_mode_conflict', message: '当前深链接需要切回“按建议分组”视图。' }
        } else if (!groupedAuditLogEntries.some((group) => group.stableKey === viewState.stable_key)) {
            auditFocusState = { kind: 'event_filters_conflict', message: '当前基础筛选条件已排除这条时间线。' }
        } else if (!filteredGroupedAuditLogEntries.some((group) => group.stableKey === viewState.stable_key)) {
            auditFocusState = { kind: 'group_focus_conflict', message: '当前工作台筛选没有覆盖这条时间线。' }
        }
    }
    return {
        auditCategoryOptions,
        auditActionOptions,
        auditChapterOptions,
        auditItemsByStableKey,
        filteredAuditLogEntries,
        groupedAuditLogEntries,
        filteredGroupedAuditLogEntries,
        auditRepairReportSummary,
        sortedAuditRepairReports,
        nextVisiblePath,
        selectedVisibleAuditRepairReport,
        auditSummary,
        checklistLookup,
        selectedAuditChecklist,
        auditFocusState,
    }
}

export function buildSupervisorAuditMarkdown({ projectInfo, entries, tasks, filters }) {
    const lines = [
        '# 督办审计导出',
        '',
        `- 当前章节：第 ${projectInfo?.progress?.current_chapter || 0} 章`,
        `- 项目总字数：${formatNumber(projectInfo?.progress?.total_words || 0)}`,
        `- 分类筛选：${filters?.category || 'all'}`,
        `- 动作筛选：${filters?.action || 'all'}`,
        `- 状态筛选：${filters?.status || 'all'}`,
        `- 章节筛选：${filters?.chapter || 'all'}`,
        `- 查看方式：${filters?.view_mode === 'events' ? '原始事件流' : '按建议分组'}`,
        `- 工作台聚焦：${filters?.group_focus || 'all'}`,
        `- 导出时间：${formatTimestampShort(new Date().toISOString())}`,
        '',
        '## 审计事件',
    ]

    if (!(entries || []).length) {
        lines.push('- 当前筛选条件下暂无审计事件。')
        return lines.join('\n')
    }

    ;(entries || []).forEach((entry, index) => {
        const sourceTask = (tasks || []).find((task) => task.id === entry?.sourceTaskId) || null
        const linkedTask = (tasks || []).find((task) => task.id === entry?.linkedTaskId) || null
        lines.push(`${index + 1}. ${formatSupervisorAuditAction(entry?.action)}`)
        lines.push(`   - 时间：${formatTimestampShort(entry?.timestamp)}`)
        if (entry?.title) lines.push(`   - 标题：${entry.title}`)
        if (entry?.summary) lines.push(`   - 摘要：${entry.summary}`)
        if (entry?.detail) lines.push(`   - 说明：${entry.detail}`)
        if (entry?.rationale) lines.push(`   - 推荐理由：${entry.rationale}`)
        if (entry?.categoryLabel || entry?.category) lines.push(`   - 类型：${entry?.categoryLabel || entry?.category}`)
        if (entry?.stableKey || entry?.stable_key) lines.push(`   - 建议键：${entry?.stableKey || entry?.stable_key}`)
        if (entry?.chapter) lines.push(`   - 章节：第 ${entry.chapter} 章`)
        if (entry?.status_snapshot) lines.push(`   - 状态快照：${formatSupervisorAuditStatusSnapshot(entry.status_snapshot)}`)
        if (entry?.dismissal_reason) lines.push(`   - 忽略原因：${formatSupervisorDismissReason(entry.dismissal_reason)}`)
        if (entry?.dismissal_note) lines.push(`   - 忽略备注：${entry.dismissal_note}`)
        if (entry?.tracking_note) lines.push(`   - 跟踪备注：${entry.tracking_note}`)
        if (entry?.actionLabel) lines.push(`   - 主动作：${entry.actionLabel}`)
        if (entry?.secondaryLabel) lines.push(`   - 次动作：${entry.secondaryLabel}`)
        if (entry?.schemaVersion || entry?.schema_version) lines.push(`   - Schema：${buildSupervisorAuditSchemaLabel(entry)}`)
        if (entry?.schemaWarning || entry?.schema_warning) lines.push(`   - 兼容提示：${entry?.schemaWarning || entry?.schema_warning}`)
        if (sourceTask) {
            buildAuditTaskRuntimeSummary(sourceTask).forEach((line) => lines.push(`   - 来源任务${line}`))
        }
        if (linkedTask) {
            buildAuditTaskRuntimeSummary(linkedTask).forEach((line) => lines.push(`   - 关联任务${line}`))
        }
        if (entry?.linkedChecklistPath || entry?.checklist_path) lines.push(`   - 关联清单：${entry?.linkedChecklistPath || entry?.checklist_path}`)
        if (entry?.selected_count) lines.push(`   - 清单选中项：${formatNumber(entry.selected_count)}`)
    })

    return lines.join('\n')
}

export function buildSupervisorAuditHealthMarkdown({ projectInfo, health }) {
    const lines = [
        '# 督办审计体检',
        '',
        `- 当前章节：第 ${projectInfo?.progress?.current_chapter || 0} 章`,
        `- 导出时间：${formatTimestampShort(new Date().toISOString())}`,
        `- 日志存在：${health?.exists === false ? '否' : '是'}`,
        `- 健康状态：${health?.healthy ? '通过' : '异常'}`,
        `- 总行数：${formatNumber(health?.total_lines || 0)}`,
        `- 非空行：${formatNumber(health?.nonempty_lines || 0)}`,
        `- 有效事件：${formatNumber(health?.valid_entries || 0)}`,
        `- 问题总数：${formatNumber(health?.issue_count || 0)}`,
    ]

    if (health?.earliestTimestamp) lines.push(`- 最早事件：${formatTimestampShort(health.earliestTimestamp)}`)
    if (health?.latestTimestamp) lines.push(`- 最新事件：${formatTimestampShort(health.latestTimestamp)}`)

    lines.push('', '## 问题分布')
    if (!(health?.issueCounts && Object.keys(health.issueCounts).length)) {
        lines.push('- 当前没有问题摘要。')
    } else {
        Object.entries(health.issueCounts).forEach(([code, count]) => {
            lines.push(`- ${formatSupervisorAuditHealthIssueLabel(code)}：${formatNumber(count)}`)
        })
    }

    lines.push('', '## Schema 分布')
    if (!(health?.schemaStateCounts && Object.keys(health.schemaStateCounts).length)) {
        lines.push('- 当前没有 schema 状态统计。')
    } else {
        Object.entries(health.schemaStateCounts).forEach(([state, count]) => {
            lines.push(`- ${formatSupervisorAuditSchemaState(state)}：${formatNumber(count)}`)
        })
    }

    lines.push('', '## Schema 版本')
    if (!(health?.schemaVersionCounts && Object.keys(health.schemaVersionCounts).length)) {
        lines.push('- 当前没有 schema 版本统计。')
    } else {
        Object.entries(health.schemaVersionCounts).forEach(([version, count]) => {
            lines.push(`- v${version}：${formatNumber(count)}`)
        })
    }

    lines.push('', '## 问题明细')
    if (!(health?.issues || []).length) {
        lines.push('- 当前没有体检问题。')
    } else {
        ;(health.issues || []).forEach((item, index) => {
            lines.push(`${index + 1}. ${formatSupervisorAuditHealthIssueLabel(item?.code)}`)
            lines.push(`   - 严重级别：${item?.severity || 'warning'}`)
            lines.push(`   - 行号：${item?.line || '全局'}`)
            lines.push(`   - 说明：${item?.message || '-'}`)
            if (item?.preview) lines.push(`   - 预览：${item.preview}`)
        })
    }

    return lines.join('\n')
}

export function buildSupervisorAuditRepairPreviewMarkdown({ projectInfo, preview }) {
    const lines = [
        '# 督办修复预演',
        '',
        `- 当前章节：第 ${projectInfo?.progress?.current_chapter || 0} 章`,
        `- 导出时间：${formatTimestampShort(new Date().toISOString())}`,
        `- 日志存在：${preview?.exists === false ? '否' : '是'}`,
        `- 总行数：${formatNumber(preview?.total_lines || 0)}`,
        `- 非空行：${formatNumber(preview?.nonempty_lines || 0)}`,
        `- 可直接修复：${formatNumber(preview?.repairable_count || 0)}`,
        `- 需人工复核：${formatNumber(preview?.manual_review_count || 0)}`,
    ]

    lines.push('', '## 动作分布')
    if (!(preview?.actionCounts && Object.keys(preview.actionCounts).length)) {
        lines.push('- 当前没有动作分布。')
    } else {
        Object.entries(preview.actionCounts).forEach(([action, count]) => {
            lines.push(`- ${formatSupervisorAuditRepairActionLabel(action)}：${formatNumber(count)}`)
        })
    }

    lines.push('', '## 提案明细')
    if (!(preview?.proposals || []).length) {
        lines.push('- 当前没有可预演的修复动作。')
    } else {
        ;(preview.proposals || []).forEach((item, index) => {
            lines.push(`${index + 1}. ${formatSupervisorAuditRepairActionLabel(item?.action)}`)
            lines.push(`   - 严重级别：${item?.severity || 'warning'}`)
            lines.push(`   - 行号：${item?.line || '全局'}`)
            lines.push(`   - 原因：${item?.reason || '-'}`)
            if (item?.stableKey) lines.push(`   - 建议键：${item.stableKey}`)
            if ((item?.issueCodes || []).length) lines.push(`   - 问题：${item.issueCodes.map((code) => formatSupervisorAuditHealthIssueLabel(code)).join(' / ')}`)
            if (item?.preview) lines.push(`   - 预览：${item.preview}`)
            if (item?.proposedEvent) lines.push(`   - 规范事件：${JSON.stringify(item.proposedEvent)}`)
        })
    }

    return lines.join('\n')
}
