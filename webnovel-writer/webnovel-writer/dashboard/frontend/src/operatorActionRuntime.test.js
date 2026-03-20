import test from 'node:test'
import assert from 'node:assert/strict'

import { executeOperatorAction } from './operatorActionRuntime.js'

test('executeOperatorAction retries task and notifies mutation + open handlers', async () => {
    const calls = []
    const response = { id: 'task-1' }

    const result = await executeOperatorAction({
        action: { kind: 'retry-task', taskId: 'task-1', resumeFromStep: 'story-director' },
        postJSON: async (path, body) => {
            calls.push(['postJSON', path, body])
            return response
        },
        onTasksMutated: (payload) => calls.push(['mutated', payload]),
        onOpenTask: (taskId) => calls.push(['open', taskId]),
    })

    assert.deepEqual(result, { outcome: 'retried', response })
    assert.deepEqual(calls, [
        ['postJSON', '/api/tasks/task-1/retry', { resume_from_step: 'story-director' }],
        ['mutated', response],
        ['open', 'task-1'],
    ])
})

test('executeOperatorAction launches task and prefers onTaskCreated over direct open', async () => {
    const calls = []
    const response = { id: 'task-2' }

    const result = await executeOperatorAction({
        action: { kind: 'launch-task', taskType: 'write', payload: { chapter: 9 } },
        postJSON: async (path, body) => {
            calls.push(['postJSON', path, body])
            return response
        },
        onTaskCreated: (payload) => calls.push(['created', payload]),
        onOpenTask: (taskId) => calls.push(['open', taskId]),
    })

    assert.deepEqual(result, { outcome: 'launched', response })
    assert.deepEqual(calls, [
        ['postJSON', '/api/tasks/write', { chapter: 9 }],
        ['created', response],
    ])
})
