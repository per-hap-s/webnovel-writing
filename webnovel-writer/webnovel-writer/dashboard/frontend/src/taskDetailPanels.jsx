function renderTagBlock(label, items) {
    if (!Array.isArray(items) || items.length === 0) return null
    return (
        <div>
            <div className="tiny">{label}</div>
            <div className="planning-tags">
                {items.map((item) => (
                    <span key={`${label}-${item}`} className="planning-tag">{item}</span>
                ))}
            </div>
        </div>
    )
}

function AlignmentCard({ title, alignment }) {
    return (
        <div className="summary-card">
            <div className="summary-card-title">{title}</div>
            <div className="alignment-section">
                <div className="tiny">已满足</div>
                <div className="alignment-list">
                    {alignment.satisfied.length ? alignment.satisfied.map((item) => (
                        <div key={`s-${item}`} className="alignment-chip satisfied">{item}</div>
                    )) : <div className="tiny">无</div>}
                </div>
            </div>
            <div className="alignment-section">
                <div className="tiny">已延期</div>
                <div className="alignment-list">
                    {alignment.deferred.length ? alignment.deferred.map((item) => (
                        <div key={`d-${item}`} className="alignment-chip deferred">{item}</div>
                    )) : <div className="tiny">无</div>}
                </div>
            </div>
            <div className="alignment-section">
                <div className="tiny">未满足</div>
                <div className="alignment-list">
                    {alignment.missed.length ? alignment.missed.map((item) => (
                        <div key={`m-${item}`} className="alignment-chip missed">{item}</div>
                    )) : <div className="tiny">无</div>}
                </div>
            </div>
        </div>
    )
}

export function hasAlignment(alignment) {
    return Boolean(alignment && (alignment.satisfied.length || alignment.missed.length || alignment.deferred.length))
}

export function hasReviewSummary(summary) {
    return Boolean(summary && typeof summary === 'object' && (
        Number(summary.overall_score || 0) > 0 ||
        Array.isArray(summary.issues) && summary.issues.length > 0 ||
        Array.isArray(summary.reviewers) && summary.reviewers.length > 0 ||
        summary.summary
    ))
}

export function formatGuardedOutcome(value) {
    if (value === 'completed_one_chapter') return '已推进一章'
    if (value === 'blocked_story_refresh') return '因刷新建议而停止'
    if (value === 'blocked_by_review') return '被审查关卡拦截'
    if (value === 'stopped_for_approval') return '停在人工审批'
    return value || '-'
}

export function formatGuardedBatchOutcome(value) {
    if (value === 'completed_requested_batch') return '已完成请求章数'
    if (value === 'blocked_story_refresh') return '因刷新建议而停止'
    if (value === 'blocked_by_review') return '被审查关卡拦截'
    if (value === 'stopped_for_approval') return '停在人工审批'
    if (value === 'child_task_failed') return '子任务失败后停止'
    return value || '-'
}

export function TaskContinuationSection({ continuationSummary, operatorActions, renderOperatorActionButtons, MetricCard }) {
    if (!continuationSummary) return null
    return (
        <div className="subsection">
            <div className="subsection-title">推进判断</div>
            <div className={`planning-warning ${continuationSummary.tone === 'success' ? 'subtle' : ''}`}>
                <div className="detail-grid">
                    <MetricCard label="当前判断" value={continuationSummary.heading || '-'} />
                    <MetricCard label="继续状态" value={continuationSummary.continuation || '-'} />
                    <MetricCard label="建议下一步" value={continuationSummary.nextStep || '-'} />
                    <MetricCard label="主动作入口" value={continuationSummary.actionLabel || '-'} />
                </div>
                {continuationSummary.summary ? <div className="tiny">{continuationSummary.summary}</div> : null}
                {continuationSummary.reasons?.length ? (
                    <div className="alignment-list">
                        {continuationSummary.reasons.map((item) => (
                            <div
                                key={`continuation-${item}`}
                                className={`alignment-chip ${continuationSummary.tone === 'danger' ? 'missed' : (continuationSummary.tone === 'success' ? 'satisfied' : 'neutral')}`}
                            >
                                {item}
                            </div>
                        ))}
                    </div>
                ) : null}
                {operatorActions.length ? (
                    <div className="button-row">
                        {renderOperatorActionButtons(operatorActions)}
                    </div>
                ) : null}
            </div>
        </div>
    )
}

export function NarrativeContractsSection({ storyPlan, directorBrief, currentStorySlot, MetricCard }) {
    if (!(storyPlan || directorBrief)) return null
    return (
        <div className="subsection">
            <div className="subsection-title">叙事导演合同</div>
            {storyPlan ? (
                <div className="planning-warning subtle">
                    <div className="detail-grid">
                        <MetricCard label="锚点章节" value={`第 ${storyPlan.anchor_chapter || '-'} 章`} />
                        <MetricCard label="规划窗口" value={`${storyPlan.planning_horizon || '-'} 章`} />
                        <MetricCard label="优先线程数" value={String((storyPlan.priority_threads || []).length)} />
                        <MetricCard label="兑现排期数" value={String((storyPlan.payoff_schedule || []).length)} />
                    </div>
                    {storyPlan.priority_threads?.length ? (
                        <div>
                            <div className="tiny">优先推进线程</div>
                            <div className="planning-tags">
                                {storyPlan.priority_threads.map((item) => (
                                    <span key={item} className="planning-tag">{item}</span>
                                ))}
                            </div>
                        </div>
                    ) : null}
                    {storyPlan.risk_flags?.length ? (
                        <div>
                            <div className="tiny">风险标记</div>
                            <div className="alignment-list">
                                {storyPlan.risk_flags.map((item) => (
                                    <div key={item} className="alignment-chip missed">{item}</div>
                                ))}
                            </div>
                        </div>
                    ) : null}
                    {storyPlan.transition_notes?.length ? (
                        <div>
                            <div className="tiny">转场说明</div>
                            <div className="alignment-list">
                                {storyPlan.transition_notes.map((item) => (
                                    <div key={item} className="alignment-chip neutral">{item}</div>
                                ))}
                            </div>
                        </div>
                    ) : null}
                    {currentStorySlot ? (
                        <div className="summary-card">
                            <div className="summary-card-title">当前章槽位: 第 {currentStorySlot.chapter} 章 / {currentStorySlot.role}</div>
                            <div className="summary-card-meta">目标：{currentStorySlot.chapter_goal || '-'}</div>
                            <div className="summary-card-meta">章末钩子：{currentStorySlot.ending_hook_target || '-'}</div>
                            {(currentStorySlot.must_advance_threads || []).length ? (
                                <div className="planning-tags">
                                    {currentStorySlot.must_advance_threads.map((item) => (
                                        <span key={item} className="planning-tag">{item}</span>
                                    ))}
                                </div>
                            ) : null}
                        </div>
                    ) : null}
                    {(storyPlan.chapters || []).length ? (
                        <div className="summary-grid">
                            {storyPlan.chapters.map((slot) => (
                                <div key={`${slot.chapter}-${slot.role}`} className="summary-card">
                                    <div className="summary-card-title">第 {slot.chapter} 章</div>
                                    <div className="tiny">{slot.role || 'progression'}</div>
                                    <div className="summary-card-meta">{slot.chapter_goal || '-'}</div>
                                    <div className="summary-card-meta">Hook：{slot.ending_hook_target || '-'}</div>
                                </div>
                            ))}
                        </div>
                    ) : null}
                </div>
            ) : null}
            {directorBrief ? (
                <div className="planning-warning subtle">
                    <div className="detail-grid">
                        <MetricCard label="单章目标" value={directorBrief.chapter_goal || '-'} />
                        <MetricCard label="主冲突" value={directorBrief.primary_conflict || '-'} />
                        <MetricCard label="章末钩子" value={directorBrief.ending_hook_target || '-'} />
                        <MetricCard label="节奏" value={directorBrief.tempo || '-'} />
                    </div>
                    {renderTagBlock('必须推进', directorBrief.must_advance_threads)}
                    {renderTagBlock('兑现目标', directorBrief.payoff_targets)}
                    {renderTagBlock('铺垫目标', directorBrief.setup_targets)}
                    {renderTagBlock('必须使用实体', directorBrief.must_use_entities)}
                </div>
            ) : null}
        </div>
    )
}

export function AlignmentResultsSection({ storyAlignment, directorAlignment }) {
    if (!(hasAlignment(storyAlignment) || hasAlignment(directorAlignment))) return null
    return (
        <div className="subsection">
            <div className="subsection-title">执行对齐结果</div>
            <div className="summary-grid">
                {hasAlignment(storyAlignment) ? (
                    <AlignmentCard title="Story Alignment" alignment={storyAlignment} />
                ) : null}
                {hasAlignment(directorAlignment) ? (
                    <AlignmentCard title="Director Alignment" alignment={directorAlignment} />
                ) : null}
            </div>
        </div>
    )
}

export function StoryRefreshSection({ storyRefresh, canRefreshStoryPlan, onRetryStory, MetricCard }) {
    if (!storyRefresh) return null
    return (
        <div className="subsection">
            <div className="subsection-title">滚动规划刷新建议</div>
            <div className={`planning-warning ${storyRefresh.should_refresh ? '' : 'subtle'}`}>
                <div className="detail-grid">
                    <MetricCard label="是否建议刷新" value={storyRefresh.should_refresh ? '建议刷新' : '继续沿用'} />
                    <MetricCard label="建议起点" value={storyRefresh.recommended_resume_from || '-'} />
                    <MetricCard label="连续 miss 章节" value={String(storyRefresh.consecutive_missed_chapters || 0)} />
                    <MetricCard label="本章 missed" value={String(storyRefresh.current_missed_count || 0)} />
                </div>
                <div className="tiny">{storyRefresh.suggested_action || '-'}</div>
                {storyRefresh.reasons?.length ? (
                    <div className="alignment-list">
                        {storyRefresh.reasons.map((item) => (
                            <div key={item} className={`alignment-chip ${storyRefresh.should_refresh ? 'missed' : 'neutral'}`}>{item}</div>
                        ))}
                    </div>
                ) : null}
                {canRefreshStoryPlan ? (
                    <div className="button-row">
                        <button className="primary-button" onClick={onRetryStory}>
                            从 Story Director 重新规划
                        </button>
                    </div>
                ) : null}
            </div>
        </div>
    )
}

export function ReviewSummarySection({ summary, MetricCard }) {
    if (!hasReviewSummary(summary)) return null
    const issues = Array.isArray(summary.issues) ? summary.issues : []
    const reviewers = Array.isArray(summary.reviewers) ? summary.reviewers : []
    return (
        <div className="subsection">
            <div className="subsection-title">审查摘要</div>
            <div className="planning-warning subtle">
                <div className="detail-grid">
                    <MetricCard label="总评分" value={String(summary.overall_score ?? '-')} />
                    <MetricCard label="是否阻断" value={summary.blocking ? '是' : '否'} />
                    <MetricCard label="问题数" value={String(issues.length)} />
                    <MetricCard label="审查器" value={reviewers.length ? reviewers.join(', ') : '-'} />
                </div>
                {summary.summary ? <div className="tiny">{summary.summary}</div> : null}
                {issues.length ? (
                    <div className="alignment-list">
                        {issues.slice(0, 6).map((issue, index) => (
                            <div key={`${issue.title || issue.severity || 'issue'}-${index}`} className={`alignment-chip ${issue.severity === 'critical' ? 'missed' : 'neutral'}`}>
                                {issue.title || issue.summary || issue.severity || '未命名问题'}
                            </div>
                        ))}
                    </div>
                ) : null}
            </div>
        </div>
    )
}

export function GuardedRunSection({ guardedRun, MetricCard, translateStepName, translateTaskStatus }) {
    if (!guardedRun) return null
    return (
        <div className="subsection">
            <div className="subsection-title">护栏推进结果</div>
            <div className="planning-warning subtle">
                <div className="detail-grid">
                    <MetricCard label="目标章节" value={`第 ${guardedRun.chapter || '-'} 章`} />
                    <MetricCard label="执行结果" value={formatGuardedOutcome(guardedRun.outcome)} />
                    <MetricCard label="停止步骤" value={translateStepName(guardedRun.stop_step || 'idle')} />
                    <MetricCard label="可继续排下一章" value={guardedRun.safe_to_continue ? '可以' : '不可以'} />
                </div>
                {guardedRun.next_action?.reason ? <div className="tiny">{guardedRun.next_action.reason}</div> : null}
                {guardedRun.next_action?.suggested_action ? <div className="tiny">{guardedRun.next_action.suggested_action}</div> : null}
                <div className="detail-grid">
                    <MetricCard label="子任务" value={guardedRun.child_task_id || '-'} />
                    <MetricCard label="子任务状态" value={guardedRun.child_task_status ? translateTaskStatus(guardedRun.child_task_status) : '-'} />
                    <MetricCard label="建议下一章" value={guardedRun.next_action?.next_chapter ? `第 ${guardedRun.next_action.next_chapter} 章` : '-'} />
                    <MetricCard label="建议排队" value={guardedRun.next_action?.can_enqueue_next ? '建议' : '暂停'} />
                </div>
            </div>
        </div>
    )
}

export function GuardedBatchSection({
    guardedBatchRun,
    MetricCard,
    translateStepName,
    translateTaskStatus,
    onSelectTask,
    lastSuccessfulBatchRun,
    lastGuardedBatchRun,
    nextRecommendedAction,
}) {
    if (!guardedBatchRun) return null
    return (
        <div className="subsection">
            <div className="subsection-title">护栏批量推进结果</div>
            <div className="planning-warning subtle">
                <div className="detail-grid">
                    <MetricCard label="起始章节" value={`第 ${guardedBatchRun.start_chapter || '-'} 章`} />
                    <MetricCard label="请求章数" value={String(guardedBatchRun.requested_max_chapters || 0)} />
                    <MetricCard label="已完成章数" value={String(guardedBatchRun.completed_chapters || 0)} />
                    <MetricCard label="执行结果" value={formatGuardedBatchOutcome(guardedBatchRun.outcome)} />
                </div>
                {guardedBatchRun.next_action?.reason ? <div className="tiny">{guardedBatchRun.next_action.reason}</div> : null}
                {guardedBatchRun.next_action?.suggested_action ? <div className="tiny">{guardedBatchRun.next_action.suggested_action}</div> : null}
                <div className="detail-grid">
                    <MetricCard label="停止步骤" value={translateStepName(guardedBatchRun.stop_step || 'idle')} />
                    <MetricCard label="停止原因" value={formatGuardedBatchOutcome(guardedBatchRun.stop_reason)} />
                    <MetricCard label="最后子任务" value={guardedBatchRun.last_child_task_id || '-'} />
                    <MetricCard label="最后子任务状态" value={guardedBatchRun.last_child_task_status ? translateTaskStatus(guardedBatchRun.last_child_task_status) : '-'} />
                </div>
                <div className="detail-grid">
                    <MetricCard label="最后成功章节" value={lastSuccessfulBatchRun?.chapter ? `第 ${lastSuccessfulBatchRun.chapter} 章` : '-'} />
                    <MetricCard label="实际停止章节" value={lastGuardedBatchRun?.chapter ? `第 ${lastGuardedBatchRun.chapter} 章` : '-'} />
                    <MetricCard label="停止判定" value={formatGuardedBatchOutcome(guardedBatchRun.stop_reason || guardedBatchRun.outcome)} />
                    <MetricCard label="下一推荐动作" value={nextRecommendedAction?.label || guardedBatchRun.next_action?.suggested_action || '-'} />
                </div>
                {(guardedBatchRun.runs || []).length ? (
                    <div className="summary-grid">
                        {guardedBatchRun.runs.map((item) => (
                            <div key={`${item.task_id || item.chapter}`} className="summary-card">
                                <div className="summary-card-title">第 {item.chapter || '-'} 章</div>
                                <div className="summary-card-meta">{formatGuardedOutcome(item.outcome || '-')}</div>
                                <div className="summary-card-meta">停止步骤：{translateStepName(item.stop_step || 'idle')}</div>
                                <div className="summary-card-meta">子任务：{item.task_id || '-'}</div>
                                <div className="summary-card-meta">建议下一章：{item.next_chapter ? `第 ${item.next_chapter} 章` : '-'}</div>
                                {item.task_id ? (
                                    <div className="button-row">
                                        <button className="secondary-button" onClick={() => onSelectTask(item.task_id)}>查看该子任务</button>
                                    </div>
                                ) : null}
                            </div>
                        ))}
                    </div>
                ) : null}
            </div>
        </div>
    )
}

export function ResumeSection({ resumeRun, MetricCard, translateStepName }) {
    if (!resumeRun) return null
    return (
        <div className="subsection">
            <div className="subsection-title">恢复任务合同</div>
            <div className="planning-warning subtle">
                <div className="detail-grid">
                    <MetricCard label="目标任务" value={resumeRun.target_task_id || '-'} />
                    <MetricCard label="恢复步骤" value={resumeRun.resume_from_step ? translateStepName(resumeRun.resume_from_step) : '-'} />
                    <MetricCard label="恢复原因" value={resumeRun.resume_reason || '-'} />
                    <MetricCard label="阻塞原因" value={resumeRun.blocking_reason || '-'} />
                </div>
            </div>
        </div>
    )
}
