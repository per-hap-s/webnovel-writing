function RecoverySemanticsDetails({ recoverySemantics }) {
    if (!recoverySemantics) return null
    return (
        <>
            <div className="tiny">{`\u6062\u590d\u8bed\u4e49\uff1a${recoverySemantics.label}`}</div>
            <div className="tiny">{`\u4e3b\u6062\u590d\u52a8\u4f5c\uff1a${recoverySemantics.primaryActionLabel}`}</div>
            <div className="tiny">{`\u6062\u590d\u540e\u76ee\u6807\uff1a${recoverySemantics.followupLabel}`}</div>
            {recoverySemantics.reviewSummaryHint ? <div className="tiny">{`\u5ba1\u67e5\u6458\u8981\uff1a${recoverySemantics.reviewSummaryHint}`}</div> : null}
        </>
    )
}

export function SupervisorActiveCard({
    item,
    draft,
    trackingDraft,
    operatorActions,
    recoverySemantics,
    recentChecklists,
    supervisorSubmitting,
    selectedSupervisorKeys,
    toggleSupervisorSelection,
    updateTrackingDraft,
    updateDismissDraft,
    handleSupervisorTrackingSave,
    handleSupervisorTrackingClear,
    handleSupervisorAction,
    handleSupervisorDismiss,
    renderOperatorActionButtons,
    formatSupervisorTrackingStatus,
    formatTimestampShort,
    SUPERVISOR_TRACKING_STATUS_OPTIONS,
    SUPERVISOR_DISMISS_REASON_OPTIONS,
}) {
    return (
        <div className={`supervisor-card ${item.tone}`}>
            <div className="supervisor-card-header">
                <div className="supervisor-title">
                    <label className="checkbox-row">
                        <input
                            type="checkbox"
                            checked={selectedSupervisorKeys.includes(item.stableKey)}
                            onChange={() => toggleSupervisorSelection(item.stableKey)}
                        />
                        <span>{item.title}</span>
                    </label>
                </div>
                <span className={`runtime-badge ${item.tone}`}>{item.badge}</span>
            </div>
            <div className="tiny">{'\u7c7b\u578b\uff1a'}{item.categoryLabel || item.category || '-'}</div>
            <div className="supervisor-meta">{item.summary}</div>
            <div className="tiny">{item.detail}</div>
            <div className="tiny">{'\u4e3a\u4ec0\u4e48\u63a8\u8350\uff1a'}{item.rationale}</div>
            <RecoverySemanticsDetails recoverySemantics={recoverySemantics} />
            {item.trackingStatus ? <div className="tiny">{`\u5904\u7406\u72b6\u6001\uff1a${item.trackingLabel || formatSupervisorTrackingStatus(item.trackingStatus)} / ${formatTimestampShort(item.trackingUpdatedAt)}`}</div> : null}
            {item.trackingNote ? <div className="tiny">{`\u72b6\u6001\u5907\u6ce8\uff1a${item.trackingNote}`}</div> : null}
            {item.linkedTaskId ? <div className="tiny">{`\u5173\u8054\u4efb\u52a1\uff1a${item.linkedTaskId}`}</div> : null}
            {item.linkedChecklistPath ? <div className="tiny">{`\u5173\u8054\u6e05\u5355\uff1a${item.linkedChecklistPath}`}</div> : null}
            <div className="field-stack">
                <label className="field">
                    <span>{'\u5904\u7406\u72b6\u6001'}</span>
                    <select value={trackingDraft.status} onChange={(event) => updateTrackingDraft(item.stableKey, { status: event.target.value })}>
                        <option value="">{'\u8bf7\u9009\u62e9\u72b6\u6001'}</option>
                        {SUPERVISOR_TRACKING_STATUS_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                    </select>
                </label>
                <label className="field">
                    <span>{'\u72b6\u6001\u5907\u6ce8'}</span>
                    <textarea
                        value={trackingDraft.note}
                        onChange={(event) => updateTrackingDraft(item.stableKey, { note: event.target.value })}
                        placeholder={'\u53ef\u9009\uff0c\u8bb0\u5f55\u8fd9\u6761\u5efa\u8bae\u5f53\u524d\u5904\u7406\u5230\u54ea\u4e00\u6b65'}
                    />
                </label>
                <label className="field">
                    <span>{'\u5173\u8054\u4efb\u52a1 ID'}</span>
                    <input
                        value={trackingDraft.linkedTaskId}
                        onChange={(event) => updateTrackingDraft(item.stableKey, { linkedTaskId: event.target.value })}
                        placeholder={'\u53ef\u9009\uff0c\u5982 task-123'}
                    />
                </label>
                <label className="field">
                    <span>{'\u5173\u8054\u6e05\u5355'}</span>
                    <select value={trackingDraft.linkedChecklistPath} onChange={(event) => updateTrackingDraft(item.stableKey, { linkedChecklistPath: event.target.value })}>
                        <option value="">{'\u4e0d\u5173\u8054\u6e05\u5355'}</option>
                        {recentChecklists.map((checklist) => (
                            <option key={checklist.relativePath} value={checklist.relativePath}>
                                {checklist.title || checklist.relativePath}
                            </option>
                        ))}
                    </select>
                </label>
            </div>
            <div className="button-row">
                <button className="secondary-button" onClick={() => handleSupervisorTrackingSave(item)} disabled={supervisorSubmitting || !trackingDraft.status}>
                    {supervisorSubmitting ? '\u5904\u7406\u4e2d...' : '\u5199\u5165\u72b6\u6001'}
                </button>
                <button className="secondary-button" onClick={() => handleSupervisorTrackingClear(item)} disabled={supervisorSubmitting || !item.trackingStatus}>
                    {supervisorSubmitting ? '\u5904\u7406\u4e2d...' : '\u6e05\u9664\u72b6\u6001'}
                </button>
            </div>
            <div className="field-stack">
                <label className="field">
                    <span>{'\u5ffd\u7565\u539f\u56e0'}</span>
                    <select value={draft.reason} onChange={(event) => updateDismissDraft(item.stableKey, { reason: event.target.value })}>
                        <option value="">{'\u8bf7\u9009\u62e9\u539f\u56e0'}</option>
                        {SUPERVISOR_DISMISS_REASON_OPTIONS.map((option) => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                        ))}
                    </select>
                </label>
                <label className="field">
                    <span>{'\u624b\u52a8\u5907\u6ce8'}</span>
                    <textarea
                        value={draft.note}
                        onChange={(event) => updateDismissDraft(item.stableKey, { note: event.target.value })}
                        placeholder={'\u53ef\u9009\uff0c\u8bb0\u5f55\u4f60\u4e3a\u4ec0\u4e48\u6682\u65f6\u4e0d\u5904\u7406\u8fd9\u6761\u5efa\u8bae'}
                    />
                </label>
            </div>
            <div className="button-row">
                {renderOperatorActionButtons(operatorActions, (action) => handleSupervisorAction(item, action), supervisorSubmitting, item.actionLabel)}
                <button className="secondary-button" onClick={() => handleSupervisorDismiss(item)} disabled={supervisorSubmitting || !draft.reason}>
                    {supervisorSubmitting ? '\u5904\u7406\u4e2d...' : '\u5ffd\u7565\u5e76\u5199\u5165\u5907\u6ce8'}
                </button>
            </div>
        </div>
    )
}

export function SupervisorDismissedCard({
    item,
    operatorActions,
    recoverySemantics,
    selectedSupervisorKeys,
    toggleSupervisorSelection,
    handleSupervisorUndismiss,
    handleSupervisorTrackingClear,
    handleSupervisorAction,
    renderOperatorActionButtons,
    supervisorSubmitting,
    formatSupervisorTrackingStatus,
    formatSupervisorDismissReason,
    formatTimestampShort,
}) {
    return (
        <div className={`supervisor-card ${item.tone}`}>
            <div className="supervisor-card-header">
                <div className="supervisor-title">
                    <label className="checkbox-row">
                        <input
                            type="checkbox"
                            checked={selectedSupervisorKeys.includes(item.stableKey)}
                            onChange={() => toggleSupervisorSelection(item.stableKey)}
                        />
                        <span>{item.title}</span>
                    </label>
                </div>
                <span className="runtime-badge">{'\u5df2\u5ffd\u7565'}</span>
            </div>
            <div className="tiny">{'\u7c7b\u578b\uff1a'}{item.categoryLabel || item.category || '-'}</div>
            <div className="supervisor-meta">{item.summary}</div>
            <div className="tiny">{item.detail}</div>
            <RecoverySemanticsDetails recoverySemantics={recoverySemantics} />
            {item.trackingStatus ? <div className="tiny">{`\u5904\u7406\u72b6\u6001\uff1a${item.trackingLabel || formatSupervisorTrackingStatus(item.trackingStatus)} / ${formatTimestampShort(item.trackingUpdatedAt)}`}</div> : null}
            {item.trackingNote ? <div className="tiny">{`\u72b6\u6001\u5907\u6ce8\uff1a${item.trackingNote}`}</div> : null}
            {item.linkedTaskId ? <div className="tiny">{`\u5173\u8054\u4efb\u52a1\uff1a${item.linkedTaskId}`}</div> : null}
            {item.linkedChecklistPath ? <div className="tiny">{`\u5173\u8054\u6e05\u5355\uff1a${item.linkedChecklistPath}`}</div> : null}
            <div className="tiny">{'\u5ffd\u7565\u65f6\u95f4\uff1a'}{formatTimestampShort(item.dismissedAt)}</div>
            <div className="tiny">{'\u5ffd\u7565\u539f\u56e0\uff1a'}{formatSupervisorDismissReason(item.dismissalReason)}</div>
            {item.dismissalNote ? <div className="tiny">{'\u624b\u52a8\u5907\u6ce8\uff1a'}{item.dismissalNote}</div> : null}
            <div className="button-row">
                <button className="secondary-button" onClick={() => handleSupervisorUndismiss(item)} disabled={supervisorSubmitting}>
                    {supervisorSubmitting ? '\u5904\u7406\u4e2d...' : '\u6062\u590d\u5230\u5f85\u5904\u7406'}
                </button>
                <button className="secondary-button" onClick={() => handleSupervisorTrackingClear(item)} disabled={supervisorSubmitting || !item.trackingStatus}>
                    {supervisorSubmitting ? '\u5904\u7406\u4e2d...' : '\u6e05\u9664\u72b6\u6001'}
                </button>
                {renderOperatorActionButtons(operatorActions, (action) => handleSupervisorAction(item, action), supervisorSubmitting, item.actionLabel)}
            </div>
        </div>
    )
}
