---
name: webnovel-write
description: Writes webnovel chapters through the current dashboard write workflow. Use when the user asks to write a chapter or runs webnovel write.
---

# Webnovel Write

## Scope

This skill documents the current real write flow. It must stay aligned with `workflow_specs/write.json`.

Current write chain:

`story-director -> chapter-director -> chapter-brief-approval -> context -> draft -> consistency-review -> continuity-review -> ooc-review -> review-summary -> polish -> approval-gate -> data-sync`

## What Is In Scope

- Generate one chapter through the dashboard/orchestrator write workflow.
- Respect chapter brief approval before正文 writing starts.
- Run the 3 fixed review steps:
  - `consistency-review`
  - `continuity-review`
  - `ooc-review`
- Produce writeback artifacts through `data-sync`.

## What Is Not Implemented

The current version does not implement these features and this skill must not promise them:

- `subtask`
- automatic checker routing
- 6-checker dynamic insertion
- `backup-agent`
- old `Step 1 / Step 2A / Step 2B / Step 6` narrative

## Required Inputs

- `project_root`
- target `chapter`
- initialized `.webnovel/state.json`
- available outline / planning data required by the director steps

If any required project state is missing, stop and report the missing input instead of guessing.

## Step Semantics

### `story-director`

- Builds multi-chapter planning context.
- Must output the fields declared in `workflow_specs/write.json`.

### `chapter-director`

- Builds the current chapter brief.
- Must output the fields declared in `workflow_specs/write.json`.

### `chapter-brief-approval`

- This is a hard gate.
- Write tasks stop here first with `status = awaiting_chapter_brief_approval`.
- Only after approval may the task continue to `context`.

### `context`

- Produces the write package for drafting.
- Required keys:
  - `story_plan`
  - `director_brief`
  - `task_brief`
  - `contract_v2`
  - `draft_prompt`

### `draft`

- Produces chapter draft content.
- Required keys are defined in `workflow_specs/write.json`.

### Review Steps

The current workflow always runs exactly 3 review steps:

- `consistency-review`
- `continuity-review`
- `ooc-review`

Each review output must include:

- `agent`
- `chapter`
- `overall_score`
- `pass`
- `issues`
- `metrics`
- `summary`

### `review-summary`

- Aggregates the 3 review outputs.
- Persists `review_metrics` only after upstream review outputs satisfy the full contract.

### `polish`

- Applies final fixes and polish.
- Must satisfy the required output contract in `workflow_specs/write.json`.

### `approval-gate`

- Optional manual gate for final writeback.
- Only used when request explicitly sets `require_manual_approval = true`.
- If triggered, task pauses with `status = awaiting_writeback_approval`.

### `data-sync`

- Writes正文、摘要、state、index and related structured artifacts back into the project.
- This is the final writeback step in the write chain.

## Approval and Resume Rules

- A task in `awaiting_chapter_brief_approval` may only resume from `chapter-brief-approval`.
- A write task in `awaiting_writeback_approval` may only resume from `approval-gate`.
- Do not trust arbitrary external `resume_from_step`.

## PowerShell Commands

Windows default shell is `PowerShell`. Use PowerShell-native syntax only.

Example verification commands:

```powershell
Set-Location "D:\CodexProjects\Project1\webnovel-writer\webnovel-writer"
python -m pytest dashboard\tests\test_orchestrator.py dashboard\tests\test_task_store.py dashboard\tests\test_write_director_workflow.py dashboard\tests\test_orchestrator_repairs.py -q
```

```powershell
Set-Location "D:\CodexProjects\Project1\webnovel-writer\webnovel-writer\dashboard\frontend"
npm run test:ui -- src\writingContinuation.test.js src\taskCenterRepairApproval.test.jsx
```

Do not use `bash/sh` syntax such as:

- `&&`
- `||`
- `source`
- `export`
- heredoc
- `VAR=value command`

## References

- `workflow_specs/write.json`
- `workflow_specs/review.json`
- `docs/architecture.md`
- `dashboard/orchestrator.py`
