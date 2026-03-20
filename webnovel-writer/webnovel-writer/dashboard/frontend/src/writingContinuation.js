import { inferRecoveryKindFromTask, resolveRecoverySemantics } from './recoverySemantics.js'
import { WRITING_CONTINUATION } from './writingTaskCopy.js'

function isRecord(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeList(value) {
    return Array.isArray(value) ? value.filter((item) => typeof item === 'string' && item.trim()) : []
}

function firstPrimaryAction(actions) {
    if (!Array.isArray(actions) || actions.length === 0) return null
    return actions.find((item) => item?.variant === 'primary') || actions[0] || null
}

function buildAlignmentSignals(label, alignment) {
    const missed = normalizeList(alignment?.missed)
    const deferred = normalizeList(alignment?.deferred)
    const satisfied = normalizeList(alignment?.satisfied)
    const signals = []
    if (missed.length) signals.push(`${label} 尚有 ${missed.length} 项未满足`)
    if (deferred.length) signals.push(`${label} 已延后 ${deferred.length} 项`)
    if (!missed.length && satisfied.length) signals.push(`${label} 已满足 ${satisfied.length} 项`)
    return signals
}

function buildContractSignals({
    storyPlan,
    directorBrief,
    storyAlignment,
    directorAlignment,
    storyRefresh,
}) {
    const signals = []
    if (storyPlan) signals.push('已接入 Story Director 多章规划')
    if (directorBrief) signals.push('已接入 Chapter Director 单章合同')
    signals.push(...buildAlignmentSignals('Story Alignment', storyAlignment))
    signals.push(...buildAlignmentSignals('Director Alignment', directorAlignment))
    if (storyRefresh?.should_refresh) {
        signals.push(`Story Refresh 建议从 ${storyRefresh.recommended_resume_from || 'story-director'} 恢复`)
    }
    return signals
}

function dedupeSignals(items) {
    const seen = new Set()
    const signals = []
    for (const item of items || []) {
        const text = typeof item === 'string' ? item.trim() : ''
        if (!text || seen.has(text)) continue
        seen.add(text)
        signals.push(text)
    }
    return signals
}

function buildSummary({
    tone,
    heading,
    continuation,
    nextStep,
    summary,
    reasons,
    actionLabel,
}) {
    return {
        tone,
        heading,
        continuation,
        nextStep,
        summary,
        reasons: dedupeSignals(reasons).slice(0, 6),
        actionLabel: actionLabel || '-',
    }
}

function resolveReviewIssueCount(task, guardedRun, guardedBatchRun) {
    const reviewSummary = guardedRun?.review_summary || guardedBatchRun?.review_summary || task?.artifacts?.review_summary
    if (!isRecord(reviewSummary)) return 0
    return Array.isArray(reviewSummary.issues) ? reviewSummary.issues.length : 0
}

function buildResumeContinuation(task, resumeRun, operatorActions, contractSignals) {
    const primaryAction = firstPrimaryAction(operatorActions)
    const blockingReason = String(resumeRun?.blocking_reason || '').trim()
    if (primaryAction?.kind === 'complete-noop') {
        return buildSummary({
            tone: 'success',
            heading: '当前无需恢复',
            continuation: WRITING_CONTINUATION.noop,
            nextStep: '继续查看主链任务即可',
            summary: blockingReason || '当前没有需要恢复的目标任务。',
            reasons: ['恢复检查已完成', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    if (task?.status === 'queued' || task?.status === 'running') {
        return buildSummary({
            tone: 'warning',
            heading: '恢复任务正在处理中',
            continuation: WRITING_CONTINUATION.waitingResumeCompletion,
            nextStep: primaryAction?.label || '等待恢复调度完成',
            summary: blockingReason || '恢复任务正在尝试定位并恢复目标任务。',
            reasons: ['恢复任务仍在运行', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    if (primaryAction?.kind === 'resume-existing-task') {
        return buildSummary({
            tone: 'warning',
            heading: '存在待恢复任务',
            continuation: '恢复后再继续',
            nextStep: primaryAction?.label || '恢复目标任务',
            summary: blockingReason || '系统已经给出可恢复目标，请先恢复原任务链路。',
            reasons: ['恢复目标已定位', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    return buildSummary({
        tone: 'neutral',
        heading: '恢复结论待确认',
        continuation: '建议人工复核',
        nextStep: primaryAction?.label || '查看恢复结果',
        summary: blockingReason || resumeRun?.resume_reason || '当前恢复任务没有明确的下一步建议。',
        reasons: contractSignals,
        actionLabel: primaryAction?.label,
    })
}

function buildGuardedWriteContinuation(task, guardedRun, operatorActions, contractSignals) {
    const primaryAction = firstPrimaryAction(operatorActions)
    const issueCount = resolveReviewIssueCount(task, guardedRun, null)
    if (guardedRun?.outcome === 'completed_one_chapter') {
        return buildSummary({
            tone: 'success',
            heading: '当前可继续推进下一章',
            continuation: WRITING_CONTINUATION.continuable,
            nextStep: primaryAction?.label || '继续护栏推进',
            summary: guardedRun?.next_action?.suggested_action || '当前护栏任务已安全完成一章，可显式发起下一章推进。',
            reasons: [
                '护栏任务已完成当前章',
                ...(guardedRun?.safe_to_continue ? ['护栏结果标记为可继续'] : []),
                ...contractSignals,
            ],
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedRun?.outcome === 'blocked_story_refresh') {
        return buildSummary({
            tone: 'warning',
            heading: '继续前需要先重规划',
            continuation: '暂停推进',
            nextStep: primaryAction?.label || '从推荐步骤重试',
            summary: guardedRun?.next_action?.suggested_action || '护栏推进已经明确要求先刷新叙事规划，再决定是否继续。',
            reasons: ['护栏命中 Story Refresh', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedRun?.outcome === 'blocked_by_review') {
        const recovery = resolveRecoverySemantics({
            recoveryKind: inferRecoveryKindFromTask(task, { guardedOutcome: guardedRun?.outcome }),
            surface: 'guarded-child',
            hasReviewSummary: issueCount > 0,
        })
        return buildSummary({
            tone: 'danger',
            heading: recovery?.heading || '继续前必须处理审查阻断',
            continuation: recovery?.continuation || WRITING_CONTINUATION.blocked,
            nextStep: primaryAction?.label || recovery?.primaryActionLabel || '打开阻断子任务',
            summary: issueCount
                ? `当前子任务的审查摘要记录了 ${issueCount} 个问题，先处理阻断再继续。`
                : '当前子任务被审查关卡拦截，护栏不能继续推进。',
            reasons: ['护栏被审查关卡拦截', recovery?.followupLabel, recovery?.reviewSummaryHint, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedRun?.outcome === 'stopped_for_approval') {
        const recovery = resolveRecoverySemantics({
            recoveryKind: inferRecoveryKindFromTask(task, { guardedOutcome: guardedRun?.outcome }),
            surface: 'guarded-child',
        })
        return buildSummary({
            tone: 'warning',
            heading: recovery?.heading || '继续前需要人工审批',
            continuation: recovery?.continuation || WRITING_CONTINUATION.waitingApproval,
            nextStep: primaryAction?.label || recovery?.primaryActionLabel || '打开待审批子任务',
            summary: '当前护栏任务已经停在 approval-gate，必须先处理待审批子任务。',
            reasons: ['护栏停在人工审批', recovery?.followupLabel, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label,
        })
    }
    return buildSummary({
        tone: 'neutral',
        heading: '护栏结论待确认',
        continuation: '建议人工复核',
        nextStep: primaryAction?.label || '查看护栏结果',
        summary: guardedRun?.next_action?.suggested_action || '当前护栏任务没有给出明确的继续结论。',
        reasons: contractSignals,
        actionLabel: primaryAction?.label,
    })
}

function buildGuardedBatchContinuation(task, guardedBatchRun, operatorActions, contractSignals) {
    const primaryAction = firstPrimaryAction(operatorActions)
    const issueCount = resolveReviewIssueCount(task, null, guardedBatchRun)
    if (guardedBatchRun?.outcome === 'completed_requested_batch') {
        return buildSummary({
            tone: 'success',
            heading: '当前批次可继续下一批',
            continuation: WRITING_CONTINUATION.continuable,
            nextStep: primaryAction?.label || '继续下一批护栏推进',
            summary: guardedBatchRun?.next_action?.suggested_action || '本批护栏已完成请求章数，可以显式发起下一批。',
            reasons: [
                `本批已完成 ${Number(guardedBatchRun?.completed_chapters || 0)} 章`,
                ...contractSignals,
            ],
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedBatchRun?.outcome === 'blocked_story_refresh') {
        return buildSummary({
            tone: 'warning',
            heading: '继续前需要先重规划',
            continuation: '暂停推进',
            nextStep: primaryAction?.label || '从推荐步骤恢复',
            summary: guardedBatchRun?.next_action?.suggested_action || '批量护栏已因 Story Refresh 建议停止，先重规划再决定是否继续。',
            reasons: ['批量护栏命中 Story Refresh', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedBatchRun?.outcome === 'blocked_by_review') {
        const recovery = resolveRecoverySemantics({
            recoveryKind: inferRecoveryKindFromTask(task, { guardedOutcome: guardedBatchRun?.outcome }),
            surface: 'guarded-batch-child',
            hasReviewSummary: issueCount > 0,
        })
        return buildSummary({
            tone: 'danger',
            heading: recovery?.heading || '继续前必须处理审查阻断',
            continuation: recovery?.continuation || WRITING_CONTINUATION.blocked,
            nextStep: primaryAction?.label || recovery?.primaryActionLabel || '打开最后子任务',
            summary: issueCount
                ? `最后一个子任务的审查摘要记录了 ${issueCount} 个问题，先处理阻断再继续。`
                : '批量护栏被最后一个子任务的审查结果阻断。',
            reasons: ['批量护栏被审查关卡拦截', recovery?.followupLabel, recovery?.reviewSummaryHint, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedBatchRun?.outcome === 'stopped_for_approval') {
        const recovery = resolveRecoverySemantics({
            recoveryKind: inferRecoveryKindFromTask(task, { guardedOutcome: guardedBatchRun?.outcome }),
            surface: 'guarded-batch-child',
        })
        return buildSummary({
            tone: 'warning',
            heading: recovery?.heading || '继续前需要人工审批',
            continuation: recovery?.continuation || WRITING_CONTINUATION.waitingApproval,
            nextStep: primaryAction?.label || recovery?.primaryActionLabel || '打开最后子任务',
            summary: '批量护栏停在人工审批，必须先处理最后一个子任务。',
            reasons: ['批量护栏停在人工审批', recovery?.followupLabel, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedBatchRun?.outcome === 'child_task_failed') {
        return buildSummary({
            tone: 'danger',
            heading: '继续前需要先处理失败子任务',
            continuation: WRITING_CONTINUATION.blocked,
            nextStep: primaryAction?.label || '打开失败子任务',
            summary: '批量护栏已经因为子任务失败停止，不能直接继续下一批。',
            reasons: ['批量护栏命中子任务失败', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    return buildSummary({
        tone: 'neutral',
        heading: '批量推进结论待确认',
        continuation: '建议人工复核',
        nextStep: primaryAction?.label || '查看批量结果',
        summary: guardedBatchRun?.next_action?.suggested_action || '当前批量护栏没有给出明确的继续结论。',
        reasons: contractSignals,
        actionLabel: primaryAction?.label,
    })
}

function buildWriteContinuation(task, storyRefresh, contractSignals, operatorActions) {
    const primaryAction = firstPrimaryAction(operatorActions)
    const reviewIssueCount = resolveReviewIssueCount(task, null, null)
    const reviewBlocked = String(task?.error?.code || '').trim() === 'REVIEW_GATE_BLOCKED'
    const missedCount =
        normalizeList(task?.artifacts?.writeback?.director_alignment?.missed).length
        + normalizeList(task?.artifacts?.writeback?.story_alignment?.missed).length

    if (task?.status === 'queued' || task?.status === 'running') {
        return buildSummary({
            tone: 'warning',
            heading: '当前任务仍在执行',
            continuation: WRITING_CONTINUATION.waitingCompletion,
            nextStep: task?.runtime_status?.phase_label || task?.current_step || '等待当前步骤结束',
            summary: task?.runtime_status?.phase_detail || '写作主链仍在运行，建议等待当前任务结束后再决定是否继续。',
            reasons: ['主链任务仍在运行', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    if (task?.status === 'awaiting_writeback_approval') {
        const recovery = resolveRecoverySemantics({
            recoveryKind: inferRecoveryKindFromTask(task),
            surface: 'write',
        })
        return buildSummary({
            tone: 'warning',
            heading: recovery?.heading || '继续前需要人工审批',
            continuation: recovery?.continuation || WRITING_CONTINUATION.waitingApproval,
            nextStep: recovery?.primaryActionLabel || '批准或拒绝回写',
            summary: '正文已经生成并停在 approval-gate，必须先处理人工审批。',
            reasons: ['当前 write 任务停在 approval-gate', recovery?.followupLabel, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label || recovery?.primaryActionLabel || '批准或拒绝回写',
        })
    }
    if (reviewBlocked) {
        const recovery = resolveRecoverySemantics({
            recoveryKind: inferRecoveryKindFromTask(task),
            surface: 'write',
            hasReviewSummary: reviewIssueCount > 0,
        })
        return buildSummary({
            tone: 'danger',
            heading: recovery?.heading || '继续前必须处理审查阻断',
            continuation: recovery?.continuation || WRITING_CONTINUATION.blocked,
            nextStep: recovery?.primaryActionLabel || '打开阻断任务并修复',
            summary: reviewIssueCount
                ? `审查摘要记录了 ${reviewIssueCount} 个问题，当前章节尚不满足继续推进条件。`
                : '当前章节被审查关卡拦截，不能直接继续下一章。',
            reasons: ['Write 任务被审查关卡拦截', recovery?.followupLabel, recovery?.reviewSummaryHint, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label,
        })
    }
    if (storyRefresh?.should_refresh) {
        return buildSummary({
            tone: 'warning',
            heading: '继续前建议先重规划',
            continuation: '建议暂停',
            nextStep: `从 ${storyRefresh.recommended_resume_from || 'story-director'} 重试`,
            summary: storyRefresh.suggested_action || '当前章节的写回结果已经建议先刷新滚动规划，再决定是否继续。',
            reasons: ['Writeback 建议 Story Refresh', ...contractSignals],
            actionLabel: primaryAction?.label || `从 ${storyRefresh.recommended_resume_from || 'story-director'} 重试`,
        })
    }
    if (task?.status === 'completed' && missedCount > 0) {
        return buildSummary({
            tone: 'warning',
            heading: '本章已完成，但建议复核后再继续',
            continuation: '建议复核',
            nextStep: '查看对齐结果后决定是否继续',
            summary: '当前章节已完成写回，但仍存在未满足的导演或多章合同项，建议先人工复核。',
            reasons: contractSignals,
            actionLabel: primaryAction?.label,
        })
    }
    if (task?.status === 'completed') {
        return buildSummary({
            tone: 'success',
            heading: '当前可继续下一章',
            continuation: WRITING_CONTINUATION.continuable,
            nextStep: '创建下一章写作或护栏推进',
            summary: '当前章节已完成写回，未命中新的 Story Refresh 或审查阻断，可以进入下一章。',
            reasons: ['当前章节已完成写回', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    return buildSummary({
        tone: 'neutral',
        heading: '当前状态待人工判断',
        continuation: '建议人工复核',
        nextStep: primaryAction?.label || '查看任务详情',
        summary: '当前任务没有命中明确的继续或阻断分支，请结合任务结果人工判断。',
        reasons: contractSignals,
        actionLabel: primaryAction?.label,
    })
}

export function buildTaskContinuationSummary({
    task,
    storyPlan,
    directorBrief,
    storyAlignment,
    directorAlignment,
    storyRefresh,
    guardedRun,
    guardedBatchRun,
    resumeRun,
    operatorActions,
}) {
    const contractSignals = buildContractSignals({
        storyPlan,
        directorBrief,
        storyAlignment,
        directorAlignment,
        storyRefresh,
    })

    if (task?.task_type === 'resume') {
        return buildResumeContinuation(task, resumeRun, operatorActions, contractSignals)
    }
    if (guardedBatchRun) {
        return buildGuardedBatchContinuation(task, guardedBatchRun, operatorActions, contractSignals)
    }
    if (guardedRun) {
        return buildGuardedWriteContinuation(task, guardedRun, operatorActions, contractSignals)
    }
    return buildWriteContinuation(task, storyRefresh, contractSignals, operatorActions)
}
