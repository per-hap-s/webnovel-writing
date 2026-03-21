const CANONICAL_OPERATOR_ACTION_KINDS = new Set([
    'open-task',
    'retry-task',
    'launch-task',
    'resume-existing-task',
    'open-blocked-task',
    'complete-noop',
])

function isRecord(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeText(value) {
    return String(value ?? '').trim()
}

function normalizeVariant(value, fallback = 'secondary') {
    const normalized = normalizeText(value)
    return normalized === 'primary' || normalized === 'secondary' ? normalized : fallback
}

function normalizeKind(value) {
    const normalized = normalizeText(value)
    if (normalized === 'retry-story') return 'retry-task'
    if (normalized === 'create-task') return 'launch-task'
    return CANONICAL_OPERATOR_ACTION_KINDS.has(normalized) ? normalized : ''
}

function defaultLabelForAction(action) {
    if (!action) return '执行下一步'
    if (action.kind === 'open-task' || action.kind === 'open-blocked-task') {
        return '查看任务'
    }
    if (action.kind === 'retry-task') {
        return action.resumeFromStep === 'story-director' ? '刷新后续章节规划并重跑本章' : '按当前步骤重跑'
    }
    if (action.kind === 'launch-task') {
        return action.taskType === 'repair' ? '创建局部修稿任务' : '执行下一步'
    }
    if (action.kind === 'resume-existing-task') {
        return '恢复执行'
    }
    if (action.kind === 'complete-noop') {
        return '无需操作'
    }
    return '执行下一步'
}

export function normalizeOperatorAction(action, fallback = {}) {
    if (!isRecord(action)) return null
    const rawKind = normalizeText(action.kind ?? action.type ?? fallback.kind)
    const kind = normalizeKind(rawKind)
    if (!kind) return null

    const normalized = {
        id: normalizeText(action.id || fallback.id || `${kind}:${normalizeText(action.taskId || action.task_type || action.taskType || action.resumeFromStep || action.label || action.actionLabel || 'action')}`),
        kind,
        label: normalizeText(action.label || action.actionLabel || fallback.label) || defaultLabelForAction({ ...action, kind }),
        variant: normalizeVariant(action.variant || fallback.variant),
    }

    const taskId = normalizeText(action.taskId || action.task_id || fallback.taskId)
    const taskType = normalizeText(action.taskType || action.task_type || fallback.taskType)
    const resumeFromStep = normalizeText(action.resumeFromStep || action.resume_from_step || fallback.resumeFromStep || (rawKind === 'retry-story' ? 'story-director' : ''))
    const reason = normalizeText(action.reason || fallback.reason)

    if (taskId) normalized.taskId = taskId
    if (taskType) normalized.taskType = taskType
    if (resumeFromStep) normalized.resumeFromStep = resumeFromStep
    if (reason) normalized.reason = reason
    if (isRecord(action.payload)) {
        normalized.payload = action.payload
    } else if (isRecord(fallback.payload)) {
        normalized.payload = fallback.payload
    }
    if (typeof action.disabled === 'boolean') {
        normalized.disabled = action.disabled
    } else if (typeof fallback.disabled === 'boolean') {
        normalized.disabled = fallback.disabled
    }

    return normalized
}

export function normalizeOperatorActions(actions, fallback = {}) {
    const list = Array.isArray(actions) ? actions : (actions ? [actions] : [])
    return list.map((action, index) => normalizeOperatorAction(action, { ...fallback, id: `${fallback.id || 'operator'}:${index}` })).filter(Boolean)
}

function buildTaskLaunchPayload(task, chapter, taskType) {
    const request = isRecord(task?.request) ? task.request : {}
    if (taskType === 'guarded-batch-write') {
        return {
            start_chapter: Math.max(1, Number(chapter || 0)),
            max_chapters: Math.max(1, Number(request.max_chapters || 1)),
            mode: String(request.mode || 'standard'),
            require_manual_approval: request.require_manual_approval !== false,
            project_root: String(request.project_root || ''),
            options: isRecord(request.options) ? request.options : {},
        }
    }
    return {
        chapter: Math.max(1, Number(chapter || 0)),
        mode: String(request.mode || 'standard'),
        require_manual_approval: request.require_manual_approval !== false,
        project_root: String(request.project_root || ''),
        options: isRecord(request.options) ? request.options : {},
    }
}

function resolveTaskStructuredOutput(task, stepName, artifactKey) {
    const stepResults = task?.artifacts?.step_results || {}
    const stepOutput = stepResults?.[stepName]?.structured_output
    if (isRecord(stepOutput)) return stepOutput
    const artifactOutput = task?.artifacts?.[artifactKey]
    return isRecord(artifactOutput) ? artifactOutput : {}
}

function buildGuardedWriteFallbackActions(task, structuredOutput) {
    const request = isRecord(task?.request) ? task.request : {}
    const chapter = Number(structuredOutput?.chapter || request.chapter || 0)
    const nextAction = isRecord(structuredOutput?.next_action) ? structuredOutput.next_action : {}
    const nextChapter = Math.max(1, Number(nextAction.next_chapter || (chapter > 0 ? chapter + 1 : 1)))
    const guardedPayload = buildTaskLaunchPayload(task, nextChapter, 'guarded-write')
    const writePayload = buildTaskLaunchPayload(task, nextChapter, 'write')
    const currentWritePayload = buildTaskLaunchPayload(task, chapter > 0 ? chapter : nextChapter, 'write')

    if (structuredOutput?.outcome === 'completed_one_chapter') {
        return [
            normalizeOperatorAction({
                id: `guarded-write:continue:${task?.id || nextChapter}`,
                kind: 'launch-task',
                label: '继续护栏推进下一章',
                variant: 'primary',
                taskType: 'guarded-write',
                payload: guardedPayload,
            }),
            normalizeOperatorAction({
                id: `guarded-write:create:${task?.id || nextChapter}`,
                kind: 'launch-task',
                label: '创建下一章常规写作',
                variant: 'secondary',
                taskType: 'write',
                payload: writePayload,
            }),
            normalizeOperatorAction({
                id: `guarded-write:open:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '打开子任务',
                variant: 'secondary',
                taskId: structuredOutput?.child_task_id || task?.id || '',
            }),
        ].filter(Boolean)
    }

    if (structuredOutput?.outcome === 'blocked_story_refresh') {
        return [
            normalizeOperatorAction({
                id: `guarded-write:retry:${task?.id || nextChapter}`,
                kind: 'retry-task',
                label: '刷新后续章节规划并重跑本章',
                variant: 'primary',
                taskId: task?.id || '',
                resumeFromStep: 'story-director',
            }),
            normalizeOperatorAction({
                id: `guarded-write:create-current:${task?.id || nextChapter}`,
                kind: 'launch-task',
                label: '创建当前章常规写作',
                variant: 'secondary',
                taskType: 'write',
                payload: currentWritePayload,
            }),
            normalizeOperatorAction({
                id: `guarded-write:open:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '打开子任务',
                variant: 'secondary',
                taskId: structuredOutput?.child_task_id || task?.id || '',
            }),
        ].filter(Boolean)
    }

    if (structuredOutput?.outcome === 'blocked_by_review') {
        return normalizeOperatorActions([
            {
                id: `guarded-write:open-review:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '打开阻塞子任务',
                variant: 'primary',
                taskId: structuredOutput?.child_task_id || task?.id || '',
            },
        ])
    }

    if (structuredOutput?.outcome === 'stopped_for_approval') {
        return normalizeOperatorActions([
            {
                id: `guarded-write:open-approval:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '打开待审批子任务',
                variant: 'primary',
                taskId: structuredOutput?.child_task_id || task?.id || '',
            },
        ])
    }

    if (nextAction.can_enqueue_next) {
        return [
            normalizeOperatorAction({
                id: `guarded-write:continue:${task?.id || nextChapter}`,
                kind: 'launch-task',
                label: '继续护栏推进下一章',
                variant: 'primary',
                taskType: 'guarded-write',
                payload: guardedPayload,
            }),
            normalizeOperatorAction({
                id: `guarded-write:create:${task?.id || nextChapter}`,
                kind: 'launch-task',
                label: '创建下一章常规写作',
                variant: 'secondary',
                taskType: 'write',
                payload: writePayload,
            }),
        ].filter(Boolean)
    }

    return []
}

function buildGuardedBatchFallbackActions(task, structuredOutput) {
    const request = isRecord(task?.request) ? task.request : {}
    const startChapter = Number(structuredOutput?.start_chapter || request.start_chapter || request.chapter || 0)
    const nextAction = isRecord(structuredOutput?.next_action) ? structuredOutput.next_action : {}
    const nextChapter = Math.max(1, Number(nextAction.next_chapter || (startChapter > 0 ? startChapter + Math.max(1, Number(structuredOutput?.completed_chapters || 1)) : 1)))
    const batchPayload = buildTaskLaunchPayload(task, nextChapter, 'guarded-batch-write')

    if (structuredOutput?.outcome === 'completed_requested_batch') {
        return [
            normalizeOperatorAction({
                id: `guarded-batch:continue:${task?.id || nextChapter}`,
                kind: 'launch-task',
                label: '继续下一批护栏推进',
                variant: 'primary',
                taskType: 'guarded-batch-write',
                payload: batchPayload,
            }),
            normalizeOperatorAction({
                id: `guarded-batch:open-last:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '查看最后子任务',
                variant: 'secondary',
                taskId: structuredOutput?.last_child_task_id || task?.id || '',
            }),
        ].filter(Boolean)
    }

    if (structuredOutput?.outcome === 'blocked_story_refresh') {
        return [
            normalizeOperatorAction({
                id: `guarded-batch:open-last:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '打开最后子任务',
                variant: 'primary',
                taskId: structuredOutput?.last_child_task_id || task?.id || '',
            }),
            normalizeOperatorAction({
                id: `guarded-batch:retry-last:${task?.id || nextChapter}`,
                kind: 'retry-task',
                label: '刷新后续章节规划并重跑最后子任务',
                variant: 'secondary',
                taskId: structuredOutput?.last_child_task_id || task?.id || '',
                resumeFromStep: 'story-director',
            }),
        ].filter(Boolean)
    }

    if (structuredOutput?.outcome === 'blocked_by_review') {
        return normalizeOperatorActions([
            {
                id: `guarded-batch:open-review:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '打开最后子任务',
                variant: 'primary',
                taskId: structuredOutput?.last_child_task_id || task?.id || '',
            },
        ])
    }

    if (structuredOutput?.outcome === 'stopped_for_approval') {
        return normalizeOperatorActions([
            {
                id: `guarded-batch:open-approval:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '打开最后子任务',
                variant: 'primary',
                taskId: structuredOutput?.last_child_task_id || task?.id || '',
            },
        ])
    }

    if (structuredOutput?.outcome === 'child_task_failed') {
        return normalizeOperatorActions([
            {
                id: `guarded-batch:open-failed:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '打开失败子任务',
                variant: 'primary',
                taskId: structuredOutput?.last_child_task_id || task?.id || '',
            },
        ])
    }

    if (nextAction.can_enqueue_next) {
        return [
            normalizeOperatorAction({
                id: `guarded-batch:continue:${task?.id || nextChapter}`,
                kind: 'launch-task',
                label: '继续下一批护栏推进',
                variant: 'primary',
                taskType: 'guarded-batch-write',
                payload: batchPayload,
            }),
            normalizeOperatorAction({
                id: `guarded-batch:open-last:${task?.id || nextChapter}`,
                kind: 'open-task',
                label: '查看最后子任务',
                variant: 'secondary',
                taskId: structuredOutput?.last_child_task_id || task?.id || '',
            }),
        ].filter(Boolean)
    }

    return []
}

function buildResumeFallbackActions(structuredOutput) {
    if (!isRecord(structuredOutput?.resume_action)) return []
    return normalizeOperatorActions([structuredOutput.resume_action])
}

export function resolveTaskOperatorActions(task) {
    const taskType = normalizeText(task?.task_type)
    if (!taskType) return []

    if (taskType === 'guarded-write') {
        const structuredOutput = resolveTaskStructuredOutput(task, 'guarded-chapter-runner', 'guarded_runner')
        const directActions = normalizeOperatorActions(structuredOutput?.operator_actions)
        return directActions.length ? directActions : buildGuardedWriteFallbackActions(task, structuredOutput)
    }

    if (taskType === 'guarded-batch-write') {
        const structuredOutput = resolveTaskStructuredOutput(task, 'guarded-batch-runner', 'guarded_batch_runner')
        const directActions = normalizeOperatorActions(structuredOutput?.operator_actions)
        return directActions.length ? directActions : buildGuardedBatchFallbackActions(task, structuredOutput)
    }

    if (taskType === 'resume') {
        const structuredOutput = resolveTaskStructuredOutput(task, 'resume', 'resume')
        const directActions = normalizeOperatorActions(structuredOutput?.operator_actions)
        if (directActions.length) return directActions
        return buildResumeFallbackActions(structuredOutput)
    }

    const structuredOutputs = Object.values(task?.artifacts?.step_results || {})
        .map((item) => item?.structured_output)
        .filter(isRecord)
    for (const structuredOutput of structuredOutputs) {
        const directActions = normalizeOperatorActions(structuredOutput.operator_actions)
        if (directActions.length) return directActions
    }

    return []
}

export function resolveSupervisorItemOperatorActions(item) {
    if (!isRecord(item)) return []
    const directActions = normalizeOperatorActions(item.operator_actions)
    if (directActions.length) return directActions
    const legacyActions = []
    if (isRecord(item.action)) {
        legacyActions.push(normalizeOperatorAction(item.action, { label: item.actionLabel, variant: item.action.variant }))
    }
    if (isRecord(item.secondaryAction)) {
        legacyActions.push(normalizeOperatorAction(item.secondaryAction, { label: item.secondaryLabel, variant: item.secondaryAction.variant || 'secondary' }))
    }
    const normalizedLegacyActions = legacyActions.filter(Boolean)
    if (normalizedLegacyActions.length) return normalizedLegacyActions
    return []
}
