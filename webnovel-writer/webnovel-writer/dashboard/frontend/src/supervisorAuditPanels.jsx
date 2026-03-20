import { ErrorNotice } from './appSections.jsx'
import { resolveSupervisorItemOperatorActions } from './operatorAction.js'
import { resolveSupervisorRecoverySemantics } from './recoverySemantics.js'
import {
    SupervisorAuditEventCard,
    SupervisorAuditGroupCard,
} from './auditTimelineCards.jsx'

export function SupervisorAuditHealthPanel({
    auditHealth,
    formatNumber,
    formatTimestampShort,
    formatSupervisorAuditHealthIssueLabel,
    handleDownloadAuditHealthMarkdown,
    handleDownloadAuditHealthJson,
}) {
    return (
        <section className="panel full-span">
            <div className="panel-title">{'\u5ba1\u8ba1\u4f53\u68c0'}</div>
            {!auditHealth ? <div className="empty-state">{'\u6682\u65f6\u672a\u62ff\u5230 audit health \u4fe1\u606f\u3002'}</div> : (
                <>
                    <div className="button-row">
                        <span className={`runtime-badge ${auditHealth.healthy ? 'success' : 'warning'}`}>
                            {auditHealth.healthy ? '\u65e5\u5fd7\u4f53\u68c0\u901a\u8fc7' : '\u65e5\u5fd7\u4f53\u68c0\u5f02\u5e38'}
                        </span>
                        <span className="runtime-badge muted">{`\u626b\u63cf ${formatNumber(auditHealth.nonempty_lines || 0)} / ${formatNumber(auditHealth.total_lines || 0)} \u884c`}</span>
                        <span className="runtime-badge muted">{`\u6709\u6548\u4e8b\u4ef6 ${formatNumber(auditHealth.valid_entries || 0)}`}</span>
                        {auditHealth.latestTimestamp ? <span className="runtime-badge muted">{`\u6700\u65b0\u8bb0\u5f55\uff1a${formatTimestampShort(auditHealth.latestTimestamp)}`}</span> : null}
                    </div>
                    <div className="button-row">
                        <button className="secondary-button" onClick={handleDownloadAuditHealthMarkdown}>
                            {'\u5bfc\u51fa\u4f53\u68c0 Markdown'}
                        </button>
                        <button className="secondary-button" onClick={handleDownloadAuditHealthJson}>
                            {'\u5bfc\u51fa\u4f53\u68c0 JSON'}
                        </button>
                    </div>
                    {auditHealth.exists === false ? (
                        <div className="empty-state">{'\u5f53\u524d\u9879\u76ee\u8fd8\u6ca1\u6709 audit-log.jsonl\u3002'}</div>
                    ) : null}
                    {auditHealth.issue_count ? (
                        <div className="supervisor-grid">
                            {(auditHealth.issues || []).map((item, index) => (
                                <div key={`audit-health-issue:${item.code || index}:${item.line || index}`} className={`supervisor-card ${item.severity === 'danger' ? 'danger' : 'warning'}`}>
                                    <div className="supervisor-card-header">
                                        <div className="supervisor-title">
                                            <span>{formatSupervisorAuditHealthIssueLabel(item.code)}</span>
                                        </div>
                                        <span className={`runtime-badge ${item.severity === 'danger' ? 'danger' : 'warning'}`}>
                                            {item.line ? `Line ${item.line}` : '\u5168\u5c40'}
                                        </span>
                                    </div>
                                    <div className="tiny">{item.message}</div>
                                    {item.preview ? <pre>{item.preview}</pre> : null}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="empty-state">{'\u672a\u53d1\u73b0\u574f JSON\u3001\u7f3a\u5173\u952e\u5b57\u6bb5\u6216\u672a\u6765 schema \u95ee\u9898\u3002'}</div>
                    )}
                </>
            )}
        </section>
    )
}

export function SupervisorAuditRepairPreviewPanel({
    auditRepairPreview,
    formatNumber,
    formatSupervisorAuditRepairActionLabel,
    formatSupervisorAuditHealthIssueLabel,
    handleDownloadAuditRepairPreviewMarkdown,
    handleDownloadAuditRepairPreviewJson,
}) {
    return (
        <section className="panel full-span">
            <div className="panel-title">{'\u4fee\u590d\u9884\u6f14'}</div>
            {!auditRepairPreview ? <div className="empty-state">{'\u6682\u65f6\u672a\u62ff\u5230 repair preview \u4fe1\u606f\u3002'}</div> : (
                <>
                    <div className="button-row">
                        <span className="runtime-badge muted">{`\u53ef\u76f4\u63a5\u4fee\u590d ${formatNumber(auditRepairPreview.repairable_count || 0)}`}</span>
                        <span className="runtime-badge warning">{`\u9700\u4eba\u5de5\u590d\u6838 ${formatNumber(auditRepairPreview.manual_review_count || 0)}`}</span>
                        <span className="runtime-badge muted">{`\u626b\u63cf ${formatNumber(auditRepairPreview.nonempty_lines || 0)} \u884c`}</span>
                    </div>
                    <div className="button-row">
                        <button className="secondary-button" onClick={handleDownloadAuditRepairPreviewMarkdown}>
                            {'\u5bfc\u51fa\u9884\u6f14 Markdown'}
                        </button>
                        <button className="secondary-button" onClick={handleDownloadAuditRepairPreviewJson}>
                            {'\u5bfc\u51fa\u9884\u6f14 JSON'}
                        </button>
                    </div>
                    {auditRepairPreview.exists === false ? (
                        <div className="empty-state">{'\u5f53\u524d\u9879\u76ee\u8fd8\u6ca1\u6709 audit-log.jsonl\u3002'}</div>
                    ) : null}
                    {(auditRepairPreview.proposals || []).length ? (
                        <div className="supervisor-grid">
                            {(auditRepairPreview.proposals || []).map((item, index) => (
                                <div key={`audit-repair-preview:${item.line || index}:${item.action || index}`} className={`supervisor-card ${item.severity === 'danger' ? 'danger' : 'warning'}`}>
                                    <div className="supervisor-card-header">
                                        <div className="supervisor-title">
                                            <span>{formatSupervisorAuditRepairActionLabel(item.action)}</span>
                                        </div>
                                        <span className={`runtime-badge ${item.severity === 'danger' ? 'danger' : 'warning'}`}>
                                            {item.line ? `Line ${item.line}` : '\u5168\u5c40'}
                                        </span>
                                    </div>
                                    <div className="tiny">{item.reason || '-'}</div>
                                    {item.stableKey ? <div className="tiny">{`\u5efa\u8bae\u952e\uff1a${item.stableKey}`}</div> : null}
                                    {(item.issueCodes || []).length ? <div className="tiny">{`\u95ee\u9898\uff1a${item.issueCodes.map((code) => formatSupervisorAuditHealthIssueLabel(code)).join(' / ')}`}</div> : null}
                                    {item.preview ? <pre>{item.preview}</pre> : null}
                                    {item.proposedEvent ? <pre>{JSON.stringify(item.proposedEvent, null, 2)}</pre> : null}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <div className="empty-state">{'\u5f53\u524d\u6ca1\u6709\u53ef\u9884\u6f14\u7684\u4fee\u590d\u52a8\u4f5c\u3002'}</div>
                    )}
                </>
            )}
        </section>
    )
}

export function SupervisorAuditFilterPanel({
    auditCategoryFilter,
    setAuditCategoryFilter,
    auditCategoryOptions,
    auditActionFilter,
    setAuditActionFilter,
    auditActionOptions,
    auditStatusFilter,
    setAuditStatusFilter,
    SUPERVISOR_STATUS_FILTER_OPTIONS,
    auditChapterFilter,
    setAuditChapterFilter,
    auditChapterOptions,
    auditViewMode,
    setAuditViewMode,
    auditGroupFocus,
    setAuditGroupFocus,
    auditGroupFocusOptions,
    auditFocusedStableKey,
    setAuditFocusedStableKey,
    handleDownloadAuditMarkdown,
    handleDownloadAuditJson,
}) {
    return (
        <section className="panel full-span">
            <div className="panel-title">{'审计筛选'}</div>
            <div className="detail-grid">
                <label className="field">
                    <span>{'建议类型'}</span>
                    <select value={auditCategoryFilter} onChange={(event) => setAuditCategoryFilter(event.target.value)}>
                        {auditCategoryOptions.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                    </select>
                </label>
                <label className="field">
                    <span>{'审计动作'}</span>
                    <select value={auditActionFilter} onChange={(event) => setAuditActionFilter(event.target.value)}>
                        {auditActionOptions.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                    </select>
                </label>
                <label className="field">
                    <span>{'状态'}</span>
                    <select value={auditStatusFilter} onChange={(event) => setAuditStatusFilter(event.target.value)}>
                        {SUPERVISOR_STATUS_FILTER_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                    </select>
                </label>
                <label className="field">
                    <span>{'章节'}</span>
                    <select value={auditChapterFilter} onChange={(event) => setAuditChapterFilter(event.target.value)}>
                        {auditChapterOptions.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                    </select>
                </label>
                <label className="field">
                    <span>{'查看方式'}</span>
                    <select value={auditViewMode} onChange={(event) => setAuditViewMode(event.target.value)}>
                        <option value="grouped">{'按建议分组'}</option>
                        <option value="events">{'原始事件流'}</option>
                    </select>
                </label>
                <label className="field">
                    <span>{'工作台筛选'}</span>
                    <select value={auditGroupFocus} onChange={(event) => setAuditGroupFocus(event.target.value)} disabled={auditViewMode !== 'grouped'}>
                        {auditGroupFocusOptions.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                    </select>
                </label>
            </div>
            <div className="button-row">
                {auditFocusedStableKey ? (
                    <button className="secondary-button" onClick={() => setAuditFocusedStableKey('')}>
                        {'清除聚焦'}
                    </button>
                ) : null}
                <button className="secondary-button" onClick={handleDownloadAuditMarkdown}>
                    {'导出当前筛选 Markdown'}
                </button>
                <button className="secondary-button" onClick={handleDownloadAuditJson}>
                    {'导出当前筛选 JSON'}
                </button>
            </div>
        </section>
    )
}

export function SupervisorAuditTimelinePanel({
    auditFocusState,
    setAuditViewMode,
    handleResetAuditEventFilters,
    handleResetAuditGroupFilters,
    setAuditFocusedStableKey,
    auditViewMode,
    filteredGroupedAuditLogEntries,
    filteredAuditLogEntries,
    auditItemsByStableKey,
    tasks,
    checklistLookup,
    selectedAuditChecklist,
    auditFocusedStableKey,
    auditSubmitting,
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
    handleCopyAuditGroupLink,
    onOpenTask,
    setSelectedAuditChecklistPath,
    handleAuditGroupAction,
    handleAuditGroupTracking,
    handleAuditGroupUndismiss,
    handleAuditGroupTrackingClear,
    handleDownloadAuditChecklist,
    auditError,
}) {
    return (
        <section className="panel full-span">
            <div className="panel-title">{'审计时间线'}</div>
            <div className="empty-state">{'这里显示 Supervisor 的状态变更、忽略 / 恢复、清单保存等审计事件。'}</div>
            {auditFocusState ? (
                <div className="error-panel">
                    <div className="error-title">{'深链接聚焦失败'}</div>
                    <div className="error-details">{auditFocusState.message}</div>
                    <div className="button-row">
                        {auditFocusState.kind === 'view_mode_conflict' ? (
                            <button className="secondary-button" onClick={() => setAuditViewMode('grouped')}>
                                {'切回按建议分组'}
                            </button>
                        ) : null}
                        {auditFocusState.kind === 'event_filters_conflict' ? (
                            <button className="secondary-button" onClick={handleResetAuditEventFilters}>
                                {'清除基础筛选'}
                            </button>
                        ) : null}
                        {auditFocusState.kind === 'group_focus_conflict' ? (
                            <button className="secondary-button" onClick={handleResetAuditGroupFilters}>
                                {'清除工作台筛选'}
                            </button>
                        ) : null}
                        <button className="secondary-button" onClick={() => setAuditFocusedStableKey('')}>
                            {'移除这条深链接聚焦'}
                        </button>
                    </div>
                </div>
            ) : null}
            <div className="supervisor-grid">
                {auditViewMode === 'grouped' ? filteredGroupedAuditLogEntries.map((group) => {
                    const latestEntry = group.latestEntry || {}
                    const currentAuditItem = auditItemsByStableKey.get(group.stableKey) || null
                    const sourceTask = tasks.find((task) => task.id === latestEntry.sourceTaskId) || null
                    const linkedTask = tasks.find((task) => task.id === latestEntry.linkedTaskId) || null
                    const linkedChecklist = checklistLookup.get(latestEntry.linkedChecklistPath || latestEntry.checklist_path) || null
                    const recoverySemantics = currentAuditItem ? resolveSupervisorRecoverySemantics(currentAuditItem) : null
                    const operatorActions = currentAuditItem ? resolveSupervisorItemOperatorActions(currentAuditItem) : []
                    return (
                        <SupervisorAuditGroupCard
                            key={`audit-group:${group.groupKey}`}
                            group={group}
                            latestEntry={latestEntry}
                            currentAuditItem={currentAuditItem}
                            sourceTask={sourceTask}
                            linkedTask={linkedTask}
                            linkedChecklist={linkedChecklist}
                            selectedAuditChecklist={selectedAuditChecklist}
                            auditFocusedStableKey={auditFocusedStableKey}
                            auditSubmitting={auditSubmitting}
                            recoverySemantics={recoverySemantics}
                            operatorActions={operatorActions}
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
                            setAuditFocusedStableKey={setAuditFocusedStableKey}
                            handleCopyAuditGroupLink={handleCopyAuditGroupLink}
                            onOpenTask={onOpenTask}
                            setSelectedAuditChecklistPath={setSelectedAuditChecklistPath}
                            handleAuditGroupAction={handleAuditGroupAction}
                            handleAuditGroupTracking={handleAuditGroupTracking}
                            handleAuditGroupUndismiss={handleAuditGroupUndismiss}
                            handleAuditGroupTrackingClear={handleAuditGroupTrackingClear}
                        />
                    )
                }) : filteredAuditLogEntries.map((entry, index) => {
                    const sourceTask = tasks.find((task) => task.id === entry.sourceTaskId) || null
                    const linkedTask = tasks.find((task) => task.id === entry.linkedTaskId) || null
                    const linkedChecklist = checklistLookup.get(entry.linkedChecklistPath || entry.checklist_path) || null
                    return (
                        <SupervisorAuditEventCard
                            key={`audit-log:${entry.timestamp || index}:${entry.action || 'event'}`}
                            entry={entry}
                            index={index}
                            sourceTask={sourceTask}
                            linkedTask={linkedTask}
                            linkedChecklist={linkedChecklist}
                            selectedAuditChecklist={selectedAuditChecklist}
                            formatTimestampShort={formatTimestampShort}
                            formatSupervisorAuditAction={formatSupervisorAuditAction}
                            buildSupervisorAuditSchemaLabel={buildSupervisorAuditSchemaLabel}
                            formatSupervisorAuditStatusSnapshot={formatSupervisorAuditStatusSnapshot}
                            formatSupervisorDismissReason={formatSupervisorDismissReason}
                            buildAuditTaskRuntimeSummary={buildAuditTaskRuntimeSummary}
                            onOpenTask={onOpenTask}
                            setSelectedAuditChecklistPath={setSelectedAuditChecklistPath}
                            handleDownloadAuditChecklist={handleDownloadAuditChecklist}
                            formatNumber={formatNumber}
                        />
                    )
                })}
                {(auditViewMode === 'grouped' ? filteredGroupedAuditLogEntries.length === 0 : filteredAuditLogEntries.length === 0) ? <div className="empty-state">{'当前筛选条件下暂无审计事件。'}</div> : null}
            </div>
            {auditError ? <ErrorNotice error={auditError} /> : null}
        </section>
    )
}

export function SupervisorAuditRepairArchivePanel({
    auditRepairReportFilter,
    setAuditRepairReportFilter,
    auditRepairReportSortMode,
    setAuditRepairReportSortMode,
    AUDIT_REPAIR_REPORT_SORT_OPTIONS,
    auditRepairReportSummary,
    auditRepairReports,
    sortedAuditRepairReports,
    selectedVisibleAuditRepairReport,
    setSelectedAuditRepairReportPath,
    handleDownloadAuditRepairReport,
    formatTimestampShort,
    formatNumber,
    formatAuditRepairReportSummary,
}) {
    return (
        <>
            <section className="panel full-span">
                <div className="panel-title">{'修复归档'}</div>
                <div className="detail-grid">
                    <label className="field">
                        <span>{'归档筛选'}</span>
                        <select value={auditRepairReportFilter} onChange={(event) => setAuditRepairReportFilter(event.target.value)}>
                            <option value="all">{'全部批次'}</option>
                            <option value="changed">{'已改动日志'}</option>
                            <option value="manual_only">{'仅人工复核'}</option>
                            <option value="unchanged">{'无文件改动'}</option>
                        </select>
                    </label>
                    <label className="field">
                        <span>{'排序方式'}</span>
                        <select value={auditRepairReportSortMode} onChange={(event) => setAuditRepairReportSortMode(event.target.value)}>
                            {AUDIT_REPAIR_REPORT_SORT_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                        </select>
                    </label>
                </div>
                <div className="summary-grid">
                    <div className="summary-card">
                        <div className="summary-card-title">{'当前命中'}</div>
                        <div className="summary-card-meta">{`${formatNumber(auditRepairReportSummary.visible)} 份报告`}</div>
                        <div className="summary-card-meta">{`全部归档 ${formatNumber(auditRepairReports.length)} 份`}</div>
                    </div>
                    <div className="summary-card">
                        <div className="summary-card-title">{'已改动日志'}</div>
                        <div className="summary-card-meta">{`${formatNumber(auditRepairReportSummary.changed)} 份`}</div>
                        <div className="summary-card-meta">{'至少包含自动修复写回'}</div>
                    </div>
                    <div className="summary-card">
                        <div className="summary-card-title">{'仅人工复核'}</div>
                        <div className="summary-card-meta">{`${formatNumber(auditRepairReportSummary.manualOnly)} 份`}</div>
                        <div className="summary-card-meta">{'没有自动改写，仅保留人工处理项'}</div>
                    </div>
                    <div className="summary-card">
                        <div className="summary-card-title">{'无文件改动'}</div>
                        <div className="summary-card-meta">{`${formatNumber(auditRepairReportSummary.unchanged)} 份`}</div>
                        <div className="summary-card-meta">{'包含 manual-only 与纯记录批次'}</div>
                    </div>
                </div>
                <div className="supervisor-grid">
                    {sortedAuditRepairReports.map((item) => (
                        <div key={`audit-repair-report:${item.relativePath}`} className={`supervisor-card ${item.changed ? 'warning' : 'success'}`}>
                            <div className="supervisor-card-header">
                                <div className="supervisor-title">
                                    <span>{item.filename || 'repair report'}</span>
                                </div>
                                <span className="runtime-badge">{formatTimestampShort(item.generatedAt)}</span>
                            </div>
                            <div className="tiny">{`路径：${item.relativePath}`}</div>
                            <div className="tiny">{formatAuditRepairReportSummary(item)}</div>
                            <div className="tiny">{`变更：${item.changed ? '已修复日志' : '仅记录，无文件改动'}`}</div>
                            <div className="tiny">{`删除坏行：${formatNumber(item.droppedCount)}`}</div>
                            <div className="tiny">{`重写事件：${formatNumber(item.rewrittenCount)}`}</div>
                            <div className="tiny">{`人工复核：${formatNumber(item.manualReviewCount)}`}</div>
                            {item.backupCreated && item.backupPath ? <div className="tiny">{`备份：${item.backupPath}`}</div> : null}
                            <div className="button-row">
                                <button className="secondary-button" onClick={() => setSelectedAuditRepairReportPath(item.relativePath)}>
                                    {selectedVisibleAuditRepairReport?.relativePath === item.relativePath ? '已在查看' : '查看报告'}
                                </button>
                                <button className="secondary-button" onClick={() => handleDownloadAuditRepairReport(item)}>
                                    {'下载报告'}
                                </button>
                            </div>
                        </div>
                    ))}
                    {sortedAuditRepairReports.length === 0 ? <div className="empty-state">{'当前筛选下没有 repair report。'}</div> : null}
                </div>
            </section>
            {selectedVisibleAuditRepairReport ? (
                <section className="panel full-span">
                    <div className="panel-title">{selectedVisibleAuditRepairReport.filename || '修复报告预览'}</div>
                    <div className="tiny">{`路径：${selectedVisibleAuditRepairReport.relativePath}`}</div>
                    {selectedVisibleAuditRepairReport.backupCreated && selectedVisibleAuditRepairReport.backupPath ? <div className="tiny">{`备份：${selectedVisibleAuditRepairReport.backupPath}`}</div> : null}
                    {selectedVisibleAuditRepairReport.content ? <pre>{JSON.stringify(selectedVisibleAuditRepairReport.content, null, 2)}</pre> : null}
                </section>
            ) : null}
        </>
    )
}

export function SupervisorAuditChecklistArchivePanel({
    auditChecklists,
    selectedAuditChecklist,
    setSelectedAuditChecklistPath,
    handleDownloadAuditChecklist,
    formatTimestampShort,
}) {
    return (
        <>
            <section className="panel full-span">
                <div className="panel-title">{'清单归档'}</div>
                <div className="supervisor-grid">
                    {auditChecklists.map((item) => (
                        <div key={`audit-checklist:${item.relativePath}`} className="supervisor-card success">
                            <div className="supervisor-card-header">
                                <div className="supervisor-title">
                                    <span>{item.title || `第 ${item.chapter || 0} 章清单`}</span>
                                </div>
                                <span className="runtime-badge">{formatTimestampShort(item.savedAt)}</span>
                            </div>
                            <div className="tiny">{`路径：${item.relativePath}`}</div>
                            {item.note ? <div className="tiny">{`备注：${item.note}`}</div> : null}
                            <div className="supervisor-meta">{item.summary || '已保存的 Supervisor 清单'}</div>
                            <div className="button-row">
                                <button className="secondary-button" onClick={() => setSelectedAuditChecklistPath(item.relativePath)}>
                                    {selectedAuditChecklist?.relativePath === item.relativePath ? '已在查看' : '查看内容'}
                                </button>
                                <button className="secondary-button" onClick={() => handleDownloadAuditChecklist(item)}>
                                    {'下载清单'}
                                </button>
                            </div>
                        </div>
                    ))}
                    {auditChecklists.length === 0 ? <div className="empty-state">{'暂时还没有可用的审计清单。'}</div> : null}
                </div>
            </section>
            {selectedAuditChecklist ? (
                <section className="panel full-span">
                    <div className="panel-title">{selectedAuditChecklist.title || '关联清单预览'}</div>
                    <div className="tiny">{`路径：${selectedAuditChecklist.relativePath}`}</div>
                    {selectedAuditChecklist.note ? <div className="tiny">{`备注：${selectedAuditChecklist.note}`}</div> : null}
                    {selectedAuditChecklist.content ? <pre>{selectedAuditChecklist.content}</pre> : null}
                </section>
            ) : null}
        </>
    )
}
