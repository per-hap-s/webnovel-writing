import test from 'node:test'
import assert from 'node:assert/strict'

import {
    normalizeOperatorAction,
    resolveSupervisorItemOperatorActions,
    resolveTaskOperatorActions,
} from './operatorAction.js'

test('resolveTaskOperatorActions builds guarded write fallback actions from next_action', () => {
    const actions = resolveTaskOperatorActions({
        task_type: 'guarded-write',
        id: 'task-guarded-1',
        request: {
            chapter: 2,
            mode: 'standard',
            require_manual_approval: false,
            project_root: 'C:/novel',
            options: { foo: 'bar' },
        },
        artifacts: {
            step_results: {
                'guarded-chapter-runner': {
                    structured_output: {
                        outcome: 'completed_one_chapter',
                        chapter: 2,
                        next_action: {
                            can_enqueue_next: true,
                            next_chapter: 3,
                        },
                    },
                },
            },
        },
    })

    assert.equal(actions.length, 3)
    assert.equal(actions[0].kind, 'launch-task')
    assert.equal(actions[0].taskType, 'guarded-write')
    assert.equal(actions[0].payload.chapter, 3)
    assert.equal(actions[0].variant, 'primary')
    assert.equal(actions[1].kind, 'launch-task')
    assert.equal(actions[1].taskType, 'write')
    assert.equal(actions[2].kind, 'open-task')
    assert.equal(actions[2].taskId, 'task-guarded-1')
})

test('resolveTaskOperatorActions builds guarded batch fallback actions from legacy result', () => {
    const actions = resolveTaskOperatorActions({
        task_type: 'guarded-batch-write',
        id: 'task-batch-1',
        request: {
            start_chapter: 4,
            max_chapters: 2,
            mode: 'fast',
            require_manual_approval: true,
            project_root: 'C:/novel',
            options: { baz: 'qux' },
        },
        artifacts: {
            guarded_batch_runner: {
                outcome: 'completed_requested_batch',
                start_chapter: 4,
                requested_max_chapters: 2,
                completed_chapters: 2,
                next_action: {
                    can_enqueue_next: true,
                    next_chapter: 6,
                },
                last_child_task_id: 'task-child-9',
            },
        },
    })

    assert.equal(actions.length, 2)
    assert.equal(actions[0].kind, 'launch-task')
    assert.equal(actions[0].taskType, 'guarded-batch-write')
    assert.equal(actions[0].payload.start_chapter, 6)
    assert.equal(actions[0].payload.max_chapters, 2)
    assert.equal(actions[1].kind, 'open-task')
    assert.equal(actions[1].taskId, 'task-child-9')
})

test('resolveSupervisorItemOperatorActions normalizes legacy supervisor actions', () => {
    const actions = resolveSupervisorItemOperatorActions({
        stableKey: 'approval:task-1',
        action: {
            type: 'retry-story',
            taskId: 'task-1',
            variant: 'primary',
        },
        secondaryAction: {
            type: 'open-task',
            taskId: 'task-1',
            variant: 'secondary',
        },
    })

    assert.equal(actions.length, 2)
    assert.equal(actions[0].kind, 'retry-task')
    assert.equal(actions[0].resumeFromStep, 'story-director')
    assert.equal(actions[0].variant, 'primary')
    assert.equal(actions[1].kind, 'open-task')
    assert.equal(actions[1].taskId, 'task-1')
})

test('normalizeOperatorAction keeps canonical launch-task shape', () => {
    const action = normalizeOperatorAction({
        kind: 'create-task',
        taskType: 'write',
        payload: { chapter: 5 },
        label: '创建任务',
    })

    assert.equal(action.kind, 'launch-task')
    assert.equal(action.taskType, 'write')
    assert.equal(action.payload.chapter, 5)
    assert.equal(action.label, '创建任务')
})

