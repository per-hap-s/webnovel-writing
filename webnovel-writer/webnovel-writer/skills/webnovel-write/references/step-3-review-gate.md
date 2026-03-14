# Step 3 Review Gate

## Required Checker Contract

Each checker invoked in Step 3 must return the required fields documented in [`references/checker-output-schema.md`](../../../../references/checker-output-schema.md):

- `agent`
- `chapter`
- `overall_score`
- `pass`
- `issues`
- `metrics`
- `summary`

Extra fields are allowed, but they do not replace the required contract.

## Aggregation Rules

`review-summary` aggregates all review step outputs into:

- `overall_score`
- `reviewers`
- `issues`
- `severity_counts`
- `hard_blocking_issues`
- `blocking`
- `can_proceed`

## Hard Block Rules

The write workflow must stop before `polish` when either condition is met:

- Any issue has `severity=critical`.
- Any issue has `type="TIMELINE_ISSUE"` and `severity in ["high", "critical"]`.

When blocked, the task error code is `REVIEW_GATE_BLOCKED` and the event stream records `Review gate blocked execution`.

## Approval Gate

Manual writeback approval is separate from the review gate:

- Review gate runs before `polish`.
- `approval-gate` runs after `polish`.
- When `require_manual_approval=true`, task status becomes `awaiting_writeback_approval` until approval or rejection.

## Minimal Execution Notes

- Prefer using the workflow persisted on the task record during retries or explicit resumes.
- Only fall back to `workflow_specs/write.json` when the task record does not contain a workflow spec.
- Backend task events should stay in stable English keys/messages; UI translation belongs in the dashboard frontend.
