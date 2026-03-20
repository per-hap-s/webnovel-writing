import { buildTaskContinuationSummary } from './writingContinuation.js'
import { WRITING_CONTINUATION } from './writingTaskCopy.js'
import { deriveWritingTaskContext } from './writingTaskDerived.js'

const WRITING_MAINLINE_TASK_TYPES = new Set(['write', 'guarded-write', 'guarded-batch-write', 'resume'])

export function supportsWritingTaskContinuation(task) {
    return WRITING_MAINLINE_TASK_TYPES.has(String(task?.task_type || '').trim())
}

function resolvePrimaryAction(actions) {
    if (!Array.isArray(actions) || actions.length === 0) return null
    const action = actions.find((item) => item?.variant === 'primary') || actions[0] || null
    if (!action || action.kind === 'complete-noop') return null
    return action
}

function resolveBlockedKind(task, derived, detailSummary) {
    if (detailSummary.continuation === WRITING_CONTINUATION.continuable) return 'continuable'
    if (detailSummary.continuation === WRITING_CONTINUATION.noop) return 'noop'
    if (
        task?.status === 'awaiting_writeback_approval'
        || derived.guardedRun?.outcome === 'stopped_for_approval'
        || derived.guardedBatchRun?.outcome === 'stopped_for_approval'
    ) {
        return 'approval'
    }
    if (
        derived.storyRefresh?.should_refresh
        || derived.guardedRun?.outcome === 'blocked_story_refresh'
        || derived.guardedBatchRun?.outcome === 'blocked_story_refresh'
    ) {
        return 'story-refresh'
    }
    if (
        String(task?.error?.code || '').trim() === 'REVIEW_GATE_BLOCKED'
        || derived.guardedRun?.outcome === 'blocked_by_review'
        || derived.guardedBatchRun?.outcome === 'blocked_by_review'
    ) {
        return 'review'
    }
    if (derived.guardedBatchRun?.outcome === 'child_task_failed') {
        return 'child-task-failed'
    }
    if (detailSummary.continuation === WRITING_CONTINUATION.waitingApproval) return 'approval'
    if (
        detailSummary.continuation === WRITING_CONTINUATION.waitingCompletion
        || detailSummary.continuation === WRITING_CONTINUATION.waitingResumeCompletion
    ) {
        return 'running'
    }
    if (detailSummary.continuation === WRITING_CONTINUATION.blocked) return 'blocked'
    return 'neutral'
}

export function buildWritingTaskListSummary({ task, derived = null } = {}) {
    if (!supportsWritingTaskContinuation(task)) return null

    const resolved = derived || deriveWritingTaskContext(task)
    const detailSummary = buildTaskContinuationSummary({
        task,
        storyPlan: resolved.storyPlan,
        directorBrief: resolved.directorBrief,
        storyAlignment: resolved.storyAlignment,
        directorAlignment: resolved.directorAlignment,
        storyRefresh: resolved.storyRefresh,
        guardedRun: resolved.guardedRun,
        guardedBatchRun: resolved.guardedBatchRun,
        resumeRun: resolved.resumeRun,
        operatorActions: resolved.operatorActions,
    })
    const primaryAction = resolvePrimaryAction(resolved.operatorActions)

    return {
        ...detailSummary,
        detailSummary: detailSummary.summary,
        continuationLabel: detailSummary.continuation,
        reasonLabel: detailSummary.summary || detailSummary.reasons[0] || '-',
        primaryAction,
        primaryActionLabel: primaryAction?.label || '',
        blockedKind: resolveBlockedKind(task, resolved, detailSummary),
        isContinuable: detailSummary.continuation === WRITING_CONTINUATION.continuable,
    }
}
