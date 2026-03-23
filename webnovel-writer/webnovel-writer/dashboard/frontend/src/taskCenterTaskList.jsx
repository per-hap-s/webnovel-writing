import { buildWritingTaskListSummary } from './writingTaskListSummary.js'
import {
    buildRuntimeSummary,
    mapContinuationToneToBadgeTone,
    resolveRuntimeBadgeLabel,
    resolveRuntimeBadgeTone,
    withLiveRuntimeStatus,
} from './taskCenterRuntime.js'

const TASK_CENTER_COPY = {
    viewTask: '查看任务',
    executeNextStep: '执行下一步',
    noNextStep: '当前任务暂无可执行的下一步',
    empty: '暂无任务',
    busy: '处理中...',
}

function buildActionKey(action) {
    if (!action) return ''
    return action.id || `${action.kind}:${action.taskId || action.taskType || action.label || 'action'}`
}

export function TaskCenterTaskList({
    tasks,
    selectedTaskId,
    runtimeNow,
    taskActionState,
    onSelectTask,
    onTaskPrimaryActionClick,
    translateTaskType,
    translateTaskStatus,
    translateStepName,
    resolveTaskStatusLabel,
    resolveCurrentStepLabel,
    resolveTargetLabel,
}) {
    return (
        <section className="panel list-panel">
            <div className="panel-title">任务中心</div>
            <div className="task-list">
                {tasks.map((task) => {
                    const liveTask = withLiveRuntimeStatus(task, runtimeNow)
                    const writingSummary = buildWritingTaskListSummary({ task: liveTask })
                    const primaryAction = writingSummary?.primaryAction || null
                    const actionKey = buildActionKey(primaryAction)
                    const actionPending = Boolean(primaryAction && taskActionState?.pendingActionKey === actionKey)
                    const nextStepLabel = writingSummary?.primaryActionLabel || writingSummary?.nextStep || '当前无下一步'
                    return (
                        <div key={task.id} className={`task-item ${selectedTaskId === task.id ? 'active' : ''}`}>
                            <button className="task-item-main" onClick={() => onSelectTask(task.id)}>
                                <div className="task-item-header">
                                    <div>{translateTaskType(liveTask.task_type)}</div>
                                    <span className={`runtime-badge ${resolveRuntimeBadgeTone(liveTask)}`}>{resolveRuntimeBadgeLabel(liveTask)}</span>
                                </div>
                                <div className="tiny task-target">{resolveTargetLabel ? resolveTargetLabel(liveTask) : (liveTask.runtime_status?.target_label || '-')}</div>
                                <div className="muted">{resolveTaskStatusLabel ? resolveTaskStatusLabel(liveTask) : translateTaskStatus(liveTask.status)}</div>
                                <div className="tiny">{resolveCurrentStepLabel ? resolveCurrentStepLabel(liveTask) : translateStepName(liveTask.current_step || 'idle')}</div>
                                <div className="tiny runtime-summary">{buildRuntimeSummary(liveTask)}</div>
                                {writingSummary ? (
                                    <div className="task-followup">
                                        <div className="task-followup-header">
                                            <span className={`runtime-badge ${mapContinuationToneToBadgeTone(writingSummary.tone)}`}>{writingSummary.continuationLabel}</span>
                                            <span className="tiny task-followup-action">{nextStepLabel}</span>
                                        </div>
                                        <div className="tiny task-followup-summary">{writingSummary.reasonLabel}</div>
                                    </div>
                                ) : null}
                            </button>
                            <div className="task-item-actions">
                                <button className="secondary-button" onClick={() => onSelectTask(task.id)}>{TASK_CENTER_COPY.viewTask}</button>
                                <button
                                    className={primaryAction ? 'primary-button' : 'secondary-button'}
                                    onClick={(event) => onTaskPrimaryActionClick(event, liveTask, primaryAction)}
                                    disabled={!primaryAction || actionPending || primaryAction.disabled}
                                    title={primaryAction ? (primaryAction.reason || primaryAction.label) : TASK_CENTER_COPY.noNextStep}
                                >
                                    {actionPending ? TASK_CENTER_COPY.busy : (primaryAction?.label || TASK_CENTER_COPY.executeNextStep)}
                                </button>
                            </div>
                        </div>
                    )
                })}
                {tasks.length === 0 && <div className="empty-state">{TASK_CENTER_COPY.empty}</div>}
            </div>
        </section>
    )
}
