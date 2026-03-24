import test from 'node:test'
import assert from 'node:assert/strict'

import { buildWritingTaskListSummary, supportsWritingTaskContinuation } from './writingTaskListSummary.js'
import { WRITING_CONTINUATION } from './writingTaskCopy.js'

test('buildWritingTaskListSummary exposes primary action for continuable write tasks', () => {
    const task = {
        task_type: 'write',
        status: 'completed',
        request: { chapter: 8 },
        artifacts: {
            writeback: {
                story_alignment: { satisfied: ['mainline'], missed: [], deferred: [] },
                director_alignment: { satisfied: ['hook'], missed: [], deferred: [] },
            },
        },
        operatorActions: [{ kind: 'launch-task', label: 'Continue chapter 9', variant: 'primary', taskType: 'write', payload: { chapter: 9 } }],
    }

    const summary = buildWritingTaskListSummary({ task })

    assert.equal(summary.continuationLabel, WRITING_CONTINUATION.continuable)
    assert.equal(summary.blockedKind, 'continuable')
    assert.equal(summary.primaryAction.kind, 'launch-task')
    assert.equal(summary.isContinuable, true)
    assert.ok(summary.primaryActionLabel.length > 0)
})

test('buildWritingTaskListSummary marks guarded review blocks as review-blocked and keeps open action', () => {
    const task = {
        task_type: 'guarded-write',
        status: 'completed',
        artifacts: {
            guarded_runner: {
                outcome: 'blocked_by_review',
                review_summary: {
                    issues: [{ title: 'pace slip' }],
                },
            },
        },
        operatorActions: [{ kind: 'open-task', label: 'Open blocked child task', variant: 'primary', taskId: 'child-1' }],
    }

    const summary = buildWritingTaskListSummary({ task })

    assert.equal(summary.continuationLabel, WRITING_CONTINUATION.blocked)
    assert.equal(summary.blockedKind, 'review')
    assert.equal(summary.primaryAction.kind, 'open-task')
    assert.ok(summary.primaryActionLabel.length > 0)
    assert.match(summary.reasonLabel, /1/)
})

test('buildWritingTaskListSummary marks approval and story refresh states with actionable primary actions', () => {
    const approvalTask = {
        task_type: 'write',
        status: 'awaiting_writeback_approval',
        request: { chapter: 9, require_manual_approval: true },
        operatorActions: [{ kind: 'open-task', label: 'Open approval task', variant: 'primary', taskId: 'task-9' }],
        artifacts: { writeback: {} },
    }
    const refreshTask = {
        task_type: 'write',
        status: 'completed',
        artifacts: {
            writeback: {
                story_alignment: { satisfied: [], missed: [], deferred: [] },
                director_alignment: { satisfied: [], missed: [], deferred: [] },
                story_refresh: {
                    should_refresh: true,
                    recommended_resume_from: 'chapter-director',
                    suggested_action: 'refresh before continuing',
                },
            },
        },
        operatorActions: [{ kind: 'retry-task', label: 'Retry from chapter-director', variant: 'primary', taskId: 'task-10', resumeFromStep: 'chapter-director' }],
    }

    const approvalSummary = buildWritingTaskListSummary({ task: approvalTask })
    const refreshSummary = buildWritingTaskListSummary({ task: refreshTask })

    assert.equal(approvalSummary.blockedKind, 'approval')
    assert.equal(approvalSummary.primaryAction.kind, 'open-task')
    assert.equal(refreshSummary.blockedKind, 'story-refresh')
    assert.equal(refreshSummary.primaryAction.kind, 'retry-task')
})

test('buildWritingTaskListSummary suppresses noop actions as executable primary CTA', () => {
    const task = {
        task_type: 'resume',
        status: 'completed',
        artifacts: { resume: { blocking_reason: 'nothing to resume' } },
        operatorActions: [{ kind: 'complete-noop', label: 'No action needed', variant: 'primary' }],
    }

    const summary = buildWritingTaskListSummary({ task })

    assert.equal(summary.continuationLabel, WRITING_CONTINUATION.noop)
    assert.equal(summary.blockedKind, 'noop')
    assert.equal(summary.primaryAction, null)
    assert.equal(summary.primaryActionLabel, '')
})

test('buildWritingTaskListSummary keeps disabled primary actions for read-only CTA projection', () => {
    const task = {
        task_type: 'resume',
        status: 'failed',
        artifacts: { resume: { blocking_reason: 'target task missing' } },
        operatorActions: [{ kind: 'open-blocked-task', label: 'Open blocked task', variant: 'primary', disabled: true, reason: 'missing target_task_id' }],
    }

    const summary = buildWritingTaskListSummary({ task })

    assert.equal(summary.primaryAction.kind, 'open-blocked-task')
    assert.equal(summary.primaryAction.disabled, true)
    assert.equal(summary.primaryActionLabel, summary.primaryAction.label)
    assert.ok(summary.primaryActionLabel.length > 0)
})

test('buildWritingTaskListSummary marks batch child failure separately from generic blocked state', () => {
    const task = {
        task_type: 'guarded-batch-write',
        status: 'completed',
        artifacts: {
            guarded_batch_runner: {
                outcome: 'child_task_failed',
            },
        },
        operatorActions: [{ kind: 'open-task', label: 'Open failed child task', variant: 'primary', taskId: 'child-2' }],
    }

    const summary = buildWritingTaskListSummary({ task })

    assert.equal(summary.blockedKind, 'child-task-failed')
    assert.equal(summary.primaryAction.kind, 'open-task')
    assert.match(summary.detailSummary, /child|fail|子任务|失败/i)
})

test('supportsWritingTaskContinuation only accepts write mainline task types', () => {
    assert.equal(supportsWritingTaskContinuation({ task_type: 'write' }), true)
    assert.equal(supportsWritingTaskContinuation({ task_type: 'guarded-write' }), true)
    assert.equal(supportsWritingTaskContinuation({ task_type: 'guarded-batch-write' }), true)
    assert.equal(supportsWritingTaskContinuation({ task_type: 'resume' }), true)
    assert.equal(supportsWritingTaskContinuation({ task_type: 'plan' }), false)
    assert.equal(buildWritingTaskListSummary({ task: { task_type: 'plan' } }), null)
})
