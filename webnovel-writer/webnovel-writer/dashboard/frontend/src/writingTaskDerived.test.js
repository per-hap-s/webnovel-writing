import test from 'node:test'
import assert from 'node:assert/strict'

import { deriveWritingTaskContext } from './writingTaskDerived.js'

test('deriveWritingTaskContext normalizes write artifacts and operator actions', () => {
    const task = {
        task_type: 'write',
        request: { chapter: 12 },
        artifacts: {
            step_results: {
                'story-director': {
                    structured_output: {
                        anchor_chapter: 10,
                        chapters: [{ chapter: 12, goal: '推进主线' }],
                    },
                },
                'chapter-director': {
                    structured_output: {
                        chapter_goal: '揭示线索',
                    },
                },
            },
            writeback: {
                story_alignment: { satisfied: ['主线推进'], missed: ['支线回收'], deferred: [] },
                director_alignment: { satisfied: ['兑现钩子'], missed: [], deferred: ['伏笔延后'] },
                story_refresh: {
                    should_refresh: true,
                    recommended_resume_from: 'story-director',
                    suggested_action: '先刷新滚动规划',
                },
            },
        },
        operatorActions: [{ label: '继续下一章', variant: 'primary' }],
    }

    const derived = deriveWritingTaskContext(task)

    assert.equal(derived.storyPlan.anchor_chapter, 10)
    assert.equal(derived.directorBrief.chapter_goal, '揭示线索')
    assert.deepEqual(derived.storyAlignment.missed, ['支线回收'])
    assert.deepEqual(derived.directorAlignment.deferred, ['伏笔延后'])
    assert.equal(derived.storyRefresh.recommended_resume_from, 'story-director')
    assert.equal(derived.currentStorySlot.goal, '推进主线')
    assert.equal(derived.operatorActions[0].label, '继续下一章')
})

test('deriveWritingTaskContext resolves guarded write and guarded batch fallback artifacts', () => {
    const guardedTask = {
        task_type: 'guarded-write',
        artifacts: {
            guarded_runner: {
                outcome: 'blocked_by_review',
            },
        },
    }
    const guardedBatchTask = {
        task_type: 'guarded-batch-write',
        artifacts: {
            guarded_batch_runner: {
                outcome: 'completed_requested_batch',
                completed_chapters: 2,
            },
        },
    }

    assert.equal(deriveWritingTaskContext(guardedTask).guardedRun.outcome, 'blocked_by_review')
    assert.equal(deriveWritingTaskContext(guardedBatchTask).guardedBatchRun.completed_chapters, 2)
})

test('deriveWritingTaskContext resolves resume step output and defaults missing arrays', () => {
    const task = {
        task_type: 'resume',
        artifacts: {
            step_results: {
                resume: {
                    structured_output: {
                        resume_from_step: 'chapter-director',
                        blocking_reason: '等待恢复目标',
                    },
                },
            },
            writeback: {},
        },
    }

    const derived = deriveWritingTaskContext(task)

    assert.equal(derived.resumeRun.resume_from_step, 'chapter-director')
    assert.deepEqual(derived.storyAlignment.satisfied, [])
    assert.deepEqual(derived.directorAlignment.missed, [])
    assert.equal(derived.storyRefresh, null)
})
