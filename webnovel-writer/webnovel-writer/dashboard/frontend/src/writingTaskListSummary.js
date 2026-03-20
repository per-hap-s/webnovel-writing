import { buildTaskContinuationSummary } from './writingContinuation.js'
import { deriveWritingTaskContext } from './writingTaskDerived.js'

const WRITING_MAINLINE_TASK_TYPES = new Set(['write', 'guarded-write', 'guarded-batch-write', 'resume'])

export function supportsWritingTaskContinuation(task) {
    return WRITING_MAINLINE_TASK_TYPES.has(String(task?.task_type || '').trim())
}

function resolveBlockedKind(task, derived, detailSummary) {
    if (detailSummary.continuation === '可以继续') return 'continuable'
    if (detailSummary.continuation === '无需操作') return 'noop'
    if (task?.status === 'awaiting_writeback_approval' || derived.guardedRun?.outcome === 'stopped_for_approval' || derived.guardedBatchRun?.outcome === 'stopped_for_approval') {
        return 'approval'
    }
    if (derived.storyRefresh?.should_refresh || derived.guardedRun?.outcome === 'blocked_story_refresh' || derived.guardedBatchRun?.outcome === 'blocked_story_refresh') {
        return 'story-refresh'
    }
    if (String(task?.error?.code || '').trim() === 'REVIEW_GATE_BLOCKED' || derived.guardedRun?.outcome === 'blocked_by_review' || derived.guardedBatchRun?.outcome === 'blocked_by_review') {
        return 'review'
    }
    if (derived.guardedBatchRun?.outcome === 'child_task_failed') {
        return 'child-task-failed'
    }
    if (detailSummary.continuation === '等待审批') return 'approval'
    if (detailSummary.continuation === '等待完成' || detailSummary.continuation === '等待恢复完成') return 'running'
    if (detailSummary.continuation === '不可继续') return 'blocked'
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

    const primaryActionLabel = detailSummary.actionLabel && detailSummary.actionLabel !== '-' ? detailSummary.actionLabel : ''
    return {
        ...detailSummary,
        detailSummary: detailSummary.summary,
        continuationLabel: detailSummary.continuation,
        reasonLabel: detailSummary.summary || detailSummary.reasons[0] || '-',
        primaryActionLabel,
        blockedKind: resolveBlockedKind(task, resolved, detailSummary),
        isContinuable: detailSummary.continuation === '可以继续',
    }
}
