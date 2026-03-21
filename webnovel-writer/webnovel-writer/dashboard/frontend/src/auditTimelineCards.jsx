export function SupervisorAuditGroupCard({
    group,
    latestEntry,
    currentAuditItem,
    sourceTask,
    linkedTask,
    linkedChecklist,
    selectedAuditChecklist,
    auditFocusedStableKey,
    auditSubmitting,
    recoverySemantics,
    operatorActions,
    formatNumber,
    formatTimestampShort,
    formatSupervisorAuditStatusSnapshot,
    formatSupervisorDismissReason,
    formatSupervisorTrackingStatus,
    formatSupervisorAuditAction,
    buildSupervisorAuditSchemaLabel,
    buildSupervisorAuditGroupAnchorId,
    buildAuditTaskRuntimeSummary,
    renderOperatorActionButtons,
    setAuditFocusedStableKey,
    handleCopyAuditGroupLink,
    onOpenTask,
    setSelectedAuditChecklistPath,
    handleAuditGroupAction,
    handleAuditGroupTracking,
    handleAuditGroupUndismiss,
    handleAuditGroupTrackingClear,
}) {
    return (
        <div
            id={buildSupervisorAuditGroupAnchorId(group.stableKey)}
            className={`supervisor-card ${auditFocusedStableKey && group.stableKey === auditFocusedStableKey ? 'success' : ''}`}
        >
            <div className="supervisor-card-header">
                <div className="supervisor-title">
                    <span>{group.title}</span>
                </div>
                <div className="button-row">
                    {group.schemaVersion ? (
                        <span className={`runtime-badge ${group.schemaState === 'future' ? 'warning' : 'muted'}`}>
                            {buildSupervisorAuditSchemaLabel(group)}
                        </span>
                    ) : null}
                    <span className="runtime-badge">{`${formatNumber(group.compactedEventCount)} / ${formatNumber(group.eventCount)} 条事件`}</span>
                </div>
            </div>
            {group.summary ? <div className="supervisor-meta">{group.summary}</div> : null}
            {group.stableKey ? <div className="tiny">{`建议键：${group.stableKey}`}</div> : null}
            {group.categoryLabel ? <div className="tiny">{`类型：${group.categoryLabel}`}</div> : null}
            {group.schemaWarning ? <div className="tiny">{`兼容提示：${group.schemaWarning}`}</div> : null}
            {group.chapter ? <div className="tiny">{`章节：第 ${group.chapter} 章`}</div> : null}
            {group.latestStatusSnapshot ? <div className="tiny">{`最新状态：${formatSupervisorAuditStatusSnapshot(group.latestStatusSnapshot)}`}</div> : null}
            {group.latestTimestamp ? <div className="tiny">{`最新变更：${formatTimestampShort(group.latestTimestamp)}`}</div> : null}
            {group.earliestTimestamp ? <div className="tiny">{`首次记录：${formatTimestampShort(group.earliestTimestamp)}`}</div> : null}
            {group.eventCount !== group.compactedEventCount ? <div className="tiny">{`已压缩展示：${formatNumber(group.eventCount - group.compactedEventCount)} 条 tracking 更新`}</div> : null}
            <div className="tiny">{`当前建议状态：${currentAuditItem ? currentAuditItem.dismissed ? '已从 Inbox 移除' : '可直接执行' : '建议已不存在'}`}</div>
            {latestEntry.rationale ? <div className="tiny">{`当时推荐理由：${latestEntry.rationale}`}</div> : null}
            {latestEntry.actionLabel ? <div className="tiny">{`当时建议动作：${latestEntry.actionLabel}`}</div> : null}
            {recoverySemantics ? <div className="tiny">{`恢复语义：${recoverySemantics.label}`}</div> : null}
            {recoverySemantics ? <div className="tiny">{`主恢复动作：${recoverySemantics.primaryActionLabel}`}</div> : null}
            {recoverySemantics ? <div className="tiny">{`恢复后目标：${recoverySemantics.followupLabel}`}</div> : null}
            {recoverySemantics?.reviewSummaryHint ? <div className="tiny">{`问题汇总：${recoverySemantics.reviewSummaryHint}`}</div> : null}
            {group.stableKey ? (
                <div className="button-row">
                    <button className="secondary-button" onClick={() => setAuditFocusedStableKey(group.stableKey)}>
                        {auditFocusedStableKey === group.stableKey ? '已聚焦' : '聚焦这条时间线'}
                    </button>
                    <button className="secondary-button" onClick={() => handleCopyAuditGroupLink(group.stableKey)}>
                        {'复制深链接'}
                    </button>
                </div>
            ) : null}
            {currentAuditItem?.trackingStatus ? <div className="tiny">{`当前跟踪状态：${currentAuditItem.trackingLabel || formatSupervisorTrackingStatus(currentAuditItem.trackingStatus)}`}</div> : null}
            {currentAuditItem?.trackingNote ? <div className="tiny">{`当前状态备注：${currentAuditItem.trackingNote}`}</div> : null}
            {sourceTask ? buildAuditTaskRuntimeSummary(sourceTask).map((line) => (
                <div key={`group-source-task:${group.groupKey}:${line}`} className="tiny">{`来源任务${line}`}</div>
            )) : null}
            {linkedTask ? buildAuditTaskRuntimeSummary(linkedTask).map((line) => (
                <div key={`group-linked-task:${group.groupKey}:${line}`} className="tiny">{`关联任务${line}`}</div>
            )) : null}
            {linkedChecklist?.title ? <div className="tiny">{`关联清单：${linkedChecklist.title}`}</div> : null}
            {(latestEntry.sourceTaskId || latestEntry.linkedTaskId || linkedChecklist) ? (
                <div className="button-row">
                    {latestEntry.sourceTaskId ? (
                        <button className="secondary-button" onClick={() => onOpenTask(latestEntry.sourceTaskId)}>
                            {'打开来源任务'}
                        </button>
                    ) : null}
                    {latestEntry.linkedTaskId ? (
                        <button className="secondary-button" onClick={() => onOpenTask(latestEntry.linkedTaskId)}>
                            {'打开关联任务'}
                        </button>
                    ) : null}
                    {linkedChecklist ? (
                        <button className="secondary-button" onClick={() => setSelectedAuditChecklistPath(linkedChecklist.relativePath)}>
                            {selectedAuditChecklist?.relativePath === linkedChecklist.relativePath ? '已在预览' : '预览关联清单'}
                        </button>
                    ) : null}
                </div>
            ) : null}
            {currentAuditItem ? (
                <div className="button-row">
                    {renderOperatorActionButtons(operatorActions, (action) => handleAuditGroupAction(currentAuditItem, action), auditSubmitting, currentAuditItem.actionLabel || '执行当前建议')}
                    {!currentAuditItem.dismissed && currentAuditItem.trackingStatus !== 'in_progress' ? (
                        <button className="secondary-button" onClick={() => handleAuditGroupTracking(currentAuditItem, 'in_progress')} disabled={auditSubmitting}>
                            {auditSubmitting ? '处理中...' : '标记处理中'}
                        </button>
                    ) : null}
                    {!currentAuditItem.dismissed && currentAuditItem.trackingStatus !== 'completed' ? (
                        <button className="secondary-button" onClick={() => handleAuditGroupTracking(currentAuditItem, 'completed')} disabled={auditSubmitting}>
                            {auditSubmitting ? '处理中...' : '标记已处理'}
                        </button>
                    ) : null}
                    {currentAuditItem.dismissed ? (
                        <button className="secondary-button" onClick={() => handleAuditGroupUndismiss(currentAuditItem)} disabled={auditSubmitting}>
                            {auditSubmitting ? '处理中...' : '恢复建议'}
                        </button>
                    ) : null}
                    {currentAuditItem.trackingStatus ? (
                        <button className="secondary-button" onClick={() => handleAuditGroupTrackingClear(currentAuditItem)} disabled={auditSubmitting}>
                            {auditSubmitting ? '处理中...' : '清除跟踪状态'}
                        </button>
                    ) : null}
                </div>
            ) : null}
            <div className="tiny">{'时间线：'}</div>
            <div className="supervisor-grid">
                {group.compactedEntries.map((entry, index) => (
                    <div key={`audit-group-entry:${group.groupKey}:${entry.timestamp || index}:${entry.action || 'event'}`} className="supervisor-card">
                        <div className="supervisor-card-header">
                            <div className="supervisor-title">
                                <span>{formatSupervisorAuditAction(entry.action)}</span>
                            </div>
                            <span className="runtime-badge">{formatTimestampShort(entry.timestamp)}</span>
                        </div>
                        {Number(entry.mergedCount || 1) > 1 ? <div className="tiny">{`已合并 ${formatNumber(entry.mergedCount)} 条连续 tracking 更新`}</div> : null}
                        {entry.status_snapshot ? <div className="tiny">{`状态快照：${formatSupervisorAuditStatusSnapshot(entry.status_snapshot)}`}</div> : null}
                        {entry.dismissal_reason ? <div className="tiny">{`忽略原因：${formatSupervisorDismissReason(entry.dismissal_reason)}`}</div> : null}
                        {entry.dismissal_note ? <div className="tiny">{`忽略备注：${entry.dismissal_note}`}</div> : null}
                        {entry.tracking_note ? <div className="tiny">{`状态备注：${entry.tracking_note}`}</div> : null}
                        {entry.linkedChecklistPath || entry.checklist_path ? <div className="tiny">{`关联清单：${entry.linkedChecklistPath || entry.checklist_path}`}</div> : null}
                    </div>
                ))}
            </div>
        </div>
    )
}

export function SupervisorAuditEventCard({
    entry,
    index,
    sourceTask,
    linkedTask,
    linkedChecklist,
    selectedAuditChecklist,
    formatTimestampShort,
    formatSupervisorAuditAction,
    buildSupervisorAuditSchemaLabel,
    formatSupervisorAuditStatusSnapshot,
    formatSupervisorDismissReason,
    buildAuditTaskRuntimeSummary,
    onOpenTask,
    setSelectedAuditChecklistPath,
    handleDownloadAuditChecklist,
    formatNumber,
}) {
    return (
        <div key={`audit-log:${entry.timestamp || index}:${entry.action || 'event'}`} className="supervisor-card">
            <div className="supervisor-card-header">
                <div className="supervisor-title">
                    <span>{formatSupervisorAuditAction(entry.action)}</span>
                </div>
                <div className="button-row">
                    {(entry.schemaVersion || entry.schema_version) ? (
                        <span className={`runtime-badge ${String(entry.schemaState || entry.schema_state || '').trim() === 'future' ? 'warning' : 'muted'}`}>
                            {buildSupervisorAuditSchemaLabel(entry)}
                        </span>
                    ) : null}
                    <span className="runtime-badge">{formatTimestampShort(entry.timestamp)}</span>
                </div>
            </div>
            {entry.title ? <div className="supervisor-meta">{entry.title}</div> : null}
            {entry.summary ? <div className="tiny">{entry.summary}</div> : null}
            {entry.detail ? <div className="tiny">{`当时建议说明：${entry.detail}`}</div> : null}
            {entry.rationale ? <div className="tiny">{`当时推荐理由：${entry.rationale}`}</div> : null}
            {entry.categoryLabel || entry.category ? <div className="tiny">{`类型：${entry.categoryLabel || entry.category}`}</div> : null}
            {entry.schemaWarning || entry.schema_warning ? <div className="tiny">{`兼容提示：${entry.schemaWarning || entry.schema_warning}`}</div> : null}
            {entry.badge ? <div className="tiny">{`当时标签：${entry.badge}`}</div> : null}
            {entry.priority ? <div className="tiny">{`当时优先级：${entry.priority}`}</div> : null}
            {entry.tone ? <div className="tiny">{`当时颜色：${entry.tone}`}</div> : null}
            {entry.chapter ? <div className="tiny">{`章节：第 ${entry.chapter} 章`}</div> : null}
            {entry.status_snapshot ? <div className="tiny">{`状态快照：${formatSupervisorAuditStatusSnapshot(entry.status_snapshot)}`}</div> : null}
            {entry.dismissal_reason ? <div className="tiny">{`忽略原因：${formatSupervisorDismissReason(entry.dismissal_reason)}`}</div> : null}
            {entry.dismissal_note ? <div className="tiny">{`忽略备注：${entry.dismissal_note}`}</div> : null}
            {entry.tracking_note ? <div className="tiny">{`状态备注：${entry.tracking_note}`}</div> : null}
            {entry.actionLabel ? <div className="tiny">{`当时建议动作：${entry.actionLabel}`}</div> : null}
            {entry.secondaryLabel ? <div className="tiny">{`当时备选动作：${entry.secondaryLabel}`}</div> : null}
            {entry.sourceTaskId ? <div className="tiny">{`来源任务：${entry.sourceTaskId}`}</div> : null}
            {sourceTask ? buildAuditTaskRuntimeSummary(sourceTask).map((line) => (
                <div key={`source-task:${entry.sourceTaskId}:${line}`} className="tiny">{`来源任务${line}`}</div>
            )) : null}
            {entry.sourceTaskId ? (
                <div className="button-row">
                    <button className="secondary-button" onClick={() => onOpenTask(entry.sourceTaskId)}>
                        {'打开来源任务'}
                    </button>
                </div>
            ) : null}
            {entry.linkedTaskId ? <div className="tiny">{`关联任务：${entry.linkedTaskId}`}</div> : null}
            {linkedTask ? buildAuditTaskRuntimeSummary(linkedTask).map((line) => (
                <div key={`linked-task:${entry.linkedTaskId}:${line}`} className="tiny">{`关联任务${line}`}</div>
            )) : null}
            {entry.linkedTaskId ? (
                <div className="button-row">
                    <button className="secondary-button" onClick={() => onOpenTask(entry.linkedTaskId)}>
                        {'打开关联任务'}
                    </button>
                </div>
            ) : null}
            {entry.linkedChecklistPath || entry.checklist_path ? <div className="tiny">{`关联清单：${entry.linkedChecklistPath || entry.checklist_path}`}</div> : null}
            {linkedChecklist?.title ? <div className="tiny">{`清单标题：${linkedChecklist.title}`}</div> : null}
            {linkedChecklist?.summary ? <div className="tiny">{`清单摘要：${linkedChecklist.summary}`}</div> : null}
            {entry.selected_count ? <div className="tiny">{`清单选中项：${formatNumber(entry.selected_count)}`}</div> : null}
            {linkedChecklist ? (
                <div className="button-row">
                    <button className="secondary-button" onClick={() => setSelectedAuditChecklistPath(linkedChecklist.relativePath)}>
                        {selectedAuditChecklist?.relativePath === linkedChecklist.relativePath ? '已在预览' : '预览关联清单'}
                    </button>
                    <button className="secondary-button" onClick={() => handleDownloadAuditChecklist(linkedChecklist)}>
                        {'下载关联清单'}
                    </button>
                </div>
            ) : null}
        </div>
    )
}
