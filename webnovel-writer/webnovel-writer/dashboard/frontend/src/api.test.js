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
    expect(normalized.displayMessage).toContain('规划输入待补齐')
    expect(normalized.details.blocking_items).toHaveLength(1)
})
