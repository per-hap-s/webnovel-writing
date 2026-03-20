import test from 'node:test'
import assert from 'node:assert/strict'

import { buildTaskContinuationSummary } from './writingContinuation.js'

test('completed write task is marked ready to continue when no blockers remain', () => {
    const summary = buildTaskContinuationSummary({
        task: {
            task_type: 'write',
            status: 'completed',
            artifacts: {
                writeback: {
                    story_alignment: { satisfied: ['主线推进'], missed: [], deferred: [] },
                    director_alignment: { satisfied: ['兑现钩子'], missed: [], deferred: [] },
                },
            },
        },
        storyPlan: { anchor_chapter: 10 },
        directorBrief: { chapter_goal: '推进主线' },
        storyAlignment: { satisfied: ['主线推进'], missed: [], deferred: [] },
        directorAlignment: { satisfied: ['兑现钩子'], missed: [], deferred: [] },
        storyRefresh: null,
        guardedRun: null,
        guardedBatchRun: null,
        resumeRun: null,
        operatorActions: [],
    })

    assert.equal(summary.heading, '当前可继续下一章')
    assert.equal(summary.continuation, '可以继续')
    assert.match(summary.summary, /已完成写回/)
    assert(summary.reasons.includes('已接入 Story Director 多章规划'))
    assert(summary.reasons.includes('已接入 Chapter Director 单章合同'))
})

test('write task with story refresh is marked as requiring replanning', () => {
    const summary = buildTaskContinuationSummary({
        task: {
            task_type: 'write',
            status: 'completed',
            artifacts: {
                writeback: {
                    story_alignment: { satisfied: [], missed: [], deferred: [] },
                    director_alignment: { satisfied: [], missed: [], deferred: [] },
                },
            },
        },
        storyPlan: null,
        directorBrief: null,
        storyAlignment: { satisfied: [], missed: [], deferred: [] },
        directorAlignment: { satisfied: [], missed: [], deferred: [] },
        storyRefresh: {
            should_refresh: true,
            recommended_resume_from: 'chapter-director',
            suggested_action: '先刷新导演合同再继续',
        },
        guardedRun: null,
        guardedBatchRun: null,
        resumeRun: null,
        operatorActions: [],
    })

    assert.equal(summary.heading, '继续前建议先重规划')
    assert.equal(summary.nextStep, '从 chapter-director 重试')
    assert(summary.reasons.includes('Writeback 建议 Story Refresh'))
})

test('guarded review block is marked as non-continuable', () => {
    const summary = buildTaskContinuationSummary({
        task: {
            task_type: 'guarded-write',
            status: 'completed',
            artifacts: {},
        },
        storyPlan: null,
        directorBrief: null,
        storyAlignment: { satisfied: [], missed: [], deferred: [] },
        directorAlignment: { satisfied: [], missed: [], deferred: [] },
        storyRefresh: null,
        guardedRun: {
            outcome: 'blocked_by_review',
            review_summary: {
                issues: [{ title: '节奏失衡' }, { title: '动机不足' }],
            },
        },
        guardedBatchRun: null,
        resumeRun: null,
        operatorActions: [{ id: 'open-review', kind: 'open-task', label: '打开阻断子任务', variant: 'primary', taskId: 'task-1' }],
    })

    assert.equal(summary.heading, '继续前必须处理审查阻断')
    assert.equal(summary.continuation, '不可继续')
    assert.equal(summary.actionLabel, '打开阻断子任务')
    assert.match(summary.summary, /2 个问题/)
})

test('guarded batch completion is marked ready for next batch', () => {
    const summary = buildTaskContinuationSummary({
        task: {
            task_type: 'guarded-batch-write',
            status: 'completed',
            artifacts: {},
        },
        storyPlan: null,
        directorBrief: null,
        storyAlignment: { satisfied: [], missed: [], deferred: [] },
        directorAlignment: { satisfied: [], missed: [], deferred: [] },
        storyRefresh: null,
        guardedRun: null,
        guardedBatchRun: {
            outcome: 'completed_requested_batch',
            completed_chapters: 3,
            next_action: {
                suggested_action: '继续下一批护栏推进',
            },
        },
        resumeRun: null,
        operatorActions: [{ id: 'next-batch', kind: 'launch-task', label: '继续下一批护栏推进', variant: 'primary', taskType: 'guarded-batch-write', payload: {} }],
    })

    assert.equal(summary.heading, '当前批次可继续下一批')
    assert.equal(summary.nextStep, '继续下一批护栏推进')
    assert(summary.reasons.includes('本批已完成 3 章'))
})

test('resume noop task is marked as no action required', () => {
    const summary = buildTaskContinuationSummary({
        task: {
            task_type: 'resume',
            status: 'completed',
            artifacts: {},
        },
        storyPlan: null,
        directorBrief: null,
        storyAlignment: { satisfied: [], missed: [], deferred: [] },
        directorAlignment: { satisfied: [], missed: [], deferred: [] },
        storyRefresh: null,
        guardedRun: null,
        guardedBatchRun: null,
        resumeRun: {
            blocking_reason: '没有发现可恢复的任务',
        },
        operatorActions: [{ id: 'noop', kind: 'complete-noop', label: '无需恢复', variant: 'primary' }],
    })

    assert.equal(summary.heading, '当前无需恢复')
    assert.equal(summary.continuation, '无需操作')
    assert.equal(summary.actionLabel, '无需恢复')
})
