import {
    AlignmentResultsSection,
    GuardedBatchSection,
    GuardedRunSection,
    NarrativeContractsSection,
    ReviewSummarySection,
    ResumeSection,
    StoryRefreshSection,
    TaskContinuationSection,
} from './taskDetailPanels.jsx'
import { buildTaskContinuationSummary } from './writingContinuation.js'
import { formatTimestampShort } from './dashboardPageCommon.jsx'
import { renderOperatorActionButtons } from './operatorActionButtons.jsx'
import {
    buildEventPayloadTags,
    formatCountValue,
    formatRetryableValue,
    formatRuntimeDuration,
    formatTimeoutValue,
    resolveRuntimeBadgeLabel,
    withLiveRuntimeStatus,
} from './taskCenterRuntime.js'
import { deriveWritingTaskContext } from './writingTaskDerived.js'
import { supportsWritingTaskContinuation } from './writingTaskListSummary.js'

export function TaskCenterTaskDetail({
    tasks,
    selectedTask,
    events,
    runtimeNow,
    actionError,
    canRetryTask,
    canCancelTask,
    cancelSubmitting,
    followupSubmitting,
    onSelectTask,
    onNavigateOverview,
    onPerform,
    onCancelTask,
    onExecuteOperatorAction,
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
    return (
        <section className="panel detail-panel">
            <div className="panel-title">任务详情</div>
            {!selectedTask && <div className="empty-state">请选择任务查看详情</div>}
            {selectedTask && (() => {
                const liveSelectedTask = withLiveRuntimeStatus(selectedTask, runtimeNow)
                const writingContext = deriveWritingTaskContext(liveSelectedTask)
                const {
                    storyPlan,
                    directorBrief,
                    guardedRun,
                    guardedBatchRun,
                    resumeRun,
                    storyAlignment,
                    directorAlignment,
                    storyRefresh,
                    currentStorySlot,
                    operatorActions,
                } = writingContext
                const parentTask = liveSelectedTask?.parent_task_id ? (tasks.find((item) => item.id === liveSelectedTask.parent_task_id) || null) : null
                const rootTask = liveSelectedTask?.root_task_id ? (tasks.find((item) => item.id === liveSelectedTask.root_task_id) || null) : null
                const guardedBatchRuns = Array.isArray(guardedBatchRun?.runs) ? guardedBatchRun.runs : []
                const lastGuardedBatchRun = guardedBatchRuns.length ? guardedBatchRuns[guardedBatchRuns.length - 1] : null
                const lastSuccessfulBatchRun = [...guardedBatchRuns].reverse().find((item) => item?.task_status === 'completed') || null
                const nextRecommendedAction = operatorActions.find((action) => action.variant === 'primary') || operatorActions[0] || null
                const continuationSummary = supportsWritingTaskContinuation(liveSelectedTask)
                    ? buildTaskContinuationSummary({
                        task: liveSelectedTask,
                        storyPlan,
                        directorBrief,
                        storyAlignment,
                        directorAlignment,
                        storyRefresh,
                        guardedRun,
                        guardedBatchRun,
                        resumeRun,
                        operatorActions,
                    })
                    : null
                const canRefreshStoryPlan = Boolean(
                    storyRefresh?.should_refresh
                    && !['queued', 'running', 'awaiting_writeback_approval'].includes(liveSelectedTask.status)
                )

                return (
                    <>
                        <div className="detail-grid">
                            <MetricCard label="状态" value={resolveTaskStatusLabel ? resolveTaskStatusLabel(liveSelectedTask) : translateTaskStatus(liveSelectedTask.status)} />
                            <MetricCard label="任务目标" value={resolveTargetLabel ? resolveTargetLabel(liveSelectedTask) : (liveSelectedTask.runtime_status?.target_label || '-')} />
                            <MetricCard label="当前步骤" value={resolveCurrentStepLabel ? resolveCurrentStepLabel(liveSelectedTask) : translateStepName(liveSelectedTask.current_step || 'idle')} />
                            <MetricCard label="审批" value={resolveApprovalStatusLabel ? resolveApprovalStatusLabel(liveSelectedTask) : (liveSelectedTask.approval_status || '-')} />
                            <MetricCard label="类型" value={translateTaskType(liveSelectedTask.task_type)} />
                        </div>
                        {liveSelectedTask?.artifacts?.plan_blocked ? (
                            <div className="planning-warning">
                                <div className="subsection-title">待补信息</div>
                                <div className="tiny">规划任务已停止，当前输入不足。请先补齐规划信息，再重新运行 plan。</div>
                                <div className="planning-tags">
                                    {(liveSelectedTask.artifacts.blocking_items || []).map((item, index) => (
                                        <span key={`${item.field || item.label}-${index}`} className="planning-tag">{item.label || item.field || '未命名缺失项'}</span>
                                    ))}
                                </div>
                                {onNavigateOverview ? <button className="secondary-button" onClick={onNavigateOverview}>前往总览补录</button> : null}
                            </div>
                        ) : null}
                        <div className="subsection">
                            <div className="subsection-title">实时运行状态</div>
                            <div className="detail-grid">
                                <MetricCard label="当前阶段" value={liveSelectedTask.runtime_status?.phase_label || (resolveCurrentStepLabel ? resolveCurrentStepLabel(liveSelectedTask) : translateStepName(liveSelectedTask.current_step || 'idle'))} />
                                <MetricCard label="任务目标" value={liveSelectedTask.runtime_status?.target_label || (resolveTargetLabel ? resolveTargetLabel(liveSelectedTask) : '-')} />
                                <MetricCard label="阶段说明" value={liveSelectedTask.runtime_status?.phase_detail || '暂无'} />
                                <MetricCard label="运行状态" value={resolveRuntimeBadgeLabel(liveSelectedTask)} />
                                <MetricCard label="已运行时长" value={formatRuntimeDuration(liveSelectedTask.runtime_status?.running_seconds)} />
                                <MetricCard label="已等待时长" value={formatRuntimeDuration(liveSelectedTask.runtime_status?.waiting_seconds)} />
                                <MetricCard label="当前尝试" value={formatCountValue(liveSelectedTask.runtime_status?.attempt)} />
                                <MetricCard label="重试次数" value={formatCountValue(liveSelectedTask.runtime_status?.retry_count, true)} />
                                <MetricCard label="超时预算" value={formatTimeoutValue(liveSelectedTask.runtime_status?.timeout_seconds)} />
                                <MetricCard label="步骤开始于" value={formatTimestampShort(liveSelectedTask.runtime_status?.step_started_at || '-')} />
                                <MetricCard label="等待开始于" value={formatTimestampShort(liveSelectedTask.runtime_status?.waiting_since || '-')} />
                                <MetricCard label="最近事件" value={liveSelectedTask.runtime_status?.last_event_label || '暂无'} />
                                <MetricCard label="最近更新时间" value={formatTimestampShort(liveSelectedTask.runtime_status?.last_event_at || liveSelectedTask.updated_at || '-')} />
                                <MetricCard label="最近活动" value={formatTimestampShort(liveSelectedTask.runtime_status?.last_activity_at || '-')} />
                                <MetricCard label="最近一次有效活动" value={formatTimestampShort(liveSelectedTask.runtime_status?.last_non_heartbeat_activity_at || '-')} />
                                <MetricCard label="错误码" value={liveSelectedTask.runtime_status?.error_code || '-'} />
                                <MetricCard label="HTTP 状态" value={liveSelectedTask.runtime_status?.http_status || '-'} />
                                <MetricCard label="是否可重试" value={formatRetryableValue(liveSelectedTask.runtime_status?.retryable)} />
                            </div>
                        </div>
                        {(liveSelectedTask.parent_task_id || liveSelectedTask.trigger_source || liveSelectedTask.root_task_id) ? (
                            <div className="subsection">
                                <div className="subsection-title">任务链路</div>
                                <div className="detail-grid">
                                    <MetricCard label="触发来源" value={liveSelectedTask.trigger_source || '-'} />
                                    <MetricCard label="父任务" value={liveSelectedTask.parent_task_id || '-'} />
                                    <MetricCard label="根任务" value={liveSelectedTask.root_task_id || '-'} />
                                    <MetricCard label="父步骤" value={liveSelectedTask.parent_step_name ? translateStepName(liveSelectedTask.parent_step_name) : '-'} />
                                </div>
                                <div className="button-row">
                                    {parentTask ? <button className="secondary-button" onClick={() => onSelectTask(parentTask.id)}>查看父任务</button> : null}
                                    {rootTask && rootTask.id !== parentTask?.id ? <button className="secondary-button" onClick={() => onSelectTask(rootTask.id)}>查看根任务</button> : null}
                                </div>
                            </div>
                        ) : null}
                        {continuationSummary ? (
                            <TaskContinuationSection
                                continuationSummary={continuationSummary}
                                operatorActions={operatorActions}
                                renderOperatorActionButtons={(actions) => renderOperatorActionButtons(actions, onExecuteOperatorAction, followupSubmitting, '', '创建中...')}
                                MetricCard={MetricCard}
                            />
                        ) : null}
                        <NarrativeContractsSection
                            storyPlan={storyPlan}
                            directorBrief={directorBrief}
                            currentStorySlot={currentStorySlot}
                            MetricCard={MetricCard}
                        />
                        <AlignmentResultsSection storyAlignment={storyAlignment} directorAlignment={directorAlignment} />
                        <StoryRefreshSection
                            storyRefresh={storyRefresh}
                            canRefreshStoryPlan={canRefreshStoryPlan}
                            onRetryStory={() => onPerform(`/api/tasks/${liveSelectedTask.id}/retry`, { resume_from_step: storyRefresh?.recommended_resume_from || 'story-director' })}
                            MetricCard={MetricCard}
                        />
                        <ReviewSummarySection
                            summary={guardedRun?.review_summary || guardedBatchRun?.review_summary}
                            MetricCard={MetricCard}
                        />
                        <GuardedRunSection
                            guardedRun={guardedRun}
                            MetricCard={MetricCard}
                            translateStepName={translateStepName}
                            translateTaskStatus={translateTaskStatus}
                        />
                        <GuardedBatchSection
                            guardedBatchRun={guardedBatchRun}
                            MetricCard={MetricCard}
                            translateStepName={translateStepName}
                            translateTaskStatus={translateTaskStatus}
                            onSelectTask={onSelectTask}
                            lastSuccessfulBatchRun={lastSuccessfulBatchRun}
                            lastGuardedBatchRun={lastGuardedBatchRun}
                            nextRecommendedAction={nextRecommendedAction}
                        />
                        <ResumeSection
                            resumeRun={resumeRun}
                            MetricCard={MetricCard}
                            translateStepName={translateStepName}
                        />
                        <div className="button-row">
                            {canRetryTask ? <button className="secondary-button" onClick={() => onPerform(`/api/tasks/${liveSelectedTask.id}/retry`, {})}>重试</button> : null}
                            {canCancelTask ? (
                                <button className="secondary-button" onClick={() => onCancelTask(liveSelectedTask)} disabled={cancelSubmitting}>
                                    {cancelSubmitting ? '停止中...' : '停止任务'}
                                </button>
                            ) : null}
                            {liveSelectedTask.status === 'awaiting_writeback_approval' && (
                                <>
                                    <button className="primary-button" onClick={() => onPerform('/api/review/approve', { task_id: liveSelectedTask.id, reason: '由仪表盘批准回写' })}>批准回写</button>
                                    <button className="danger-button" onClick={() => onPerform('/api/review/reject', { task_id: liveSelectedTask.id, reason: '由仪表盘拒绝回写' })}>拒绝回写</button>
                                </>
                            )}
                        </div>
                        <ErrorNotice error={actionError} />
                        <ErrorNotice
                            error={liveSelectedTask.error || null}
                            title={
                                liveSelectedTask.status === 'interrupted'
                                    ? '任务中断原因'
                                    : liveSelectedTask.status === 'rejected'
                                        ? '任务拒绝原因'
                                        : '任务失败原因'
                            }
                        />
                        <div className="subsection">
                            <div className="subsection-title">步骤输出</div>
                            <details className="raw-output-details">
                                <summary>查看原始结果 / 调试信息</summary>
                                <pre className="code-block">{JSON.stringify(liveSelectedTask.artifacts?.step_results || {}, null, 2)}</pre>
                            </details>
                        </div>
                        <div className="subsection">
                            <div className="subsection-title">事件流</div>
                            <div className="event-list">
                                {events.map((event) => (
                                    <div key={event.id} className={`event-card ${event.level}`}>
                                        <div className="event-meta">[{translateEventLevel(event.level)}] {translateStepName(event.step_name || 'task')} · {formatTimestampShort(event.timestamp)}</div>
                                        <div>{translateEventMessage(event.message)}</div>
                                        <div className="event-payload-row">
                                            {buildEventPayloadTags(event.payload || {}).map((tag) => (
                                                <span key={`${event.id}-${tag.label}`} className="event-payload-tag">{tag.label}：{tag.value}</span>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </>
                )
            })()}
        </section>
    )
}
