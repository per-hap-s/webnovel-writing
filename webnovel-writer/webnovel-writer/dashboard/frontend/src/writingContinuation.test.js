import { describe, expect, test } from 'vitest'

import { buildTaskContinuationSummary } from './writingContinuation.js'
import { WRITING_CONTINUATION } from './writingTaskCopy.js'

describe('buildTaskContinuationSummary', () => {
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

        expect(summary.heading).toBe('当前可继续下一章')
        expect(summary.continuation).toBe(WRITING_CONTINUATION.continuable)
        expect(summary.summary).toMatch(/已完成写回/)
        expect(summary.reasons).toContain('已接入多章规划')
        expect(summary.reasons).toContain('已接入章节简报')
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
                suggested_action: '先刷新后续规划再继续',
            },
            guardedRun: null,
            guardedBatchRun: null,
            resumeRun: null,
            operatorActions: [],
        })

        expect(summary.heading).toBe('继续前建议先重做规划')
        expect(summary.nextStep).toBe('刷新后续章节规划并重跑本章')
        expect(summary.reasons).toContain('当前写回结果建议刷新后续章节规划')
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

        expect(summary.heading).toBe('继续前必须处理审查阻断')
        expect(summary.continuation).toBe(WRITING_CONTINUATION.blocked)
        expect(summary.actionLabel).toBe('打开阻断子任务')
        expect(summary.summary).toMatch(/2 个问题/)
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

        expect(summary.heading).toBe('当前批次可继续下一批')
        expect(summary.nextStep).toBe('继续下一批护栏推进')
        expect(summary.reasons).toContain('本批已完成 3 章')
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

        expect(summary.heading).toBe('当前无需恢复')
        expect(summary.continuation).toBe(WRITING_CONTINUATION.noop)
        expect(summary.actionLabel).toBe('无需恢复')
    })

    test('write task awaiting chapter brief approval makes replanning completion explicit', () => {
        const summary = buildTaskContinuationSummary({
            task: {
                task_type: 'write',
                status: 'awaiting_chapter_brief_approval',
                current_step: 'chapter-brief-approval',
                artifacts: {
                    writeback: {
                        story_alignment: { satisfied: [], missed: [], deferred: [] },
                        director_alignment: { satisfied: [], missed: [], deferred: [] },
                    },
                },
            },
            storyPlan: { anchor_chapter: 1 },
            directorBrief: { chapter_goal: '确认新的夜班封控推进点' },
            storyAlignment: { satisfied: [], missed: [], deferred: [] },
            directorAlignment: { satisfied: [], missed: [], deferred: [] },
            storyRefresh: null,
            guardedRun: null,
            guardedBatchRun: null,
            resumeRun: null,
            operatorActions: [],
        })

        expect(summary.nextStep).toBe('确认新简报并开写')
        expect(summary.summary).toContain('重规划已完成')
    })
})
