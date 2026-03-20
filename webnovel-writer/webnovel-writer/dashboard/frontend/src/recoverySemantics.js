function normalizeText(value) {
    return String(value ?? '').trim()
}

function buildReviewSemantics(surface, { hasReviewSummary = false } = {}) {
    if (surface === 'guarded-child') {
        return {
            kind: 'review',
            label: '\u5ba1\u67e5\u963b\u65ad',
            heading: '\u7ee7\u7eed\u524d\u5fc5\u987b\u5904\u7406\u5ba1\u67e5\u963b\u65ad',
            continuation: '\u4e0d\u53ef\u7ee7\u7eed',
            primaryActionLabel: '\u6253\u5f00\u963b\u65ad\u5b50\u4efb\u52a1',
            followupLabel: '\u5148\u5728\u5b50\u4efb\u52a1\u4e2d\u5904\u7406\u5ba1\u67e5\u95ee\u9898',
            reviewSummaryHint: hasReviewSummary ? '\u6253\u5f00\u963b\u65ad\u5b50\u4efb\u52a1\u540e\u67e5\u770b review_summary' : '',
        }
    }
    if (surface === 'guarded-batch-child') {
        return {
            kind: 'review',
            label: '\u5ba1\u67e5\u963b\u65ad',
            heading: '\u7ee7\u7eed\u524d\u5fc5\u987b\u5904\u7406\u5ba1\u67e5\u963b\u65ad',
            continuation: '\u4e0d\u53ef\u7ee7\u7eed',
            primaryActionLabel: '\u6253\u5f00\u6700\u540e\u5b50\u4efb\u52a1',
            followupLabel: '\u5148\u5904\u7406\u6700\u540e\u5b50\u4efb\u52a1\u7684\u5ba1\u67e5\u95ee\u9898',
            reviewSummaryHint: hasReviewSummary ? '\u6253\u5f00\u6700\u540e\u5b50\u4efb\u52a1\u540e\u67e5\u770b review_summary' : '',
        }
    }
    return {
        kind: 'review',
        label: '\u5ba1\u67e5\u963b\u65ad',
        heading: '\u7ee7\u7eed\u524d\u5fc5\u987b\u5904\u7406\u5ba1\u67e5\u963b\u65ad',
        continuation: '\u4e0d\u53ef\u7ee7\u7eed',
        primaryActionLabel: '\u6253\u5f00\u963b\u65ad\u4efb\u52a1',
        followupLabel: '\u5148\u4fee\u590d\u5ba1\u67e5\u95ee\u9898\u518d\u7ee7\u7eed',
        reviewSummaryHint: hasReviewSummary ? '\u6253\u5f00\u963b\u65ad\u4efb\u52a1\u540e\u67e5\u770b review_summary' : '',
    }
}

function buildApprovalSemantics(surface) {
    if (surface === 'guarded-child') {
        return {
            kind: 'approval',
            label: '\u4eba\u5de5\u5ba1\u6279',
            heading: '\u7ee7\u7eed\u524d\u9700\u8981\u4eba\u5de5\u5ba1\u6279',
            continuation: '\u7b49\u5f85\u5ba1\u6279',
            primaryActionLabel: '\u6253\u5f00\u5f85\u5ba1\u6279\u5b50\u4efb\u52a1',
            followupLabel: '\u5b8c\u6210\u5ba1\u6279\u540e\u518d\u8fd4\u56de\u7236\u6d41\u7a0b',
            reviewSummaryHint: '',
        }
    }
    if (surface === 'guarded-batch-child') {
        return {
            kind: 'approval',
            label: '\u4eba\u5de5\u5ba1\u6279',
            heading: '\u7ee7\u7eed\u524d\u9700\u8981\u4eba\u5de5\u5ba1\u6279',
            continuation: '\u7b49\u5f85\u5ba1\u6279',
            primaryActionLabel: '\u6253\u5f00\u6700\u540e\u5b50\u4efb\u52a1',
            followupLabel: '\u5b8c\u6210\u5ba1\u6279\u540e\u518d\u51b3\u5b9a\u662f\u5426\u7ee7\u7eed\u672c\u6279',
            reviewSummaryHint: '',
        }
    }
    return {
        kind: 'approval',
        label: '\u4eba\u5de5\u5ba1\u6279',
        heading: '\u7ee7\u7eed\u524d\u9700\u8981\u4eba\u5de5\u5ba1\u6279',
        continuation: '\u7b49\u5f85\u5ba1\u6279',
        primaryActionLabel: '\u6253\u5f00\u5f85\u5ba1\u6279\u4efb\u52a1',
        followupLabel: '\u5b8c\u6210\u5ba1\u6279\u540e\u6062\u590d\u7236\u6d41\u7a0b',
        reviewSummaryHint: '',
    }
}

export function resolveRecoverySemantics({ recoveryKind = '', surface = 'write', hasReviewSummary = false } = {}) {
    const kind = normalizeText(recoveryKind)
    if (kind === 'review') {
        return buildReviewSemantics(surface, { hasReviewSummary })
    }
    if (kind === 'approval') {
        return buildApprovalSemantics(surface)
    }
    return null
}

export function resolveSupervisorRecoverySemantics(item, surface = 'write') {
    const recoveryKind = inferRecoveryKindFromSupervisorItem(item)
    if (!recoveryKind) return null
    return resolveRecoverySemantics({
        recoveryKind,
        surface,
        hasReviewSummary: Boolean(item?.reviewSummary || item?.review_summary || item?.reviewSummaryHint),
    })
}

export function inferRecoveryKindFromSupervisorItem(item) {
    const category = normalizeText(item?.category)
    if (category === 'approval') return 'approval'
    if (category === 'review_block') return 'review'
    return ''
}

export function inferRecoveryKindFromTask(task, { guardedOutcome = '' } = {}) {
    const outcome = normalizeText(guardedOutcome)
    if (outcome === 'blocked_by_review') return 'review'
    if (outcome === 'stopped_for_approval') return 'approval'
    const status = normalizeText(task?.status)
    const errorCode = normalizeText(task?.error?.code)
    if (status === 'awaiting_writeback_approval') return 'approval'
    if (errorCode === 'REVIEW_GATE_BLOCKED') return 'review'
    return ''
}
