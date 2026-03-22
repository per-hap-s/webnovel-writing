import { normalizeOperatorActions, resolveTaskOperatorActions } from './operatorAction.js'

function isRecord(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

export function normalizeAlignment(value) {
    const alignment = isRecord(value) ? value : {}
    return {
        satisfied: Array.isArray(alignment.satisfied) ? alignment.satisfied : [],
        missed: Array.isArray(alignment.missed) ? alignment.missed : [],
        deferred: Array.isArray(alignment.deferred) ? alignment.deferred : [],
    }
}

export function normalizeStoryRefresh(value) {
    if (!isRecord(value)) return null
    return {
        should_refresh: Boolean(value.should_refresh),
        recommended_resume_from: value.recommended_resume_from || null,
        reasons: Array.isArray(value.reasons) ? value.reasons : [],
        reason_codes: Array.isArray(value.reason_codes) ? value.reason_codes : [],
        consecutive_missed_chapters: Number(value.consecutive_missed_chapters || 0),
        current_missed_count: Number(value.current_missed_count || 0),
        current_satisfied_count: Number(value.current_satisfied_count || 0),
        current_deferred_count: Number(value.current_deferred_count || 0),
        suggested_action: value.suggested_action || '',
    }
}

export function resolveStoryPlan(task) {
    const stepResults = task?.artifacts?.step_results || {}
    const storyStep = stepResults['story-director']?.structured_output
    if (isRecord(storyStep)) return storyStep
    const contextStoryPlan = stepResults.context?.structured_output?.story_plan
    if (isRecord(contextStoryPlan) && Object.keys(contextStoryPlan).length > 0) return contextStoryPlan
    return null
}

export function resolveDirectorBrief(task) {
    const stepResults = task?.artifacts?.step_results || {}
    const directorStep = stepResults['chapter-director']?.structured_output
    if (isRecord(directorStep)) return directorStep
    const contextDirectorBrief = stepResults.context?.structured_output?.director_brief
    if (isRecord(contextDirectorBrief) && Object.keys(contextDirectorBrief).length > 0) return contextDirectorBrief
    return null
}

export function resolveGuardedRunnerResult(task) {
    const stepResults = task?.artifacts?.step_results || {}
    const guardedStep = stepResults['guarded-chapter-runner']?.structured_output
    if (isRecord(guardedStep)) return guardedStep
    const guardedArtifact = task?.artifacts?.guarded_runner
    if (isRecord(guardedArtifact)) return guardedArtifact
    return null
}

export function resolveGuardedBatchRunnerResult(task) {
    const stepResults = task?.artifacts?.step_results || {}
    const guardedStep = stepResults['guarded-batch-runner']?.structured_output
    if (isRecord(guardedStep)) return guardedStep
    const guardedArtifact = task?.artifacts?.guarded_batch_runner
    if (isRecord(guardedArtifact)) return guardedArtifact
    return null
}

export function resolveResumeResult(task) {
    const stepResults = task?.artifacts?.step_results || {}
    const resumeStep = stepResults.resume?.structured_output
    if (isRecord(resumeStep)) return resumeStep
    const resumeArtifact = task?.artifacts?.resume
    if (isRecord(resumeArtifact)) return resumeArtifact
    return null
}

export function resolveStoryPlanSlot(storyPlan, chapter) {
    if (!storyPlan || !Array.isArray(storyPlan.chapters)) return null
    return storyPlan.chapters.find((item) => Number(item?.chapter || 0) === Number(chapter || 0)) || null
}

export function deriveWritingTaskContext(task, { operatorActions = null } = {}) {
    const storyPlan = resolveStoryPlan(task)
    const writeback = task?.artifacts?.writeback || {}
    const normalizedProvidedActions = normalizeOperatorActions(operatorActions)
    const normalizedTaskActions = normalizeOperatorActions(task?.operatorActions)
    const resolvedOperatorActions = normalizedProvidedActions.length
        ? normalizedProvidedActions
        : normalizedTaskActions.length
            ? normalizedTaskActions
            : resolveTaskOperatorActions(task)
    return {
        storyPlan,
        directorBrief: resolveDirectorBrief(task),
        storyAlignment: normalizeAlignment(writeback.story_alignment),
        directorAlignment: normalizeAlignment(writeback.director_alignment),
        storyRefresh: normalizeStoryRefresh(writeback.story_refresh || task?.artifacts?.story_refresh),
        guardedRun: resolveGuardedRunnerResult(task),
        guardedBatchRun: resolveGuardedBatchRunnerResult(task),
        resumeRun: resolveResumeResult(task),
        operatorActions: resolvedOperatorActions,
        currentStorySlot: resolveStoryPlanSlot(storyPlan, Number(task?.request?.chapter || 0)),
    }
}
