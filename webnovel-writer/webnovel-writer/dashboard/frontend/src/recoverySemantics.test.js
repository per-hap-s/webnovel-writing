import test from 'node:test'
import assert from 'node:assert/strict'

import {
    inferRecoveryKindFromSupervisorItem,
    inferRecoveryKindFromTask,
    resolveRecoverySemantics,
    resolveSupervisorRecoverySemantics,
} from './recoverySemantics.js'

test('resolveRecoverySemantics returns canonical review guidance for write surface', () => {
    const semantics = resolveRecoverySemantics({ recoveryKind: 'review', surface: 'write', hasReviewSummary: true })

    assert.equal(semantics.label, '审查阻断')
    assert.equal(semantics.primaryActionLabel, '打开阻断任务')
    assert.equal(semantics.followupLabel, '先修复审查问题再继续')
    assert.match(semantics.reviewSummaryHint, /review_summary/)
})

test('resolveRecoverySemantics returns guarded approval guidance for child surface', () => {
    const semantics = resolveRecoverySemantics({ recoveryKind: 'approval', surface: 'guarded-child' })

    assert.equal(semantics.label, '人工审批')
    assert.equal(semantics.primaryActionLabel, '打开待审批子任务')
    assert.equal(semantics.followupLabel, '完成审批后再返回父流程')
})

test('inferRecoveryKindFromSupervisorItem detects approval and review categories', () => {
    assert.equal(inferRecoveryKindFromSupervisorItem({ category: 'approval' }), 'approval')
    assert.equal(inferRecoveryKindFromSupervisorItem({ category: 'review_block' }), 'review')
    assert.equal(inferRecoveryKindFromSupervisorItem({ category: 'guarded_continue' }), '')
})

test('resolveSupervisorRecoverySemantics derives review guidance from supervisor items', () => {
    const semantics = resolveSupervisorRecoverySemantics({
        category: 'review_block',
        review_summary: { issues: [{ title: 'blocking issue' }] },
    })
    const canonical = resolveRecoverySemantics({ recoveryKind: 'review', surface: 'write', hasReviewSummary: true })

    assert.equal(semantics.label, canonical.label)
    assert.equal(semantics.primaryActionLabel, canonical.primaryActionLabel)
    assert.match(semantics.reviewSummaryHint, /review_summary/)
})

test('inferRecoveryKindFromTask detects write and guarded blocking states', () => {
    assert.equal(inferRecoveryKindFromTask({ status: 'awaiting_writeback_approval' }), 'approval')
    assert.equal(inferRecoveryKindFromTask({ error: { code: 'REVIEW_GATE_BLOCKED' } }), 'review')
    assert.equal(inferRecoveryKindFromTask({}, { guardedOutcome: 'blocked_by_review' }), 'review')
    assert.equal(inferRecoveryKindFromTask({}, { guardedOutcome: 'stopped_for_approval' }), 'approval')
})
