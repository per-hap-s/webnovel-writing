# Write Mainline Next Phase

## Current Baseline

The current write stack already includes:

- `story-director`
- `chapter-director`
- `context -> draft -> review -> polish -> data-sync`
- `director_alignment`
- `story_refresh`
- `guarded-write`
- `guarded-batch-write`
- `operator_actions`
- `resume_action`

The dashboard now consumes the same action contract across task detail, guarded recovery, batch recovery, resume results, and Supervisor recommendations. Legacy `next_action`, `action`, and `secondaryAction` are still preserved for compatibility.

## This Round

This round switches back from batch-only recovery to the write mainline detail layer:

- Task detail now shows a unified continuation summary.
- The continuation summary explains why the current chapter can continue, why it must stop, or why it should replan first.
- The same summary consumes:
  - director inputs (`story-director`, `chapter-director`)
  - writeback signals (`story_alignment`, `director_alignment`, `story_refresh`)
  - guarded outcomes
  - resume outcomes
  - unified `operator_actions`
- Action buttons are now rendered once from the continuation panel instead of being repeated across guarded and resume subsections.
- Task detail panels are now split into a dedicated frontend module instead of staying fully inside `appSections.jsx`.
- Review / approval recovery copy is now aligned through a shared frontend recovery semantics helper so task detail, Supervisor Inbox, and Supervisor Audit do not drift.
- Task detail, Supervisor Inbox, and Supervisor Audit now reuse the same frontend operator-action runtime helper for launch / retry / open behavior instead of each page carrying its own execution branch logic.
- Supervisor cards are now split into a dedicated frontend module so `App.jsx` no longer owns both active and dismissed card markup directly.
- Audit timeline cards are now split into a dedicated frontend module so grouped audit threads and raw audit events are no longer rendered inline inside `App.jsx`.
- Supervisor Audit page panels are now split into a dedicated frontend module so filter controls, timeline containers, and archive panels are no longer rendered inline inside `App.jsx`.

In practice this means the operator can open a task and immediately see:

- current judgement
- continuation state
- recommended next step
- primary action entry
- the reasons behind that judgement

## Contract Notes

- `operator_actions` remains the primary operator-facing action model.
- `resume_action` remains a single-action alias for resume results and is mirrored into `operator_actions`.
- Task detail continuation summary is frontend-derived only.
- No new database table or write API is introduced for this phase.
- `next_action`, `action`, and `secondaryAction` remain available during migration.

## Roadmap After This Round

1. Review and approval recovery UX closure

- Keep write-level approval and review tasks as the canonical blocking surface.
- Avoid adding duplicate guarded wrapper recommendations unless they materially reduce operator ambiguity.
- Keep future wording changes flowing through the shared recovery semantics helper instead of per-page string edits.

2. Guarded detail component split

- The first split is already done for continuation, guarded, resume, refresh, and alignment panels.
- If task detail grows further, keep moving read-only task-detail panels out of `appSections.jsx`.

3. Conditional backend summary gate

- Only add a backend read-only summary if frontend summary derivation becomes repetitive in multiple places.

4. Write-mainline clarity follow-ups

- Make `write -> guarded-write -> guarded-batch-write` continuation language even more uniform.
- Surface clearer "why this chapter is safe / unsafe to continue" wording in more list and overview surfaces if needed.

## Validation

Use the following checks for this phase:

```powershell
python -m pytest dashboard\tests\test_guarded_runner.py dashboard\tests\test_guarded_batch_runner.py dashboard\tests\test_supervisor_recommendations.py dashboard\tests\test_app.py dashboard\tests\test_dashboard_smoke_contract.py scripts\data_modules\tests\test_webnovel_unified_cli.py -q
npm run test:state
npm run build
```
