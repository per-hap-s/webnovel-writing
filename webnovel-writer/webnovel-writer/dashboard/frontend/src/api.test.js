import { expect, test } from 'vitest'

import { normalizeError } from './api.js'

test('normalizeError maps PLAN_INPUT_BLOCKED to the dedicated guidance copy', () => {
    const normalized = normalizeError({
        code: 'PLAN_INPUT_BLOCKED',
        details: {
            blocking_items: [{ field: 'story_logline', label: '故事一句话' }],
        },
    })

    expect(normalized.code).toBe('PLAN_INPUT_BLOCKED')
    expect(normalized.displayMessage).toContain('规划信息待补齐')
    expect(normalized.details.blocking_items).toHaveLength(1)
})

test('normalizeError maps recoverable INVALID_STEP_OUTPUT to system fluctuation copy', () => {
    const normalized = normalizeError({
        code: 'INVALID_STEP_OUTPUT',
        details: {
            parse_stage: 'json_truncated',
            recoverability: 'retriable',
            suggested_resume_step: 'continuity-review',
        },
    })

    expect(normalized.code).toBe('INVALID_STEP_OUTPUT')
    expect(normalized.displayMessage).toContain('系统波动')
    expect(normalized.displayMessage).toContain('json_truncated')
})

test('normalizeError keeps terminal INVALID_STEP_OUTPUT distinct from retriable copy', () => {
    const normalized = normalizeError({
        code: 'INVALID_STEP_OUTPUT',
        details: {
            parse_stage: 'json_invalid',
            recoverability: 'terminal',
        },
    })

    expect(normalized.code).toBe('INVALID_STEP_OUTPUT')
    expect(normalized.displayMessage).not.toContain('系统波动')
    expect(normalized.displayMessage).toContain('json_invalid')
})
