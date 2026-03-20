import test from 'node:test'
import assert from 'node:assert/strict'

import { buildWritingTaskListSummary, supportsWritingTaskContinuation } from './writingTaskListSummary.js'

test('buildWritingTaskListSummary compresses continuable write summary without changing primary action label', () => {
    const task = {
        task_type: 'write',
        status: 'completed',
        request: { chapter: 8 },
        artifacts: {
            writeback: {
                story_alignment: { satisfied: ['主线推进'], missed: [], deferred: [] },
                director_alignment: { satisfied: ['兑现钩子'], missed: [], deferred: [] },
            },
        },
        operatorActions: [{ kind: 'launch-task', label: '继续第 9 章', variant: 'primary', taskType: 'write', payload: { chapter: 9 } }],
    }

    const summary = buildWritingTaskListSummary({ task })

    assert.equal(summary.continuationLabel, '可以继续')
    assert.equal(summary.blockedKind, 'continuable')
    assert.equal(summary.primaryActionLabel, '继续第 9 章')
    assert.equal(summary.isContinuable, true)
})

test('buildWritingTaskListSummary marks guarded review blocks as review-blocked', () => {
    const task = {
        task_type: 'guarded-write',
        status: 'completed',
        artifacts: {
            guarded_runner: {
                outcome: 'blocked_by_review',
                review_summary: {
                    issues: [{ title: '节奏失衡' }],
                },
            },
        },
        operatorActions: [{ kind: 'open-task', label: '打开阻断子任务', variant: 'primary', taskId: 'child-1' }],
    }

    const summary = buildWritingTaskListSummary({ task })

    assert.equal(summary.continuationLabel, '不可继续')
    assert.equal(summary.blockedKind, 'review')
    assert.equal(summary.primaryActionLabel, '打开阻断子任务')
    assert.match(summary.reasonLabel, /记录了 1 个问题/)
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
        operatorActions: [{ kind: 'open-task', label: '打开失败子任务', variant: 'primary', taskId: 'child-2' }],
    }

    const summary = buildWritingTaskListSummary({ task })

    assert.equal(summary.blockedKind, 'child-task-failed')
    assert.equal(summary.primaryActionLabel, '打开失败子任务')
    assert.match(summary.detailSummary, /子任务失败停止/)
})

test('supportsWritingTaskContinuation only accepts write mainline task types', () => {
    assert.equal(supportsWritingTaskContinuation({ task_type: 'write' }), true)
    assert.equal(supportsWritingTaskContinuation({ task_type: 'guarded-write' }), true)
    assert.equal(supportsWritingTaskContinuation({ task_type: 'guarded-batch-write' }), true)
    assert.equal(supportsWritingTaskContinuation({ task_type: 'resume' }), true)
    assert.equal(supportsWritingTaskContinuation({ task_type: 'plan' }), false)
    assert.equal(buildWritingTaskListSummary({ task: { task_type: 'plan' } }), null)
})
