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

## Current Focus

The next write-mainline stabilization layer is now partly in place:

- `INVALID_STEP_OUTPUT` failures are no longer treated as an undifferentiated parse error.
- Task/runtime surfaces now distinguish:
  - `PLAN_INPUT_BLOCKED`
  - `INVALID_STEP_OUTPUT` with retryable recovery semantics
  - terminal `INVALID_STEP_OUTPUT`
- Automatic retry now covers review substeps (`consistency-review`, `continuity-review`, `ooc-review`) in addition to the earlier `plan/context/draft/polish` path.
- `data-sync` remains deliberately outside this auto-retry set for the current phase.

The next major backend milestone after this stabilization work was the dedicated chapter `repair` task, rather than more UI surface expansion.

That repair layer is now in place:

- review summaries emit structured `repair_candidates[]`
- the dashboard can launch `repair` directly from existing task detail flow
- `repair` defaults to direct writeback after successful re-review
- backups and repair reports are written under `.webnovel/repair-backups/` and `.webnovel/repair-reports/`
- only whitelist issue types are eligible for automatic rewrite in this phase

The dashboard now consumes the same action contract across task detail, guarded recovery, batch recovery, resume results, and Supervisor recommendations. Legacy `next_action`, `action`, and `secondaryAction` are still preserved for compatibility.

## This Round

This round extends the write-mainline explanation chain from task detail into shared derivation, task list, and overview surfaces:

- Task detail now shows a unified continuation summary.
- Task list now renders a compact continuation explanation for write / guarded / batch / resume tasks, using the same decision source as task detail, and exposes the same primary operator action in a dedicated CTA row.
- Overview now renders write-mainline entry cards that show the latest continuation state, blocking reason, and recommended next step, and upgrades that recommendation into a clickable primary action when `operator_actions` provides one.
- The continuation summary explains why the current chapter can continue, why it must stop, or why it should replan first.
- The same summary consumes:
  - director inputs (`story-director`, `chapter-director`)
  - writeback signals (`story_alignment`, `director_alignment`, `story_refresh`)
  - guarded outcomes
  - resume outcomes
  - unified `operator_actions`
- Task derivation is now split into:
  - `writingTaskDerived.js` for task -> normalized write-context data
  - `writingTaskListSummary.js` for list/overview-safe explanation adapters
- Continuation labels that drive list/overview blocked-kind derivation are now centralized in a small frontend copy module instead of being compared as scattered string literals.
- Action buttons are now rendered once from the continuation panel instead of being repeated across guarded and resume subsections.
- Task detail panels are now split into a dedicated frontend module instead of staying fully inside `appSections.jsx`.
- Task center is now split into a dedicated container + list + detail shell, so `appSections.jsx` no longer carries task-center state, task-center rendering, and the rest of the dashboard sections in the same component body.
- Review / approval recovery copy is now aligned through a shared frontend recovery semantics helper so task detail, Supervisor Inbox, and Supervisor Audit do not drift.
- Task detail, Supervisor Inbox, and Supervisor Audit now reuse the same frontend operator-action runtime helper for launch / retry / open behavior instead of each page carrying its own execution branch logic.
- Task detail, Supervisor Inbox, and Supervisor Audit now reuse the same frontend action-button renderer, so launch / retry / open controls no longer diverge between surfaces.
- Overview and task-list CTAs now reuse the same operator-action runtime path as task detail instead of introducing a second action execution branch.
- Overview and task-list primary CTAs project the backend action contract directly, including disabled read-only actions, so recommendation copy, button label, and blocking reason do not drift from task detail.
- `complete-noop` remains a read-only continuation state: overview/list surfaces fall back to `查看任务` instead of rendering a misleading executable primary CTA.
- Overview now surfaces operator-action request failures through the shared dashboard error panel instead of failing silently.
- The dashboard shell now keeps locally created tasks visible during the immediate refresh window, so overview launches and task-creation flows do not get overwritten by a stale `/api/tasks` response before the backend list catches up.
- Supervisor cards are now split into a dedicated frontend module so `App.jsx` no longer owns both active and dismissed card markup directly.
- Audit timeline cards are now split into a dedicated frontend module so grouped audit threads and raw audit events are no longer rendered inline inside `App.jsx`.
- Supervisor Audit page panels are now split into a dedicated frontend module so filter controls, timeline containers, and archive panels are no longer rendered inline inside `App.jsx`.
- Supervisor and Supervisor Audit pages are now split into dedicated page modules, and the Audit grouped/filter/report derivation now lives in a standalone helper module instead of inside `App.jsx`.

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
- Task list / overview continuation summaries are also frontend-derived adapters over the same detail summary, not a second rule set.
- Task list / overview primary CTAs are direct projections of `operator_actions`; they do not invent a second action priority model, and disabled actions stay visible as non-clickable CTA projections.
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
- Keep list and overview surfaces thin adapters over the shared derivation instead of adding per-page explanation branches.
- Keep future task-center work inside the dedicated task-center files instead of re-expanding `appSections.jsx`.

5. Real regression expansion

- Move from the current repair-capable 1-5 chapter baseline toward the planned 1-10 chapter baseline.
- Keep `repair` scoped to local continuity fixes until the 10-chapter mainline is stable.
- Delay wider style / voice rewrite coverage until the longer regression path is consistently green.

## Validation

Use the following checks for this phase:

```powershell
python -m pytest dashboard\tests\test_guarded_runner.py dashboard\tests\test_guarded_batch_runner.py dashboard\tests\test_supervisor_recommendations.py dashboard\tests\test_app.py dashboard\tests\test_dashboard_smoke_contract.py scripts\data_modules\tests\test_webnovel_unified_cli.py -q
npm run test:state
npm run test:ui
npm run build
```
