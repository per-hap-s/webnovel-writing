import { useEffect, useMemo, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'
import { executeOperatorAction as executeRuntimeOperatorAction } from './operatorActionRuntime.js'
import { isRuntimeActiveTask } from './taskCenterRuntime.js'
import { TaskCenterTaskDetail } from './taskCenterTaskDetail.jsx'
import { TaskCenterTaskList } from './taskCenterTaskList.jsx'

function buildPendingActionKey(action) {
    if (!action) return ''
    return action.id || `${action.kind}:${action.taskId || action.taskType || action.label || 'action'}`
}

function buildRequestActionKey(path, body = {}) {
    const taskId = body?.task_id || body?.id || ''
    return `${path}:${taskId || 'request'}`
}

export function TaskCenterPageSection({
    tasks,
    selectedTask,
    selectedTaskId,
    currentProjectRoot,
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
    const [detailTask, setDetailTask] = useState(selectedTask || null)
    const [events, setEvents] = useState([])
    const [actionError, setActionError] = useState(null)
    const [runtimeNow, setRuntimeNow] = useState(() => Date.now())
    const [pendingActionKey, setPendingActionKey] = useState('')
    const liveSelectedTask = detailTask || selectedTask || null
    const requestParams = useMemo(
        () => (currentProjectRoot ? { project_root: currentProjectRoot } : {}),
        [currentProjectRoot],
    )
    const requestOptions = currentProjectRoot ? { params: requestParams } : undefined
    const selectedTaskSnapshotKey = selectedTask ? [
        selectedTask.id || '',
        selectedTask.status || '',
        selectedTask.current_step || '',
        selectedTask.approval_status || '',
        selectedTask.list_priority || '',
        selectedTask.runtime_status?.step_state || '',
        selectedTask.runtime_status?.phase_label || '',
        selectedTask.runtime_status?.error_code || '',
        selectedTask.runtime_status?.suggested_resume_step || '',
    ].join('|') : ''
    const canRetryTask = ['failed', 'interrupted'].includes(liveSelectedTask?.status) && liveSelectedTask?.runtime_status?.retryable !== false
    const canCancelTask = ['queued', 'running', 'awaiting_chapter_brief_approval', 'awaiting_writeback_approval', 'retrying', 'resuming_writeback'].includes(liveSelectedTask?.status)

    useEffect(() => {
        if (!tasks.some(isRuntimeActiveTask) && !isRuntimeActiveTask(liveSelectedTask)) return undefined
        setRuntimeNow(Date.now())
        const timer = window.setInterval(() => setRuntimeNow(Date.now()), 1000)
        return () => window.clearInterval(timer)
    }, [tasks, liveSelectedTask])

    useEffect(() => {
        let cancelled = false
        if (!selectedTaskId) {
            setDetailTask(null)
            setEvents([])
            setActionError(null)
            return () => {}
        }
        setDetailTask(selectedTask || null)
        setEvents([])
        setActionError(null)
        fetchJSON(`/api/tasks/${selectedTaskId}/detail`, requestParams)
            .then((payload) => {
                if (cancelled) return
                setDetailTask(payload?.task || null)
                setEvents(Array.isArray(payload?.events) ? payload.events : [])
            })
            .catch((error) => {
                if (cancelled) return
                setDetailTask(selectedTask || null)
                setEvents([])
                setActionError(normalizeError(error))
            })
        return () => {
            cancelled = true
        }
    }, [requestParams, selectedTaskId, selectedTaskSnapshotKey])

    const taskActionState = useMemo(() => ({ pendingActionKey }), [pendingActionKey])

    async function perform(path, body, options = {}) {
        const actionKey = options.actionKey || buildRequestActionKey(path, body)
        setPendingActionKey(actionKey)
        setActionError(null)
        try {
            const response = requestOptions
                ? await postJSON(path, body, requestOptions)
                : await postJSON(path, body)
            if (options.focusTaskId) {
                onSelectTask(options.focusTaskId)
            }
            onMutated()
            return response
        } catch (err) {
            setActionError(normalizeError(err))
            return null
        } finally {
            setPendingActionKey('')
        }
    }

    async function executeOperatorAction(action) {
        if (!action || action.disabled) return
        const actionKey = buildPendingActionKey(action)
        setPendingActionKey(actionKey)
        setActionError(null)
        try {
            await executeRuntimeOperatorAction({
                action,
                postJSON: (path, body = {}, options = {}) => {
                    if (!currentProjectRoot) {
                        return postJSON(path, body, options)
                    }
                    return postJSON(path, body, {
                        ...options,
                        params: {
                            ...(options?.params || {}),
                            ...requestParams,
                        },
                    })
                },
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
            setPendingActionKey('')
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
        await perform(
            `/api/tasks/${task.id}/cancel`,
            { reason: '由仪表盘手动停止任务' },
            { actionKey: `cancel:${task.id}`, focusTaskId: task.id },
        )
    }

    return (
        <div className="split-layout">
            <TaskCenterTaskList
                tasks={tasks}
                selectedTaskId={selectedTaskId || null}
                runtimeNow={runtimeNow}
                taskActionState={taskActionState}
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
                selectedTask={liveSelectedTask}
                events={events}
                runtimeNow={runtimeNow}
                actionError={actionError}
                canRetryTask={canRetryTask}
                canCancelTask={canCancelTask}
                pendingActionKey={pendingActionKey}
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
