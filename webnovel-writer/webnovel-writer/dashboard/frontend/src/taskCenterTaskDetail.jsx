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
import { normalizeOperatorAction } from './operatorAction.js'
import { supportsWritingTaskContinuation } from './writingTaskListSummary.js'

function buildActionKey(action) {
    if (!action) return ''
    return action.id || `${action.kind}:${action.taskId || action.taskType || action.label || 'action'}`
}

function buildRequestActionKey(path, body = {}) {
    const taskId = body?.task_id || body?.id || ''
    return `${path}:${taskId || 'request'}`
}

function resolveRepairWritebackLabel(candidate) {
    const action = candidate?.operator_action?.payload || candidate?.operatorAction?.payload || {}
    return action?.require_manual_approval ? '需要人工确认后回写' : '将自动回写正文'
}

function ActionButton({ className, onClick, disabled, loading, children, loadingLabel }) {
    return (
        <button className={className} onClick={onClick} disabled={disabled}>
            {loading ? (loadingLabel || '处理中...') : children}
        </button>
    )
}

export function TaskCenterTaskDetail({
    tasks,
    selectedTask,
    events,
    runtimeNow,
    actionError,
    canRetryTask,
    canCancelTask,
    pendingActionKey,
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
            {!selectedTask && <div className="empty-state">请选择一个任务查看详情</div>}
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
                const primaryAction = operatorActions.find((action) => action.variant === 'primary') || operatorActions[0] || null
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
                    && !['queued', 'running', 'awaiting_writeback_approval', 'retrying', 'resuming_writeback'].includes(liveSelectedTask.status),
                )
                const reviewSummary = guardedRun?.review_summary || guardedBatchRun?.review_summary || liveSelectedTask.artifacts?.review_summary || null
                const repairCandidates = Array.isArray(reviewSummary?.repair_candidates) ? reviewSummary.repair_candidates : []
                const blockingItems = Array.isArray(liveSelectedTask?.artifacts?.blocking_items) ? liveSelectedTask.artifacts.blocking_items : []
                const primaryActionKey = buildActionKey(primaryAction)
                const retryActionKey = buildRequestActionKey(`/api/tasks/${liveSelectedTask.id}/retry`)
                const chapter = Number(
                    liveSelectedTask?.request?.chapter
                    || liveSelectedTask?.artifacts?.step_results?.['chapter-director']?.structured_output?.chapter
                    || 0,
                )
                const briefApproveActionKey = buildRequestActionKey(`/api/chapters/${chapter}/brief/approve`)
                const briefRejectActionKey = buildRequestActionKey(`/api/chapters/${chapter}/brief/reject`)
                const approveActionKey = buildRequestActionKey('/api/review/approve', { task_id: liveSelectedTask.id })
                const rejectActionKey = buildRequestActionKey('/api/review/reject', { task_id: liveSelectedTask.id })
                const cancelActionKey = `cancel:${liveSelectedTask.id}`

                return (
                    <>
                        <div className="detail-grid">
                            <MetricCard label="状态" value={resolveTaskStatusLabel ? resolveTaskStatusLabel(liveSelectedTask) : translateTaskStatus(liveSelectedTask.status)} />
                            <MetricCard label="目标" value={resolveTargetLabel ? resolveTargetLabel(liveSelectedTask) : (liveSelectedTask.runtime_status?.target_label || '-')} />
                            <MetricCard label="当前阶段" value={resolveCurrentStepLabel ? resolveCurrentStepLabel(liveSelectedTask) : translateStepName(liveSelectedTask.current_step || 'idle')} />
                            <MetricCard label="确认状态" value={resolveApprovalStatusLabel ? resolveApprovalStatusLabel(liveSelectedTask) : (liveSelectedTask.approval_status || '-')} />
                            <MetricCard label="任务类型" value={translateTaskType(liveSelectedTask.task_type)} />
                            <MetricCard label="实时运行" value={resolveRuntimeBadgeLabel(liveSelectedTask)} />
                        </div>

                        <div className="planning-warning detail-action-bar">
                            <div className="subsection-title">首要动作</div>
                            <div className="button-row">
                                <ActionButton className="secondary-button" onClick={() => onSelectTask(liveSelectedTask.id)} disabled={false}>
                                    查看任务
                                </ActionButton>
                                {primaryAction ? (
                                    <ActionButton
                                        className="primary-button"
                                        onClick={() => onExecuteOperatorAction(primaryAction)}
                                        disabled={Boolean(primaryAction.disabled || pendingActionKey)}
                                        loading={pendingActionKey === primaryActionKey}
                                    >
                                        {primaryAction.label || '执行下一步'}
                                    </ActionButton>
                                ) : null}
                                {canRetryTask ? (
                                    <ActionButton
                                        className="secondary-button"
                                        onClick={() => onPerform(`/api/tasks/${liveSelectedTask.id}/retry`, {}, { actionKey: retryActionKey, focusTaskId: liveSelectedTask.id })}
                                        disabled={Boolean(pendingActionKey)}
                                        loading={pendingActionKey === retryActionKey}
                                    >
                                        按当前阶段重跑
                                    </ActionButton>
                                ) : null}
                                {liveSelectedTask.status === 'awaiting_chapter_brief_approval' && chapter > 0 ? (
                                    <>
                                        <ActionButton
                                            className="primary-button"
                                            onClick={() => onPerform(
                                                `/api/chapters/${chapter}/brief/approve`,
                                                { reason: '由仪表盘确认新简报并开写' },
                                                { actionKey: briefApproveActionKey, focusTaskId: liveSelectedTask.id },
                                            )}
                                            disabled={Boolean(pendingActionKey)}
                                            loading={pendingActionKey === briefApproveActionKey}
                                        >
                                            确认新简报并开写
                                        </ActionButton>
                                        <ActionButton
                                            className="danger-button"
                                            onClick={() => onPerform(
                                                `/api/chapters/${chapter}/brief/reject`,
                                                { reason: '由仪表盘驳回并重做新简报' },
                                                { actionKey: briefRejectActionKey, focusTaskId: liveSelectedTask.id },
                                            )}
                                            disabled={Boolean(pendingActionKey)}
                                            loading={pendingActionKey === briefRejectActionKey}
                                        >
                                            驳回并重做新简报
                                        </ActionButton>
                                    </>
                                ) : null}
                                {liveSelectedTask.status === 'awaiting_writeback_approval' ? (
                                    <>
                                        <ActionButton
                                            className="primary-button"
                                            onClick={() => onPerform('/api/review/approve', { task_id: liveSelectedTask.id, reason: '由仪表盘批准回写' }, { actionKey: approveActionKey, focusTaskId: liveSelectedTask.id })}
                                            disabled={Boolean(pendingActionKey)}
                                            loading={pendingActionKey === approveActionKey}
                                        >
                                            批准回写
                                        </ActionButton>
                                        <ActionButton
                                            className="danger-button"
                                            onClick={() => onPerform('/api/review/reject', { task_id: liveSelectedTask.id, reason: '由仪表盘拒绝回写' }, { actionKey: rejectActionKey, focusTaskId: liveSelectedTask.id })}
                                            disabled={Boolean(pendingActionKey)}
                                            loading={pendingActionKey === rejectActionKey}
                                        >
                                            拒绝回写
                                        </ActionButton>
                                    </>
                                ) : null}
                                {canCancelTask ? (
                                    <ActionButton
                                        className="secondary-button"
                                        onClick={() => onCancelTask(liveSelectedTask)}
                                        disabled={Boolean(pendingActionKey)}
                                        loading={pendingActionKey === cancelActionKey}
                                        loadingLabel="正在停止..."
                                    >
                                        停止任务
                                    </ActionButton>
                                ) : null}
                                {parentTask ? <ActionButton className="secondary-button" onClick={() => onSelectTask(parentTask.id)}>查看父任务</ActionButton> : null}
                                {rootTask && rootTask.id !== parentTask?.id ? <ActionButton className="secondary-button" onClick={() => onSelectTask(rootTask.id)}>查看根任务</ActionButton> : null}
                            </div>
                        </div>

                        {liveSelectedTask?.artifacts?.plan_blocked ? (
                            <div className="planning-warning">
                                <div className="subsection-title">当前阻断原因</div>
                                <div className="tiny">规划任务已停止，当前输入不足。请先补齐规划信息，再重新运行规划任务。</div>
                                {blockingItems.length ? (
                                    <div className="alignment-list">
                                        {blockingItems.map((item, index) => (
                                            <div key={`${item.field || item.label || 'blocking'}-${index}`} className="alignment-chip missed">
                                                {item.label || item.field || '待补信息'}
                                            </div>
                                        ))}
                                    </div>
                                ) : null}
                                {onNavigateOverview ? <div className="button-row"><button className="secondary-button" onClick={onNavigateOverview}>前往项目总览</button></div> : null}
                            </div>
                        ) : null}

                        {continuationSummary ? (
                            <TaskContinuationSection
                                continuationSummary={continuationSummary}
                                operatorActions={[]}
                                renderOperatorActionButtons={() => []}
                                MetricCard={MetricCard}
                            />
                        ) : null}

                        <ReviewSummarySection summary={reviewSummary} MetricCard={MetricCard} />

                        {repairCandidates.length ? (
                            <div className="subsection">
                                <div className="subsection-title">可自动处理的问题</div>
                                <div className="summary-grid">
                                    {repairCandidates.slice(0, 6).map((candidate, index) => {
                                        const action = normalizeOperatorAction(candidate.operator_action || candidate.operatorAction || null)
                                        const actionKey = buildActionKey(action)
                                        return (
                                            <div key={`${candidate.issue_title || index}-${index}`} className="summary-card">
                                                <div className="summary-card-title">{candidate.issue_title || '待处理问题'}</div>
                                                <div className="summary-card-meta">{candidate.chapter ? `影响章节：第 ${candidate.chapter} 章` : '影响章节：未定位'}</div>
                                                <div className="summary-card-meta">{resolveRepairWritebackLabel(candidate)}</div>
                                                <div className="tiny">{candidate.rewrite_goal || candidate.reason || '当前未提供可直接执行的处理建议。'}</div>
                                                {action ? (
                                                    <div className="button-row">
                                                        <ActionButton
                                                            className="primary-button"
                                                            onClick={() => onExecuteOperatorAction(action)}
                                                            disabled={Boolean(action.disabled || pendingActionKey)}
                                                            loading={pendingActionKey === actionKey}
                                                        >
                                                            {action.label || '创建局部修稿任务'}
                                                        </ActionButton>
                                                    </div>
                                                ) : null}
                                            </div>
                                        )
                                    })}
                                </div>
                            </div>
                        ) : null}

                        <StoryRefreshSection
                            storyRefresh={storyRefresh}
                            canRefreshStoryPlan={canRefreshStoryPlan}
                            onRetryStory={() => onPerform(
                                `/api/tasks/${liveSelectedTask.id}/retry`,
                                { resume_from_step: storyRefresh?.recommended_resume_from || 'story-director' },
                                {
                                    actionKey: buildRequestActionKey(`/api/tasks/${liveSelectedTask.id}/retry`, { task_id: liveSelectedTask.id, resume_from_step: storyRefresh?.recommended_resume_from || 'story-director' }),
                                    focusTaskId: liveSelectedTask.id,
                                },
                            )}
                            MetricCard={MetricCard}
                        />

                        <details className="raw-output-details">
                            <summary>高级诊断信息</summary>
                            <div className="subsection">
                                <div className="subsection-title">运行状态</div>
                                <div className="detail-grid">
                                    <MetricCard label="阶段说明" value={liveSelectedTask.runtime_status?.phase_detail || '暂无'} />
                                    <MetricCard label="已运行时长" value={formatRuntimeDuration(liveSelectedTask.runtime_status?.running_seconds)} />
                                    <MetricCard label="已等待时长" value={formatRuntimeDuration(liveSelectedTask.runtime_status?.waiting_seconds)} />
                                    <MetricCard label="当前尝试" value={formatCountValue(liveSelectedTask.runtime_status?.attempt)} />
                                    <MetricCard label="重试次数" value={formatCountValue(liveSelectedTask.runtime_status?.retry_count, true)} />
                                    <MetricCard label="超时预算" value={formatTimeoutValue(liveSelectedTask.runtime_status?.timeout_seconds)} />
                                    <MetricCard label="最近更新时间" value={formatTimestampShort(liveSelectedTask.runtime_status?.last_event_at || liveSelectedTask.updated_at || '-')} />
                                    <MetricCard label="是否可重试" value={formatRetryableValue(liveSelectedTask.runtime_status?.retryable)} />
                                </div>
                            </div>

                            <NarrativeContractsSection
                                storyPlan={storyPlan}
                                directorBrief={directorBrief}
                                currentStorySlot={currentStorySlot}
                                MetricCard={MetricCard}
                            />
                            <AlignmentResultsSection storyAlignment={storyAlignment} directorAlignment={directorAlignment} />
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
                                nextRecommendedAction={primaryAction}
                            />
                            <ResumeSection
                                resumeRun={resumeRun}
                                MetricCard={MetricCard}
                                translateStepName={translateStepName}
                            />
                            <div className="subsection">
                                <div className="subsection-title">原始步骤输出</div>
                                <pre className="code-block">{JSON.stringify(liveSelectedTask.artifacts?.step_results || {}, null, 2)}</pre>
                            </div>
                            <div className="subsection">
                                <div className="subsection-title">事件流</div>
                                <div className="event-list">
                                    {events.map((event) => (
                                        <div key={event.id} className={`event-card ${event.level}`}>
                                            <div className="event-meta">[{translateEventLevel(event.level)}] {translateStepName(event.step_name || 'task')} / {formatTimestampShort(event.timestamp)}</div>
                                            <div>{translateEventMessage(event.message)}</div>
                                            <div className="event-payload-row">
                                                {buildEventPayloadTags(event.payload || {}).map((tag) => (
                                                    <span key={`${event.id}-${tag.label}`} className="event-payload-tag">{`${tag.label}：${tag.value}`}</span>
                                                ))}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </details>

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
                    </>
                )
            })()}
        </section>
    )
}
