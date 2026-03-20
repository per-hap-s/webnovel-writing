import { inferRecoveryKindFromTask, resolveRecoverySemantics } from './recoverySemantics.js'

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
    if (missed.length) signals.push(`${label} \u5c1a\u6709 ${missed.length} \u9879\u672a\u6ee1\u8db3`)
    if (deferred.length) signals.push(`${label} \u5df2\u5ef6\u540e ${deferred.length} \u9879`)
    if (!missed.length && satisfied.length) signals.push(`${label} \u5df2\u6ee1\u8db3 ${satisfied.length} \u9879`)
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
    if (storyPlan) signals.push('\u5df2\u63a5\u5165 Story Director \u591a\u7ae0\u89c4\u5212')
    if (directorBrief) signals.push('\u5df2\u63a5\u5165 Chapter Director \u5355\u7ae0\u5408\u540c')
    signals.push(...buildAlignmentSignals('Story Alignment', storyAlignment))
    signals.push(...buildAlignmentSignals('Director Alignment', directorAlignment))
    if (storyRefresh?.should_refresh) {
        signals.push(`Story Refresh \u5efa\u8bae\u4ece ${storyRefresh.recommended_resume_from || 'story-director'} \u6062\u590d`)
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
            heading: '\u5f53\u524d\u65e0\u9700\u6062\u590d',
            continuation: '\u65e0\u9700\u64cd\u4f5c',
            nextStep: '\u7ee7\u7eed\u67e5\u770b\u4e3b\u94fe\u4efb\u52a1\u5373\u53ef',
            summary: blockingReason || '\u5f53\u524d\u6ca1\u6709\u9700\u8981\u6062\u590d\u7684\u76ee\u6807\u4efb\u52a1\u3002',
            reasons: ['\u6062\u590d\u68c0\u67e5\u5df2\u5b8c\u6210', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    if (task?.status === 'queued' || task?.status === 'running') {
        return buildSummary({
            tone: 'warning',
            heading: '\u6062\u590d\u4efb\u52a1\u6b63\u5728\u5904\u7406\u4e2d',
            continuation: '\u7b49\u5f85\u6062\u590d\u5b8c\u6210',
            nextStep: primaryAction?.label || '\u7b49\u5f85\u6062\u590d\u8c03\u5ea6\u5b8c\u6210',
            summary: blockingReason || '\u6062\u590d\u4efb\u52a1\u6b63\u5728\u5c1d\u8bd5\u5b9a\u4f4d\u5e76\u6062\u590d\u76ee\u6807\u4efb\u52a1\u3002',
            reasons: ['\u6062\u590d\u4efb\u52a1\u4ecd\u5728\u8fd0\u884c', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    if (primaryAction?.kind === 'resume-existing-task') {
        return buildSummary({
            tone: 'warning',
            heading: '\u5b58\u5728\u5f85\u6062\u590d\u4efb\u52a1',
            continuation: '\u6062\u590d\u540e\u518d\u7ee7\u7eed',
            nextStep: primaryAction?.label || '\u6062\u590d\u76ee\u6807\u4efb\u52a1',
            summary: blockingReason || '\u7cfb\u7edf\u5df2\u7ecf\u7ed9\u51fa\u53ef\u6062\u590d\u76ee\u6807\uff0c\u8bf7\u5148\u6062\u590d\u539f\u4efb\u52a1\u94fe\u8def\u3002',
            reasons: ['\u6062\u590d\u76ee\u6807\u5df2\u5b9a\u4f4d', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    return buildSummary({
        tone: 'neutral',
        heading: '\u6062\u590d\u7ed3\u8bba\u5f85\u786e\u8ba4',
        continuation: '\u5efa\u8bae\u4eba\u5de5\u590d\u6838',
        nextStep: primaryAction?.label || '\u67e5\u770b\u6062\u590d\u7ed3\u679c',
        summary: blockingReason || resumeRun?.resume_reason || '\u5f53\u524d\u6062\u590d\u4efb\u52a1\u6ca1\u6709\u660e\u786e\u7684\u4e0b\u4e00\u6b65\u5efa\u8bae\u3002',
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
            heading: '\u5f53\u524d\u53ef\u7ee7\u7eed\u63a8\u8fdb\u4e0b\u4e00\u7ae0',
            continuation: '\u53ef\u4ee5\u7ee7\u7eed',
            nextStep: primaryAction?.label || '\u7ee7\u7eed\u62a4\u680f\u63a8\u8fdb',
            summary: guardedRun?.next_action?.suggested_action || '\u5f53\u524d\u62a4\u680f\u4efb\u52a1\u5df2\u5b89\u5168\u5b8c\u6210\u4e00\u7ae0\uff0c\u53ef\u663e\u5f0f\u53d1\u8d77\u4e0b\u4e00\u7ae0\u63a8\u8fdb\u3002',
            reasons: [
                '\u62a4\u680f\u4efb\u52a1\u5df2\u5b8c\u6210\u5f53\u524d\u7ae0',
                ...(guardedRun?.safe_to_continue ? ['\u62a4\u680f\u7ed3\u679c\u6807\u8bb0\u4e3a\u53ef\u7ee7\u7eed'] : []),
                ...contractSignals,
            ],
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedRun?.outcome === 'blocked_story_refresh') {
        return buildSummary({
            tone: 'warning',
            heading: '\u7ee7\u7eed\u524d\u9700\u8981\u5148\u91cd\u89c4\u5212',
            continuation: '\u6682\u505c\u63a8\u8fdb',
            nextStep: primaryAction?.label || '\u4ece\u63a8\u8350\u6b65\u9aa4\u91cd\u8bd5',
            summary: guardedRun?.next_action?.suggested_action || '\u62a4\u680f\u63a8\u8fdb\u5df2\u7ecf\u660e\u786e\u8981\u6c42\u5148\u5237\u65b0\u53d9\u4e8b\u89c4\u5212\uff0c\u518d\u51b3\u5b9a\u662f\u5426\u7ee7\u7eed\u3002',
            reasons: ['\u62a4\u680f\u547d\u4e2d Story Refresh', ...contractSignals],
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
            heading: recovery?.heading || '\u7ee7\u7eed\u524d\u5fc5\u987b\u5904\u7406\u5ba1\u67e5\u963b\u65ad',
            continuation: recovery?.continuation || '\u4e0d\u53ef\u7ee7\u7eed',
            nextStep: primaryAction?.label || recovery?.primaryActionLabel || '\u6253\u5f00\u963b\u65ad\u5b50\u4efb\u52a1',
            summary: issueCount ? `\u5f53\u524d\u5b50\u4efb\u52a1\u7684\u5ba1\u67e5\u6458\u8981\u8bb0\u5f55\u4e86 ${issueCount} \u4e2a\u95ee\u9898\uff0c\u5148\u5904\u7406\u963b\u65ad\u518d\u7ee7\u7eed\u3002` : '\u5f53\u524d\u5b50\u4efb\u52a1\u88ab\u5ba1\u67e5\u5173\u5361\u62e6\u622a\uff0c\u62a4\u680f\u4e0d\u80fd\u7ee7\u7eed\u63a8\u8fdb\u3002',
            reasons: ['\u62a4\u680f\u88ab\u5ba1\u67e5\u5173\u5361\u62e6\u622a', recovery?.followupLabel, recovery?.reviewSummaryHint, ...contractSignals].filter(Boolean),
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
            heading: recovery?.heading || '\u7ee7\u7eed\u524d\u9700\u8981\u4eba\u5de5\u5ba1\u6279',
            continuation: recovery?.continuation || '\u7b49\u5f85\u5ba1\u6279',
            nextStep: primaryAction?.label || recovery?.primaryActionLabel || '\u6253\u5f00\u5f85\u5ba1\u6279\u5b50\u4efb\u52a1',
            summary: '\u5f53\u524d\u62a4\u680f\u4efb\u52a1\u5df2\u7ecf\u505c\u5728 approval-gate\uff0c\u5fc5\u987b\u5148\u5904\u7406\u5f85\u5ba1\u6279\u5b50\u4efb\u52a1\u3002',
            reasons: ['\u62a4\u680f\u505c\u5728\u4eba\u5de5\u5ba1\u6279', recovery?.followupLabel, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label,
        })
    }
    return buildSummary({
        tone: 'neutral',
        heading: '\u62a4\u680f\u7ed3\u8bba\u5f85\u786e\u8ba4',
        continuation: '\u5efa\u8bae\u4eba\u5de5\u590d\u6838',
        nextStep: primaryAction?.label || '\u67e5\u770b\u62a4\u680f\u7ed3\u679c',
        summary: guardedRun?.next_action?.suggested_action || '\u5f53\u524d\u62a4\u680f\u4efb\u52a1\u6ca1\u6709\u7ed9\u51fa\u660e\u786e\u7684\u7ee7\u7eed\u7ed3\u8bba\u3002',
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
            heading: '\u5f53\u524d\u6279\u6b21\u53ef\u7ee7\u7eed\u4e0b\u4e00\u6279',
            continuation: '\u53ef\u4ee5\u7ee7\u7eed',
            nextStep: primaryAction?.label || '\u7ee7\u7eed\u4e0b\u4e00\u6279\u62a4\u680f\u63a8\u8fdb',
            summary: guardedBatchRun?.next_action?.suggested_action || '\u672c\u6279\u62a4\u680f\u5df2\u5b8c\u6210\u8bf7\u6c42\u7ae0\u6570\uff0c\u53ef\u4ee5\u663e\u5f0f\u53d1\u8d77\u4e0b\u4e00\u6279\u3002',
            reasons: [
                `\u672c\u6279\u5df2\u5b8c\u6210 ${Number(guardedBatchRun?.completed_chapters || 0)} \u7ae0`,
                ...contractSignals,
            ],
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedBatchRun?.outcome === 'blocked_story_refresh') {
        return buildSummary({
            tone: 'warning',
            heading: '\u7ee7\u7eed\u524d\u9700\u8981\u5148\u91cd\u89c4\u5212',
            continuation: '\u6682\u505c\u63a8\u8fdb',
            nextStep: primaryAction?.label || '\u4ece\u63a8\u8350\u6b65\u9aa4\u6062\u590d',
            summary: guardedBatchRun?.next_action?.suggested_action || '\u6279\u91cf\u62a4\u680f\u5df2\u56e0 Story Refresh \u5efa\u8bae\u505c\u6b62\uff0c\u5148\u91cd\u89c4\u5212\u518d\u51b3\u5b9a\u662f\u5426\u7ee7\u7eed\u3002',
            reasons: ['\u6279\u91cf\u62a4\u680f\u547d\u4e2d Story Refresh', ...contractSignals],
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
            heading: recovery?.heading || '\u7ee7\u7eed\u524d\u5fc5\u987b\u5904\u7406\u5ba1\u67e5\u963b\u65ad',
            continuation: recovery?.continuation || '\u4e0d\u53ef\u7ee7\u7eed',
            nextStep: primaryAction?.label || recovery?.primaryActionLabel || '\u6253\u5f00\u6700\u540e\u5b50\u4efb\u52a1',
            summary: issueCount ? `\u6700\u540e\u4e00\u4e2a\u5b50\u4efb\u52a1\u7684\u5ba1\u67e5\u6458\u8981\u8bb0\u5f55\u4e86 ${issueCount} \u4e2a\u95ee\u9898\uff0c\u5148\u5904\u7406\u963b\u65ad\u518d\u7ee7\u7eed\u3002` : '\u6279\u91cf\u62a4\u680f\u88ab\u6700\u540e\u4e00\u4e2a\u5b50\u4efb\u52a1\u7684\u5ba1\u67e5\u7ed3\u679c\u963b\u65ad\u3002',
            reasons: ['\u6279\u91cf\u62a4\u680f\u88ab\u5ba1\u67e5\u5173\u5361\u62e6\u622a', recovery?.followupLabel, recovery?.reviewSummaryHint, ...contractSignals].filter(Boolean),
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
            heading: recovery?.heading || '\u7ee7\u7eed\u524d\u9700\u8981\u4eba\u5de5\u5ba1\u6279',
            continuation: recovery?.continuation || '\u7b49\u5f85\u5ba1\u6279',
            nextStep: primaryAction?.label || recovery?.primaryActionLabel || '\u6253\u5f00\u6700\u540e\u5b50\u4efb\u52a1',
            summary: '\u6279\u91cf\u62a4\u680f\u505c\u5728\u4eba\u5de5\u5ba1\u6279\uff0c\u5fc5\u987b\u5148\u5904\u7406\u6700\u540e\u4e00\u4e2a\u5b50\u4efb\u52a1\u3002',
            reasons: ['\u6279\u91cf\u62a4\u680f\u505c\u5728\u4eba\u5de5\u5ba1\u6279', recovery?.followupLabel, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label,
        })
    }
    if (guardedBatchRun?.outcome === 'child_task_failed') {
        return buildSummary({
            tone: 'danger',
            heading: '\u7ee7\u7eed\u524d\u9700\u8981\u5148\u5904\u7406\u5931\u8d25\u5b50\u4efb\u52a1',
            continuation: '\u4e0d\u53ef\u7ee7\u7eed',
            nextStep: primaryAction?.label || '\u6253\u5f00\u5931\u8d25\u5b50\u4efb\u52a1',
            summary: '\u6279\u91cf\u62a4\u680f\u5df2\u7ecf\u56e0\u4e3a\u5b50\u4efb\u52a1\u5931\u8d25\u505c\u6b62\uff0c\u4e0d\u80fd\u76f4\u63a5\u7ee7\u7eed\u4e0b\u4e00\u6279\u3002',
            reasons: ['\u6279\u91cf\u62a4\u680f\u547d\u4e2d\u5b50\u4efb\u52a1\u5931\u8d25', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    return buildSummary({
        tone: 'neutral',
        heading: '\u6279\u91cf\u63a8\u8fdb\u7ed3\u8bba\u5f85\u786e\u8ba4',
        continuation: '\u5efa\u8bae\u4eba\u5de5\u590d\u6838',
        nextStep: primaryAction?.label || '\u67e5\u770b\u6279\u91cf\u7ed3\u679c',
        summary: guardedBatchRun?.next_action?.suggested_action || '\u5f53\u524d\u6279\u91cf\u62a4\u680f\u6ca1\u6709\u7ed9\u51fa\u660e\u786e\u7684\u7ee7\u7eed\u7ed3\u8bba\u3002',
        reasons: contractSignals,
        actionLabel: primaryAction?.label,
    })
}

function buildWriteContinuation(task, storyRefresh, contractSignals, operatorActions) {
    const primaryAction = firstPrimaryAction(operatorActions)
    const reviewIssueCount = resolveReviewIssueCount(task, null, null)
    const reviewBlocked = String(task?.error?.code || '').trim() === 'REVIEW_GATE_BLOCKED'
    const missedCount =
        normalizeList(task?.artifacts?.writeback?.director_alignment?.missed).length +
        normalizeList(task?.artifacts?.writeback?.story_alignment?.missed).length

    if (task?.status === 'queued' || task?.status === 'running') {
        return buildSummary({
            tone: 'warning',
            heading: '\u5f53\u524d\u4efb\u52a1\u4ecd\u5728\u6267\u884c',
            continuation: '\u7b49\u5f85\u5b8c\u6210',
            nextStep: task?.runtime_status?.phase_label || task?.current_step || '\u7b49\u5f85\u5f53\u524d\u6b65\u9aa4\u7ed3\u675f',
            summary: task?.runtime_status?.phase_detail || '\u5199\u4f5c\u4e3b\u94fe\u4ecd\u5728\u8fd0\u884c\uff0c\u5efa\u8bae\u7b49\u5f85\u5f53\u524d\u4efb\u52a1\u7ed3\u675f\u540e\u518d\u51b3\u5b9a\u662f\u5426\u7ee7\u7eed\u3002',
            reasons: ['\u4e3b\u94fe\u4efb\u52a1\u4ecd\u5728\u8fd0\u884c', ...contractSignals],
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
            heading: recovery?.heading || '\u7ee7\u7eed\u524d\u9700\u8981\u4eba\u5de5\u5ba1\u6279',
            continuation: recovery?.continuation || '\u7b49\u5f85\u5ba1\u6279',
            nextStep: recovery?.primaryActionLabel || '\u6279\u51c6\u6216\u62d2\u7edd\u56de\u5199',
            summary: '\u6b63\u6587\u5df2\u7ecf\u751f\u6210\u5e76\u505c\u5728 approval-gate\uff0c\u5fc5\u987b\u5148\u5904\u7406\u4eba\u5de5\u5ba1\u6279\u3002',
            reasons: ['\u5f53\u524d write \u4efb\u52a1\u505c\u5728 approval-gate', recovery?.followupLabel, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label || recovery?.primaryActionLabel || '\u6279\u51c6\u6216\u62d2\u7edd\u56de\u5199',
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
            heading: recovery?.heading || '\u7ee7\u7eed\u524d\u5fc5\u987b\u5904\u7406\u5ba1\u67e5\u963b\u65ad',
            continuation: recovery?.continuation || '\u4e0d\u53ef\u7ee7\u7eed',
            nextStep: recovery?.primaryActionLabel || '\u6253\u5f00\u963b\u65ad\u4efb\u52a1\u5e76\u4fee\u590d',
            summary: reviewIssueCount ? `\u5ba1\u67e5\u6458\u8981\u8bb0\u5f55\u4e86 ${reviewIssueCount} \u4e2a\u95ee\u9898\uff0c\u5f53\u524d\u7ae0\u8282\u5c1a\u4e0d\u6ee1\u8db3\u7ee7\u7eed\u63a8\u8fdb\u6761\u4ef6\u3002` : '\u5f53\u524d\u7ae0\u8282\u88ab\u5ba1\u67e5\u5173\u5361\u62e6\u622a\uff0c\u4e0d\u80fd\u76f4\u63a5\u7ee7\u7eed\u4e0b\u4e00\u7ae0\u3002',
            reasons: ['Write \u4efb\u52a1\u88ab\u5ba1\u67e5\u5173\u5361\u62e6\u622a', recovery?.followupLabel, recovery?.reviewSummaryHint, ...contractSignals].filter(Boolean),
            actionLabel: primaryAction?.label,
        })
    }
    if (storyRefresh?.should_refresh) {
        return buildSummary({
            tone: 'warning',
            heading: '\u7ee7\u7eed\u524d\u5efa\u8bae\u5148\u91cd\u89c4\u5212',
            continuation: '\u5efa\u8bae\u6682\u505c',
            nextStep: `\u4ece ${storyRefresh.recommended_resume_from || 'story-director'} \u91cd\u8bd5`,
            summary: storyRefresh.suggested_action || '\u5f53\u524d\u7ae0\u8282\u7684\u5199\u56de\u7ed3\u679c\u5df2\u7ecf\u5efa\u8bae\u5148\u5237\u65b0\u6eda\u52a8\u89c4\u5212\uff0c\u518d\u51b3\u5b9a\u662f\u5426\u7ee7\u7eed\u3002',
            reasons: ['Writeback \u5efa\u8bae Story Refresh', ...contractSignals],
            actionLabel: primaryAction?.label || `\u4ece ${storyRefresh.recommended_resume_from || 'story-director'} \u91cd\u8bd5`,
        })
    }
    if (task?.status === 'completed' && missedCount > 0) {
        return buildSummary({
            tone: 'warning',
            heading: '\u672c\u7ae0\u5df2\u5b8c\u6210\uff0c\u4f46\u5efa\u8bae\u590d\u6838\u540e\u518d\u7ee7\u7eed',
            continuation: '\u5efa\u8bae\u590d\u6838',
            nextStep: '\u67e5\u770b\u5bf9\u9f50\u7ed3\u679c\u540e\u51b3\u5b9a\u662f\u5426\u7ee7\u7eed',
            summary: '\u5f53\u524d\u7ae0\u8282\u5df2\u5b8c\u6210\u5199\u56de\uff0c\u4f46\u4ecd\u5b58\u5728\u672a\u6ee1\u8db3\u7684\u5bfc\u6f14\u6216\u591a\u7ae0\u5408\u540c\u9879\uff0c\u5efa\u8bae\u5148\u4eba\u5de5\u590d\u6838\u3002',
            reasons: contractSignals,
            actionLabel: primaryAction?.label,
        })
    }
    if (task?.status === 'completed') {
        return buildSummary({
            tone: 'success',
            heading: '\u5f53\u524d\u53ef\u7ee7\u7eed\u4e0b\u4e00\u7ae0',
            continuation: '\u53ef\u4ee5\u7ee7\u7eed',
            nextStep: '\u521b\u5efa\u4e0b\u4e00\u7ae0\u5199\u4f5c\u6216\u62a4\u680f\u63a8\u8fdb',
            summary: '\u5f53\u524d\u7ae0\u8282\u5df2\u5b8c\u6210\u5199\u56de\uff0c\u672a\u547d\u4e2d\u65b0\u7684 Story Refresh \u6216\u5ba1\u67e5\u963b\u65ad\uff0c\u53ef\u4ee5\u8fdb\u5165\u4e0b\u4e00\u7ae0\u3002',
            reasons: ['\u5f53\u524d\u7ae0\u8282\u5df2\u5b8c\u6210\u5199\u56de', ...contractSignals],
            actionLabel: primaryAction?.label,
        })
    }
    return buildSummary({
        tone: 'neutral',
        heading: '\u5f53\u524d\u72b6\u6001\u5f85\u4eba\u5de5\u5224\u65ad',
        continuation: '\u5efa\u8bae\u4eba\u5de5\u590d\u6838',
        nextStep: primaryAction?.label || '\u67e5\u770b\u4efb\u52a1\u8be6\u60c5',
        summary: '\u5f53\u524d\u4efb\u52a1\u6ca1\u6709\u547d\u4e2d\u660e\u786e\u7684\u7ee7\u7eed\u6216\u963b\u65ad\u5206\u652f\uff0c\u8bf7\u7ed3\u5408\u4efb\u52a1\u7ed3\u679c\u4eba\u5de5\u5224\u65ad\u3002',
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
