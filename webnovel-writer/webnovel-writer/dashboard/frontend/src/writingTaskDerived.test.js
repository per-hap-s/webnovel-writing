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
                        chapters: [{ chapter: 12, goal: 'advance-mainline' }],
                    },
                },
                'chapter-director': {
                    structured_output: {
                        chapter_goal: 'reveal-clue',
                    },
                },
            },
            writeback: {
                story_alignment: { satisfied: ['mainline'], missed: ['payoff'], deferred: [] },
                director_alignment: { satisfied: ['hook'], missed: [], deferred: ['foreshadow'] },
                story_refresh: {
                    should_refresh: true,
                    recommended_resume_from: 'story-director',
                    suggested_action: 'refresh-story-plan',
                },
            },
        },
        operatorActions: [
            {
                kind: 'launch-task',
                label: 'Continue next chapter',
                variant: 'primary',
                taskType: 'write',
                payload: { chapter: 13 },
            },
        ],
    }

    const derived = deriveWritingTaskContext(task)

    assert.equal(derived.storyPlan.anchor_chapter, 10)
    assert.equal(derived.directorBrief.chapter_goal, 'reveal-clue')
    assert.deepEqual(derived.storyAlignment.missed, ['payoff'])
    assert.deepEqual(derived.directorAlignment.deferred, ['foreshadow'])
    assert.equal(derived.storyRefresh.recommended_resume_from, 'story-director')
    assert.equal(derived.currentStorySlot.goal, 'advance-mainline')
    assert.equal(derived.operatorActions[0].kind, 'launch-task')
    assert.equal(derived.operatorActions[0].variant, 'primary')
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
                        blocking_reason: 'waiting-for-target',
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
