# Context Contract Reference

This file is still referenced by `workflow_specs/write.json`, but it now documents the current `context` step instead of the old “Step 1.5” narrative.

## Purpose

The `context` step must transform planning and chapter-director outputs into a draft-ready execution package for the current chapter.

## Required Output Keys

The `context` step must output all of these keys:

- `story_plan`
- `director_brief`
- `task_brief`
- `contract_v2`
- `draft_prompt`

Missing any required key is a contract failure.

## Output Expectations

### `story_plan`

- Multi-chapter planning context needed by the current chapter.
- Must stay aligned with `story-director`.

### `director_brief`

- Current chapter brief produced by `chapter-director`.
- Must preserve chapter goal, conflict, reveal ceiling, hold-backs and review focus.

### `task_brief`

- A concise execution brief for the current chapter.
- Should be directly usable by `draft`.

### `contract_v2`

- The chapter execution contract.
- Use it to make constraints explicit, not to invent future workflow branches.

### `draft_prompt`

- The actual prompt content used by `draft`.
- It may be stored separately for compaction, but it must exist as a produced artifact.

## Constraints

- Do not describe or rely on `Step 2A`, `Step 2B`, `backup-agent`, or Git backup stages.
- Do not assume `subtask` orchestration.
- Do not assume extra review checkers outside:
  - `consistency-review`
  - `continuity-review`
  - `ooc-review`

## Consumer Relationship

`draft` consumes the `context` output directly. The contract must therefore be strict, stable and self-contained.
