# Supervisor Audit Maintenance

## Scope

Supervisor Audit currently covers five read-only workflows:

1. Audit log browsing
2. Audit health inspection
3. Repair preview review
4. Offline repair execution
5. Repair report and checklist browsing

前端创作工作台只负责渲染这些视图并提供深链接，不提供修复写回 API。

## Storage Layout

- Audit log: `.webnovel/supervisor/audit-log.jsonl`
- Repair reports: `.webnovel/supervisor/audit-repair-reports/repair-report-*.json`
- Saved checklists: `.webnovel/supervisor/checklists/checklist-ch*.md`

## Read-Only API Surface

- `GET /api/supervisor/audit-log`
- `GET /api/supervisor/audit-health`
- `GET /api/supervisor/audit-repair-preview`
- `GET /api/supervisor/audit-repair-reports`
- `GET /api/supervisor/checklists`

修复报告已经暴露了足够的字段，前端创作工作台无需额外后端摘要字段也能完成结果汇总：

- `changed`
- `droppedCount`
- `rewrittenCount`
- `manualReviewCount`
- `keptCount`
- `appliedCount`
- `skippedCount`

## 前端行为

The Supervisor Audit page uses two state layers:

1. Local preferences
2. Query deep links

The local preference payload and the query payload are normalized in the frontend helper module. The page-level browser bindings now live in dedicated frontend modules:

- `src/supervisorAuditPage.jsx`
- `src/supervisorAuditPageState.js`
- `src/supervisorAuditDerived.js`

`App.jsx` now only wires the route and parent callbacks for Supervisor Audit.

## Contract Notes

The regular Supervisor inbox still uses the current action contract:

- `action`
- `secondaryAction`
- `actionLabel`
- `secondaryLabel`

That is the existing runtime contract for now. The next mainline phase will unify this with the new operator action model used by guarded flows and resume flows:

- `operator_actions`
- `resume_action`

Supervisor recommendations may also be derived from guarded task `operator_actions`, then projected back into legacy `action` / `secondaryAction` for compatibility.

Review / approval recovery semantics are now frontend-shared as a read-only helper:

- task detail
- Supervisor Inbox
- Supervisor Audit grouped view

This helper keeps the same meaning for:

- blocking type
- primary recovery action
- follow-up goal after recovery
- review summary hint when applicable

Operator-action execution is also shared through a frontend runtime helper so task detail, Supervisor Inbox, and Supervisor Audit do not drift on launch / retry / open behavior. The Audit page now consumes the parent task mutation callbacks directly when an action creates or retries a task.

Supervisor Inbox card rendering is also split into dedicated frontend components:

- active Supervisor cards
- dismissed Supervisor cards

This keeps `App.jsx` focused on state orchestration instead of owning all card markup directly.

Supervisor Audit timeline rendering is also split into dedicated frontend components:

- grouped audit thread cards
- raw audit event cards

This keeps the audit page logic in `App.jsx` focused on filtering, grouping, and action wiring instead of inline timeline markup.

The Supervisor Audit page sections are also split into dedicated frontend panels:

- filter controls
- timeline container
- repair archive
- checklist archive

This keeps `App.jsx` focused on state orchestration and derived data, while panel layout lives outside the main app shell.

Supervisor and Supervisor Audit themselves are now split into dedicated page modules:

- `src/supervisorPage.jsx`
- `src/supervisorAuditPage.jsx`

The Audit grouped / filter / report derivation is also moved out of the app shell into `src/supervisorAuditDerived.js`, so the page module mainly owns state, effects, and parent callback wiring.

For this phase, keep the audit surface read-only and do not add a new repair summary write path unless the frontend derivation becomes materially more expensive.

## Offline Repair

Independent CLI:

```powershell
python scripts/supervisor_audit.py health --format text
python scripts/supervisor_audit.py repair-preview --format text
python scripts/supervisor_audit.py repair --format text
```

Unified CLI forwarding:

```powershell
python scripts/data_modules/webnovel.py audit health --format text
python scripts/data_modules/webnovel.py audit repair-preview --format text
python scripts/data_modules/webnovel.py audit repair --format text
```

Repair rules:

- Only `manual_review` items stay manual.
- Backups are created by default.
- Each repair writes a report.

## Validation

```powershell
cd dashboard/frontend
npm run test:state
npm run test:ui
npm run build

python -m pytest dashboard/tests/test_dashboard_smoke_contract.py -q
python -m pytest dashboard/tests/test_app.py dashboard/tests/test_supervisor_audit_schema_contract.py -q
```
