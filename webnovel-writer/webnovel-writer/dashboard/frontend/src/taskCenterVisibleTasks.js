function parseTaskTimestamp(task) {
    const parsed = Date.parse(String(task?.updated_at || task?.created_at || ''))
    return Number.isFinite(parsed) ? parsed : 0
}

function compareRepresentativePriority(left, right) {
    const leftIsResume = String(left?.task_type || '').trim() === 'resume'
    const rightIsResume = String(right?.task_type || '').trim() === 'resume'
    if (leftIsResume !== rightIsResume) {
        return leftIsResume ? 1 : -1
    }

    const leftTime = parseTaskTimestamp(left)
    const rightTime = parseTaskTimestamp(right)
    if (leftTime !== rightTime) {
        return rightTime - leftTime
    }

    return String(left?.id || '').localeCompare(String(right?.id || ''))
}

function buildResumeGroupLookup(items) {
    const lookup = new Map()

    ;(Array.isArray(items) ? items : []).forEach((task) => {
        const taskId = String(task?.id || '').trim()
        const targetTaskId = String(task?.resume_target_task_id || '').trim()
        if (!targetTaskId) return
        lookup.set(taskId, `resume:${targetTaskId}`)
        lookup.set(targetTaskId, `resume:${targetTaskId}`)
    })

    return lookup
}

function resolveCompletedTaskGroupKey(task, resumeLookup) {
    if (String(task?.status || '').trim() !== 'completed') return ''

    const taskId = String(task?.id || '').trim()
    if (taskId && resumeLookup.has(taskId)) {
        return resumeLookup.get(taskId) || ''
    }

    const rootTaskId = String(task?.root_task_id || '').trim()
    if (rootTaskId) {
        return `root:${rootTaskId}`
    }

    return ''
}

export function buildVisibleTaskCenterTasks(items) {
    const tasks = Array.isArray(items) ? items : []
    const resumeLookup = buildResumeGroupLookup(tasks)
    const representativeByGroup = new Map()

    tasks.forEach((task) => {
        const groupKey = resolveCompletedTaskGroupKey(task, resumeLookup)
        if (!groupKey) return

        const currentRepresentative = representativeByGroup.get(groupKey) || null
        if (!currentRepresentative || compareRepresentativePriority(task, currentRepresentative) < 0) {
            representativeByGroup.set(groupKey, task)
        }
    })

    const representativeIds = new Set(
        [...representativeByGroup.values()]
            .map((task) => task?.id)
            .filter(Boolean),
    )

    return tasks.filter((task) => {
        const groupKey = resolveCompletedTaskGroupKey(task, resumeLookup)
        if (!groupKey) return true
        return representativeIds.has(task.id)
    })
}
