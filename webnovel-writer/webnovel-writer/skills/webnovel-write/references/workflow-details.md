# Workflow Details

This reference now mirrors the current fixed write chain.

Current write workflow:

`story-director -> chapter-director -> chapter-brief-approval -> context -> draft -> consistency-review -> continuity-review -> ooc-review -> review-summary -> polish -> approval-gate -> data-sync`

Notes:

- `chapter-brief-approval` is always the first hard gate for write tasks.
- `approval-gate` is only a second gate when `require_manual_approval = true`.
- Review steps are fixed to 3 and do not auto-expand.
- `workflow_specs/write.json` remains the source of truth.
