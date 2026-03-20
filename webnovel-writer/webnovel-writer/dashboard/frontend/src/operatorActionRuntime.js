export async function executeOperatorAction({
    action,
    postJSON,
    onOpenTask,
    onTaskCreated,
    onTasksMutated,
}) {
    if (!action || action.disabled || typeof postJSON !== 'function') {
        return { outcome: 'skipped', response: null }
    }

    if (action.kind === 'open-task' || action.kind === 'open-blocked-task') {
        if (action.taskId && typeof onOpenTask === 'function') {
            onOpenTask(action.taskId)
        }
        return { outcome: 'opened', response: null }
    }

    if (action.kind === 'retry-task' || action.kind === 'resume-existing-task') {
        if (!action.taskId) return { outcome: 'skipped', response: null }
        const response = await postJSON(
            `/api/tasks/${action.taskId}/retry`,
            action.resumeFromStep ? { resume_from_step: action.resumeFromStep } : {},
        )
        if (typeof onTasksMutated === 'function') {
            onTasksMutated(response, action)
        }
        if (typeof onOpenTask === 'function') {
            onOpenTask(action.taskId)
        }
        return { outcome: 'retried', response }
    }

    if (action.kind === 'launch-task' && action.taskType && action.payload) {
        const response = await postJSON(`/api/tasks/${action.taskType}`, action.payload)
        if (typeof onTaskCreated === 'function') {
            onTaskCreated(response, action)
        } else if (response?.id && typeof onOpenTask === 'function') {
            onOpenTask(response.id)
        }
        return { outcome: 'launched', response }
    }

    if (action.kind === 'complete-noop') {
        return { outcome: 'noop', response: null }
    }

    return { outcome: 'skipped', response: null }
}
