import { useEffect, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'
import { executeOperatorAction as executeRuntimeOperatorAction } from './operatorActionRuntime.js'
import { isRuntimeActiveTask } from './taskCenterRuntime.js'
import { TaskCenterTaskDetail } from './taskCenterTaskDetail.jsx'
import { TaskCenterTaskList } from './taskCenterTaskList.jsx'

export function TaskCenterPageSection({
    tasks,
    selectedTask,
    onSelectTask,
    onMutated,
    onNavigateOverview,
    ErrorNotice,
    MetricCard,
    translateTaskType,
    translateTaskStatus,
    translateStepName,
    translateEventLevel,
    translateEventMessage,
    resolveTaskStatusLabel,
    resolveCurrentStepLabel,
    resolveApprovalStatusLabel,
    resolveTargetLabel,
}) {
    const [events, setEvents] = useState([])
    const [actionError, setActionError] = useState(null)
    const [runtimeNow, setRuntimeNow] = useState(() => Date.now())
    const [cancelSubmitting, setCancelSubmitting] = useState(false)
    const [followupSubmitting, setFollowupSubmitting] = useState(false)
    const canRetryTask = ['failed', 'interrupted'].includes(selectedTask?.status) && selectedTask?.runtime_status?.retryable !== false
    const canCancelTask = ['queued', 'running', 'awaiting_writeback_approval'].includes(selectedTask?.status)

    useEffect(() => {
        if (!tasks.some(isRuntimeActiveTask)) return undefined
        setRuntimeNow(Date.now())
        const timer = window.setInterval(() => setRuntimeNow(Date.now()), 1000)
        return () => window.clearInterval(timer)
    }, [tasks])

    useEffect(() => {
        if (!selectedTask?.id) return
        fetchJSON(`/api/tasks/${selectedTask.id}/events`).then(setEvents).catch(() => setEvents([]))
    }, [selectedTask?.id, selectedTask?.updated_at])

    async function perform(path, body) {
        setActionError(null)
        try {
            const response = await postJSON(path, body)
            onMutated()
            return response
        } catch (err) {
            setActionError(normalizeError(err))
            return null
        }
    }

    async function executeOperatorAction(action) {
        if (!action || followupSubmitting || action.disabled) return
        const isLaunchAction = action.kind === 'launch-task'
        if (isLaunchAction) {
            setFollowupSubmitting(true)
        }
        setActionError(null)
        try {
            await executeRuntimeOperatorAction({
                action,
                postJSON,
                onOpenTask: onSelectTask,
                onTasksMutated: () => onMutated(),
                onTaskCreated: (response) => {
                    if (response?.id) onSelectTask(response.id)
                    onMutated()
                },
            })
        } catch (err) {
            setActionError(normalizeError(err))
        } finally {
            if (isLaunchAction) {
                setFollowupSubmitting(false)
            }
        }
    }

    function handleTaskPrimaryActionClick(event, task, action) {
        event.stopPropagation()
        if (action) {
            executeOperatorAction(action)
            return
        }
        onSelectTask(task.id)
    }

    async function cancelTask(task) {
        if (!task?.id || !canCancelTask) return
        setCancelSubmitting(true)
        setActionError(null)
        try {
            await postJSON(`/api/tasks/${task.id}/cancel`, { reason: '由仪表盘手动停止任务' })
            onMutated()
        } catch (err) {
            const normalized = normalizeError(err)
            if (normalized.statusCode === 404 || normalized.statusCode === 405) {
                setActionError({
                    code: 'TASK_CANCEL_UNAVAILABLE',
                    displayMessage: '当前后端还未提供“停止任务”接口。',
                    rawMessage: normalized.rawMessage || normalized.displayMessage,
                    details: normalized.details,
                    statusCode: normalized.statusCode,
                })
            } else {
                setActionError(normalized)
            }
        } finally {
            setCancelSubmitting(false)
        }
    }

    return (
        <div className="split-layout">
            <TaskCenterTaskList
                tasks={tasks}
                selectedTaskId={selectedTask?.id || null}
                runtimeNow={runtimeNow}
                followupSubmitting={followupSubmitting}
                onSelectTask={onSelectTask}
                onTaskPrimaryActionClick={handleTaskPrimaryActionClick}
                translateTaskType={translateTaskType}
                translateTaskStatus={translateTaskStatus}
                translateStepName={translateStepName}
                resolveTaskStatusLabel={resolveTaskStatusLabel}
                resolveCurrentStepLabel={resolveCurrentStepLabel}
                resolveTargetLabel={resolveTargetLabel}
            />
            <TaskCenterTaskDetail
                tasks={tasks}
                selectedTask={selectedTask}
                events={events}
                runtimeNow={runtimeNow}
                actionError={actionError}
                canRetryTask={canRetryTask}
                canCancelTask={canCancelTask}
                cancelSubmitting={cancelSubmitting}
                followupSubmitting={followupSubmitting}
                onSelectTask={onSelectTask}
                onNavigateOverview={onNavigateOverview}
                onPerform={perform}
                onCancelTask={cancelTask}
                onExecuteOperatorAction={executeOperatorAction}
                ErrorNotice={ErrorNotice}
                MetricCard={MetricCard}
                translateTaskType={translateTaskType}
                translateTaskStatus={translateTaskStatus}
                translateStepName={translateStepName}
                translateEventLevel={translateEventLevel}
                translateEventMessage={translateEventMessage}
                resolveTaskStatusLabel={resolveTaskStatusLabel}
                resolveCurrentStepLabel={resolveCurrentStepLabel}
                resolveApprovalStatusLabel={resolveApprovalStatusLabel}
                resolveTargetLabel={resolveTargetLabel}
            />
        </div>
    )
}
