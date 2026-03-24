export function resolveRuntimeBadgeLabel(task) {
    if (task?.artifacts?.plan_blocked) return '待补信息'
    const stepState = task?.runtime_status?.step_state
    if (stepState === 'interrupted') return '已中断'
    if (stepState === 'cancelled') return '已停止'
    if (stepState === 'rejected') return '已拒绝'
    if (stepState === 'retrying') return '重试中'
    if (stepState === 'resuming_writeback') return '回写中'
    if (stepState === 'waiting_approval') return '待审批'
    if (stepState === 'failed') return '已失败'
    if (stepState === 'completed') return '已完成'
    if (stepState === 'running') return '运行中'
    return '待执行'
}

export function resolveRuntimeBadgeTone(task) {
    if (task?.artifacts?.plan_blocked) return 'warning'
    const stepState = task?.runtime_status?.step_state
    if (stepState === 'running') return 'info'
    if (stepState === 'retrying') return 'warning'
    if (stepState === 'resuming_writeback') return 'info'
    if (stepState === 'waiting_approval') return 'warning'
    if (stepState === 'interrupted') return 'warning'
    if (stepState === 'cancelled') return 'warning'
    if (stepState === 'rejected') return 'danger'
    if (stepState === 'failed') return 'danger'
    if (stepState === 'completed') return 'success'
    return 'muted'
}

export function mapContinuationToneToBadgeTone(tone) {
    if (tone === 'success') return 'success'
    if (tone === 'warning') return 'warning'
    if (tone === 'danger') return 'danger'
    return 'muted'
}

export function buildRuntimeSummary(task) {
    if (task?.artifacts?.plan_blocked) return '需先回总览补录规划信息'
    const runtime = task?.runtime_status || {}
    const parts = []
    if (runtime.phase_label) parts.push(runtime.phase_label)
    if (runtime.phase_detail) parts.push(runtime.phase_detail)
    if (runtime.step_state === 'interrupted' || runtime.step_state === 'cancelled' || runtime.step_state === 'rejected') {
        return parts.join(' · ') || resolveRuntimeBadgeLabel(task)
    }
    if (runtime.step_state === 'retrying' && runtime.attempt) {
        parts.push(`第 ${runtime.attempt} 次尝试`)
    } else if (runtime.step_state === 'resuming_writeback') {
        parts.push('审批已通过，正在回写正文和同步项目数据')
    } else if (runtime.step_state === 'running' && runtime.running_seconds >= 0) {
        parts.push(formatRuntimeDuration(runtime.running_seconds))
    } else if (runtime.step_state === 'failed' && runtime.error_code) {
        parts.push(runtime.error_code)
    } else if (runtime.step_state === 'waiting_approval') {
        parts.push(task?.status === 'awaiting_chapter_brief_approval' ? '后续重规划已完成，等待人工确认新简报后开写' : '等待人工批准回写')
    } else if (runtime.step_state === 'completed' && runtime.running_seconds > 0) {
        parts.push(`耗时 ${formatRuntimeDuration(runtime.running_seconds)}`)
    }
    if (!parts.length) return '暂无实时状态'
    return parts.join(' · ')
}

export function isRuntimeActiveTask(task) {
    const stepState = task?.runtime_status?.step_state
    return stepState === 'running' || stepState === 'retrying' || stepState === 'resuming_writeback'
}

export function withLiveRuntimeStatus(task, nowMs) {
    if (!task?.runtime_status || !isRuntimeActiveTask(task)) return task
    const runtime = task.runtime_status
    const runningStartMs = parseTimestampToMs(runtime.step_started_at || runtime.last_activity_at || runtime.last_event_at || task.updated_at)
    const waitingStartMs = parseTimestampToMs(runtime.waiting_since)
    const runningSeconds = Number.isFinite(runningStartMs)
        ? Math.max(0, Math.floor((nowMs - runningStartMs) / 1000))
        : Math.max(0, Number(runtime.running_seconds || 0))
    const waitingSeconds = shouldTickWaiting(runtime) && Number.isFinite(waitingStartMs)
        ? Math.max(0, Math.floor((nowMs - waitingStartMs) / 1000))
        : Math.max(0, Number(runtime.waiting_seconds || 0))
    return {
        ...task,
        runtime_status: {
            ...runtime,
            running_seconds: runningSeconds,
            waiting_seconds: waitingSeconds,
        },
    }
}

function shouldTickWaiting(runtime) {
    return ['llm_request_started', 'request_dispatched', 'awaiting_model_response'].includes(runtime?.last_event_message)
        || Number(runtime?.waiting_seconds || 0) > 0
}

function parseTimestampToMs(value) {
    if (!value) return Number.NaN
    const parsed = new Date(String(value).includes('T') ? String(value) : String(value).replace(' ', 'T'))
    return parsed.getTime()
}

export function formatRuntimeDuration(seconds) {
    const total = Number(seconds || 0)
    if (!Number.isFinite(total) || total < 0) return '-'
    const hours = Math.floor(total / 3600)
    const minutes = Math.floor((total % 3600) / 60)
    const remainSeconds = total % 60
    if (hours > 0) return `${hours}小时${minutes}分${remainSeconds}秒`
    if (minutes > 0) return `${minutes}分${remainSeconds}秒`
    return `${remainSeconds}秒`
}

export function formatTimeoutValue(seconds) {
    const total = Number(seconds || 0)
    if (!Number.isFinite(total) || total <= 0) return '-'
    return `${total} 秒`
}

export function formatCountValue(value, allowZero = false) {
    if (value === null || value === undefined || value === '') return '-'
    const count = Number(value)
    if (!Number.isFinite(count)) return String(value)
    if (!allowZero && count <= 0) return '-'
    return String(count)
}

export function formatRetryableValue(value) {
    if (value === null || value === undefined) return '-'
    return value ? '是' : '否'
}

export function buildEventPayloadTags(payload) {
    const items = []
    const pairs = [
        ['attempt', '尝试'],
        ['retry_count', '重试'],
        ['timeout_seconds', '超时'],
        ['http_status', 'HTTP'],
        ['error_code', '错误码'],
    ]
    pairs.forEach(([key, label]) => {
        const value = payload?.[key]
        if (value === null || value === undefined || value === '') return
        items.push({ label, value: key === 'timeout_seconds' ? `${value} 秒` : String(value) })
    })
    return items
}
