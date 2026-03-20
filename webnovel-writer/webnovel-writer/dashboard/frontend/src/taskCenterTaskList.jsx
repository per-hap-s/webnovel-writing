import { buildWritingTaskListSummary } from './writingTaskListSummary.js'
import {
    buildRuntimeSummary,
    mapContinuationToneToBadgeTone,
    resolveRuntimeBadgeLabel,
    resolveRuntimeBadgeTone,
    withLiveRuntimeStatus,
} from './taskCenterRuntime.js'

export function TaskCenterTaskList({
    tasks,
    selectedTaskId,
    runtimeNow,
    followupSubmitting,
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
            <div className="panel-title">任务监控</div>
            <div className="task-list">
                {tasks.map((task) => {
                    const liveTask = withLiveRuntimeStatus(task, runtimeNow)
                    const writingSummary = buildWritingTaskListSummary({ task: liveTask })
                    const primaryAction = writingSummary?.primaryAction || null
                    const recommendedLabel = writingSummary?.primaryActionLabel || writingSummary?.nextStep || ''
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
                                            {recommendedLabel ? <span className="tiny task-followup-action">{recommendedLabel}</span> : null}
                                        </div>
                                        <div className="tiny task-followup-summary">{writingSummary.reasonLabel}</div>
                                    </div>
                                ) : null}
                            </button>
                            {writingSummary ? (
                                <div className="task-item-actions">
                                    <button
                                        className={primaryAction ? 'primary-button' : 'secondary-button'}
                                        onClick={(event) => onTaskPrimaryActionClick(event, liveTask, primaryAction)}
                                        disabled={Boolean(primaryAction && (followupSubmitting || primaryAction.disabled))}
                                        title={primaryAction ? (primaryAction.reason || primaryAction.label) : '查看任务'}
                                    >
                                        {primaryAction
                                            ? (followupSubmitting ? '处理中...' : primaryAction.label)
                                            : '查看任务'}
                                    </button>
                                </div>
                            ) : null}
                        </div>
                    )
                })}
                {tasks.length === 0 && <div className="empty-state">暂无任务</div>}
            </div>
        </section>
    )
}
