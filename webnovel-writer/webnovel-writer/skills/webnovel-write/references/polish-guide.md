---
name: polish-guide
purpose: Guide the current `polish` step after review-summary.
version: "current"
---

# Polish Guide

## Purpose

The `polish` step improves the drafted chapter after `review-summary`. It is a quality-fix step, not a workflow branch or a style-only rewrite stage.

## Inputs

`polish` should work from:

- current chapter content
- `review-summary`
- review issues from:
  - `consistency-review`
  - `continuity-review`
  - `ooc-review`

## Required Output Keys

The `polish` step must output:

- `chapter_file`
- `content`
- `anti_ai_force_check`
- `change_summary`

`anti_ai_force_check` must be `pass`, otherwise the workflow must not continue to writeback.

## Execution Rules

1. Fix blocking and high-severity review issues first.
2. Preserve approved chapter intent and planning constraints.
3. Do not invent new workflow stages or detour into unrelated rewrites.
4. Keep edits focused on quality, consistency, continuity, voice and readability.
5. Produce a truthful `change_summary`.

## Boundaries

- Do not describe this as “Step 4”.
- Do not assume a separate style-adapter stage exists in the current flow.
- Do not rely on `backup-agent`, Git backup, or future checker expansion.

## Gate Relationship

After `polish`, the task proceeds to:

- `approval-gate` when `require_manual_approval = true`
- otherwise directly to `data-sync`
