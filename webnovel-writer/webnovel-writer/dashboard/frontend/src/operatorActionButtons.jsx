export function renderOperatorActionButtons(
    actions,
    onAction,
    submitting,
    fallbackLabel = '',
    submittingLabel = '处理中...',
    defaultLabel = '执行操作',
) {
    const normalizedActions = Array.isArray(actions) ? actions.filter(Boolean) : []
    if (!normalizedActions.length) {
        return fallbackLabel ? [(
            <button key={`operator-fallback:${fallbackLabel}`} className="secondary-button" disabled>
                {fallbackLabel}
            </button>
        )] : []
    }
    return normalizedActions.map((action) => (
        <button
            key={action.id || `${action.kind}:${action.taskId || action.taskType || action.label}`}
            className={action.variant === 'secondary' ? 'secondary-button' : 'primary-button'}
            onClick={() => onAction?.(action)}
            disabled={Boolean(submitting || action.disabled)}
            title={action.reason || action.label || defaultLabel}
        >
            {submitting ? submittingLabel : (action.label || fallbackLabel || defaultLabel)}
        </button>
    ))
}
