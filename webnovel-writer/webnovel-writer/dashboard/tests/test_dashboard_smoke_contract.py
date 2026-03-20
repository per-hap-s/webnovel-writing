from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = DASHBOARD_ROOT / "frontend" / "src" / "App.jsx"
APP_SECTIONS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "appSections.jsx"
AUDIT_STATE_PATH = DASHBOARD_ROOT / "frontend" / "src" / "supervisorAuditState.js"
TASK_DETAIL_PANELS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "taskDetailPanels.jsx"
WRITING_CONTINUATION_PATH = DASHBOARD_ROOT / "frontend" / "src" / "writingContinuation.js"
RECOVERY_SEMANTICS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "recoverySemantics.js"
SUPERVISOR_CARDS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "supervisorCards.jsx"
SUPERVISOR_AUDIT_PANELS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "supervisorAuditPanels.jsx"
AUDIT_TIMELINE_CARDS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "auditTimelineCards.jsx"
WRITE_MAINLINE_DOC_PATH = DASHBOARD_ROOT.parent / "docs" / "write-mainline-next-phase.md"
SUPERVISOR_AUDIT_DOC_PATH = DASHBOARD_ROOT.parent / "docs" / "supervisor-audit-maintenance.md"


def make_project(tmp_path: Path) -> Path:
    project_root = tmp_path / "novel"
    webnovel_dir = project_root / ".webnovel"
    webnovel_dir.mkdir(parents=True)
    (webnovel_dir / "state.json").write_text(json.dumps({"project_name": "Smoke Novel"}), encoding="utf-8")
    return project_root


def test_validation_error_envelope_matches_frontend_expectations(tmp_path: Path):
    project_root = make_project(tmp_path)
    app = create_app(project_root=project_root)

    with TestClient(app) as client:
        response = client.post("/api/review/approve", json={})

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["message"]
    assert isinstance(payload.get("details", {}).get("errors"), list)
    assert any(error["field"] == "body.task_id" for error in payload["details"]["errors"])


def test_frontend_launcher_surfaces_api_errors():
    source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")
    app_source = APP_PATH.read_text(encoding="utf-8-sig")

    assert "setError(normalizeError(err))" in source
    assert "<ErrorNotice error={error} />" in source
    assert "ProjectBootstrapSection" in source or "ProjectBootstrapSection" in app_source
    assert "key: 'guarded-write'" in app_source
    assert "key: 'guarded-batch-write'" in app_source
    assert "'guarded-write':" in app_source
    assert "'guarded-batch-write':" in app_source
    assert "start_chapter" in source
    assert "max_chapters" in source
    assert "ErrorNotice" in app_source


def test_frontend_task_event_rendering_covers_runtime_contract():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "fetchJSON(`/api/tasks/${selectedTask.id}/events`)" in section_source
    assert "translateEventMessage(event.message)" in section_source
    assert "translateEventLevel(event.level)" in section_source
    assert "translateStepName(event.step_name || 'task')" in section_source
    assert "runtime_status?.phase_label" in section_source
    assert "runtime_status?.target_label" in section_source
    assert "runtime_status?.phase_detail" in section_source
    assert "runtime_status?.waiting_seconds" in section_source
    assert "runtime_status?.step_started_at" in section_source
    assert "runtime_status?.waiting_since" in section_source
    assert "runtime_status?.last_non_heartbeat_activity_at" in section_source
    assert "buildRuntimeSummary(task)" in section_source
    assert "buildEventPayloadTags" in section_source
    assert "tree-folder-toggle" in section_source
    assert "'Review gate blocked execution'" in app_source
    assert "'Write target normalized'" in app_source
    assert "writeback_rollback_started" in app_source
    assert "writeback_rollback_finished" in app_source
    assert "'prompt_compiled'" in app_source
    assert "'awaiting_model_response'" in app_source
    assert "'step_heartbeat'" in app_source
    assert "'step_retry_started'" in app_source
    assert "'step_waiting_approval'" in app_source
    assert "'Resume target scheduled'" in app_source
    assert "'Workflow config error'" in app_source
    assert "'Guarded runner blocked by story refresh'" in app_source
    assert "'Guarded runner completed one chapter'" in app_source
    assert "'Guarded batch child task created'" in app_source
    assert "'Guarded batch stopped by child outcome'" in app_source
    assert "'Guarded batch completed requested chapters'" in app_source


def test_frontend_task_detail_includes_guarded_runner_view():
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")
    task_detail_panels_source = TASK_DETAIL_PANELS_PATH.read_text(encoding="utf-8-sig")
    continuation_source = WRITING_CONTINUATION_PATH.read_text(encoding="utf-8-sig")

    assert "resolveGuardedRunnerResult" in section_source
    assert "resolveGuardedBatchRunnerResult" in section_source
    assert "resolveResumeResult" in section_source
    assert "buildTaskContinuationSummary" in section_source
    assert "TaskContinuationSection" in section_source
    assert "NarrativeContractsSection" in section_source
    assert "AlignmentResultsSection" in section_source
    assert "StoryRefreshSection" in section_source
    assert "ReviewSummarySection" in section_source
    assert "GuardedRunSection" in section_source
    assert "GuardedBatchSection" in section_source
    assert "ResumeSection" in section_source
    assert "resolveTaskOperatorActions" in section_source
    assert "executeOperatorAction" in section_source
    assert "renderOperatorActionButtons" in section_source
    assert "operatorActions" in section_source
    assert "guarded-batch-runner" in section_source
    assert "formatGuardedOutcome" in task_detail_panels_source
    assert "formatGuardedBatchOutcome" in task_detail_panels_source
    assert "推进判断" in task_detail_panels_source or "\\u63a8\\u8fdb\\u5224\\u65ad" in task_detail_panels_source
    assert "当前判断" in task_detail_panels_source or "\\u5f53\\u524d\\u5224\\u65ad" in task_detail_panels_source
    assert "继续状态" in task_detail_panels_source or "\\u7ee7\\u7eed\\u72b6\\u6001" in task_detail_panels_source
    assert "恢复任务合同" in task_detail_panels_source or "\\u6062\\u590d\\u4efb\\u52a1\\u5408\\u540c" in task_detail_panels_source
    assert "最后成功章节" in task_detail_panels_source or "\\u6700\\u540e\\u6210\\u529f\\u7ae0\\u8282" in task_detail_panels_source
    assert "护栏批量推进结果" in task_detail_panels_source or "\\u62a4\\u680f\\u6279\\u91cf\\u63a8\\u8fdb\\u7ed3\\u679c" in task_detail_panels_source
    assert "buildWriteContinuation" in continuation_source
    assert "buildGuardedWriteContinuation" in continuation_source
    assert "buildGuardedBatchContinuation" in continuation_source
    assert "buildResumeContinuation" in continuation_source


def test_frontend_control_page_includes_supervisor_panel():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")
    recovery_source = RECOVERY_SEMANTICS_PATH.read_text(encoding="utf-8-sig")
    supervisor_cards_source = SUPERVISOR_CARDS_PATH.read_text(encoding="utf-8-sig")

    assert "{ id: 'supervisor'" in app_source
    assert "{ id: 'supervisor-audit'" in app_source
    assert "page === 'supervisor'" in app_source
    assert "page === 'supervisor-audit'" in app_source
    assert "<SupervisorPage" in app_source
    assert "<SupervisorAuditPage" in app_source
    assert "fetchJSON('/api/supervisor/recommendations?include_dismissed=true')" in app_source
    assert "postJSON('/api/supervisor/dismiss'" in app_source
    assert "postJSON('/api/supervisor/dismiss-batch'" in app_source
    assert "postJSON('/api/supervisor/undismiss'" in app_source
    assert "postJSON('/api/supervisor/undismiss-batch'" in app_source
    assert "postJSON('/api/supervisor/tracking'" in app_source
    assert "postJSON('/api/supervisor/tracking/clear'" in app_source
    assert "postJSON('/api/supervisor/checklists'" in app_source
    assert "fetchJSON('/api/supervisor/checklists'" in app_source
    assert "rawSupervisorItems" in app_source
    assert "setRawSupervisorItems" in app_source
    assert "selectedSupervisorKeys" in app_source
    assert "toggleSupervisorSelection" in app_source
    assert "setSelectionForItems" in app_source
    assert "handleBatchSupervisorDismiss" in app_source
    assert "handleBatchSupervisorUndismiss" in app_source
    assert "checklistMarkdown" in app_source
    assert "buildSupervisorChecklistMarkdown" in app_source
    assert "downloadTextFile" in app_source
    assert "handleCopyChecklist" in app_source
    assert "handleDownloadChecklist" in app_source
    assert "handleSaveChecklistToProject" in app_source
    assert "savedChecklistMeta" in app_source
    assert "checklistTitle" in app_source
    assert "checklistNote" in app_source
    assert "trackingDrafts" in app_source
    assert "resolveTrackingDraft" in app_source
    assert "updateTrackingDraft" in app_source
    assert "handleSupervisorTrackingSave" in app_source
    assert "handleSupervisorTrackingClear" in app_source
    assert "statusFilter" in app_source
    assert "setStatusFilter" in app_source
    assert "supervisorStatusSummary" in app_source
    assert "recentChecklists" in app_source
    assert "selectedChecklistPath" in app_source
    assert "reloadSupervisorChecklists" in app_source
    assert "handleDownloadSavedChecklist" in app_source
    assert "batchDismissReason" in app_source
    assert "batchDismissNote" in app_source
    assert "categoryFilter" in app_source
    assert "sortMode" in app_source
    assert "SUPERVISOR_SORT_OPTIONS" in app_source
    assert "SUPERVISOR_STATUS_FILTER_OPTIONS" in app_source
    assert "supervisorItems.map((item) => {" in app_source
    assert "dismissedSupervisorItems.map((item) => {" in app_source
    assert "resolveSupervisorItemOperatorActions(item)" in app_source
    assert "sortSupervisorItems" in app_source
    assert "extractSupervisorChapter" in app_source
    assert "item.categoryLabel" in app_source
    assert "SUPERVISOR_DISMISS_REASON_OPTIONS" in app_source
    assert "formatSupervisorDismissReason" in app_source
    assert "formatSupervisorTrackingStatus" in app_source
    assert "dismissalReason" in app_source
    assert "dismissalNote" in app_source
    assert "trackingStatus" in app_source
    assert "trackingNote" in app_source
    assert "linkedTaskId" in app_source
    assert "linkedChecklistPath" in app_source
    assert "SUPERVISOR_TRACKING_STATUS_OPTIONS" in app_source
    assert "item.rationale" in app_source
    assert "item.actionLabel" in app_source
    assert "item.secondaryLabel" in app_source
    assert "handleSupervisorDismiss" in app_source
    assert "handleSupervisorUndismiss" in app_source
    assert "item.title ||" in app_source
    assert "item.note ?" in app_source
    assert "selectedChecklist?.content" in app_source
    assert "Supervisor Inbox" in app_source
    assert "dismissedAt" in app_source
    assert "handleSupervisorAction" in app_source
    assert "resolveSupervisorItemOperatorActions" in app_source
    assert "renderOperatorActionButtons" in app_source
    assert "resolveSupervisorRecoverySemantics" in app_source
    assert "SupervisorActiveCard" in app_source
    assert "SupervisorDismissedCard" in app_source
    assert "恢复语义" in supervisor_cards_source or "\\u6062\\u590d\\u8bed\\u4e49" in supervisor_cards_source
    assert "主恢复动作" in supervisor_cards_source or "\\u4e3b\\u6062\\u590d\\u52a8\\u4f5c" in supervisor_cards_source
    assert "恢复后目标" in supervisor_cards_source or "\\u6062\\u590d\\u540e\\u76ee\\u6807" in supervisor_cards_source
    assert "审查摘要" in supervisor_cards_source or "\\u5ba1\\u67e5\\u6458\\u8981" in supervisor_cards_source
    assert "resolveRecoverySemantics" in recovery_source
    assert "inferRecoveryKindFromSupervisorItem" in recovery_source
    assert "inferRecoveryKindFromTask" in recovery_source
    assert "export function SupervisorActiveCard" in supervisor_cards_source
    assert "export function SupervisorDismissedCard" in supervisor_cards_source
    assert "RecoverySemanticsDetails" in supervisor_cards_source


def test_frontend_includes_supervisor_audit_view():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")
    audit_state_source = AUDIT_STATE_PATH.read_text(encoding="utf-8-sig")
    audit_panels_source = SUPERVISOR_AUDIT_PANELS_PATH.read_text(encoding="utf-8-sig")
    audit_timeline_cards_source = AUDIT_TIMELINE_CARDS_PATH.read_text(encoding="utf-8-sig")
    supervisor_cards_source = SUPERVISOR_CARDS_PATH.read_text(encoding="utf-8-sig")

    assert "function SupervisorAuditPage" in app_source
    assert "SupervisorAuditTimelinePanel" in app_source
    assert "SupervisorAuditRepairArchivePanel" in app_source
    assert "SupervisorAuditChecklistArchivePanel" in app_source
    assert "auditItems" in app_source
    assert "auditLogEntries" in app_source
    assert "auditHealth" in app_source
    assert "auditRepairPreview" in app_source
    assert "auditRepairReports" in app_source
    assert "auditChecklists" in app_source
    assert "auditRepairReportFilter" in app_source
    assert "auditRepairReportSortMode" in app_source
    assert "report_filter" in app_source
    assert "report_path" in app_source
    assert "report_sort" in app_source
    assert "selectedAuditRepairReportPath" in app_source
    assert "auditCategoryFilter" in app_source
    assert "auditActionFilter" in app_source
    assert "auditStatusFilter" in app_source
    assert "auditChapterFilter" in app_source
    assert "auditViewMode" in app_source
    assert "auditGroupFocus" in app_source
    assert "auditFocusedStableKey" in app_source
    assert "SUPERVISOR_AUDIT_PREFERENCES_KEY" in app_source
    assert "DASHBOARD_PAGE_QUERY_KEY" in app_source
    assert "SUPERVISOR_AUDIT_QUERY_KEYS" in app_source
    assert "buildInitialSupervisorAuditViewState" in app_source
    assert "buildSupervisorAuditPreferencePayload" in app_source
    assert "buildSupervisorAuditQueryPayload" in app_source
    assert "buildSupervisorAuditQueryString" in app_source
    assert "readSupervisorAuditQueryStateFromSearch" in app_source
    assert "resolveVisibleAuditRepairReportPath" in app_source
    assert "fetchJSON('/api/supervisor/audit-log'" in app_source
    assert "fetchJSON('/api/supervisor/audit-health'" in app_source
    assert "fetchJSON('/api/supervisor/audit-repair-preview'" in app_source
    assert "fetchJSON('/api/supervisor/audit-repair-reports'" in app_source
    assert "auditActionOptions" in app_source
    assert "auditGroupFocusOptions" in app_source
    assert "filteredAuditLogEntries" in app_source
    assert "groupedAuditLogEntries" in app_source
    assert "filteredGroupedAuditLogEntries" in app_source
    assert "filteredAuditRepairReports" in app_source
    assert "auditRepairReportSummary" in app_source
    assert "sortedAuditRepairReports" in app_source
    assert "selectedVisibleAuditRepairReport" in app_source
    assert "setSelectedAuditRepairReportPath(nextVisiblePath)" in app_source
    assert "formatSupervisorAuditAction" in app_source
    assert "formatSupervisorAuditStatusSnapshot" in app_source
    assert "buildAuditTaskRuntimeSummary" in app_source
    assert "readSupervisorAuditPreferences" in app_source
    assert "writeSupervisorAuditPreferences" in app_source
    assert "readDashboardPageFromQuery" in app_source
    assert "writeDashboardPageToQuery" in app_source
    assert "readSupervisorAuditQueryState" in app_source
    assert "writeSupervisorAuditQueryState" in app_source
    assert "buildSupervisorAuditGroupAnchorId" in app_source
    assert "compactSupervisorAuditGroupEntries" in app_source
    assert "rankSupervisorAuditGroup" in app_source
    assert "buildSupervisorAuditGroups" in app_source
    assert "buildSupervisorAuditMarkdown" in app_source
    assert "buildSupervisorAuditHealthMarkdown" in app_source
    assert "buildSupervisorAuditRepairPreviewMarkdown" in app_source
    assert "handleDownloadAuditMarkdown" in app_source
    assert "handleDownloadAuditJson" in app_source
    assert "handleDownloadAuditHealthMarkdown" in app_source
    assert "handleDownloadAuditHealthJson" in app_source
    assert "handleDownloadAuditRepairPreviewMarkdown" in app_source
    assert "handleDownloadAuditRepairPreviewJson" in app_source
    assert "handleDownloadAuditRepairReport" in app_source
    assert "formatSupervisorAuditSchemaState" in app_source
    assert "buildSupervisorAuditSchemaLabel" in app_source
    assert "formatSupervisorAuditHealthIssueLabel" in app_source
    assert "formatSupervisorAuditRepairActionLabel" in app_source
    assert "AUDIT_REPAIR_REPORT_SORT_OPTIONS" in app_source
    assert "buildAuditRepairReportImpactScore" in app_source
    assert "formatAuditRepairReportSummary" in app_source
    assert "schemaWarning" in app_source
    assert "schemaState" in app_source
    assert "audit-health-issue:" in app_source
    assert "audit-repair-preview:" in app_source
    assert "audit-repair-report:" in audit_panels_source
    assert "当前命中" in audit_panels_source or r"\u5f53\u524d\u547d\u4e2d" in audit_panels_source
    assert "仅人工复核" in audit_panels_source or r"\u4ec5\u4eba\u5de5\u590d\u6838" in audit_panels_source
    assert "排序方式" in audit_panels_source or r"\u6392\u5e8f\u65b9\u5f0f" in audit_panels_source
    assert "handleAuditGroupAction" in app_source
    assert "handleAuditGroupTracking" in app_source
    assert "handleAuditGroupUndismiss" in app_source
    assert "handleAuditGroupTrackingClear" in app_source
    assert "auditRefreshToken" in app_source
    assert "setAuditRefreshToken((current) => current + 1)" in app_source
    assert "handleCopyAuditGroupLink" in app_source
    assert "auditFocusState" in app_source
    assert "handleResetAuditEventFilters" in app_source
    assert "handleResetAuditGroupFilters" in app_source
    assert "resolveCurrentAuditGroupState" in app_source
    assert "isAuditGroupActionable" in app_source
    assert "selectedAuditChecklistPath" in app_source
    assert "selectedAuditChecklist" in app_source
    assert "setSelectedAuditChecklistPath" in app_source
    assert "handleDownloadAuditChecklist" in app_source
    assert "auditItemsByStableKey" in app_source
    assert "describeCurrentAuditItem" in app_source
    assert "linkedTask" in app_source
    assert "resolveSupervisorRecoverySemantics(currentAuditItem)" in audit_panels_source
    assert "primaryActionLabel" in audit_timeline_cards_source
    assert "primaryActionLabel" in supervisor_cards_source
    assert "linkedChecklist" in app_source
    assert "entry.detail" in app_source
    assert "entry.rationale" in app_source
    assert "entry.actionLabel" in app_source
    assert "entry.secondaryLabel" in app_source
    assert "entry.badge" in app_source
    assert "entry.priority" in app_source
    assert "entry.tone" in app_source
    assert "sourceTask" in app_source
    assert "source-task:" in audit_timeline_cards_source
    assert "linked-task:" in audit_timeline_cards_source
    assert "audit-group:" in audit_panels_source
    assert "mergedCount" in app_source
    assert "compactedEntries" in app_source
    assert "compactedEventCount" in app_source
    assert "latestStatusSnapshot" in app_source
    assert "按建议分组" in audit_panels_source or "\\u6309\\u5efa\\u8bae\\u5206\\u7ec4" in audit_panels_source
    assert "原始事件流" in audit_panels_source or "\\u539f\\u59cb\\u4e8b\\u4ef6\\u6d41" in audit_panels_source
    assert "建议时间线" in app_source or "\\u5efa\\u8bae\\u65f6\\u95f4\\u7ebf" in app_source
    assert "已合并" in audit_timeline_cards_source or "\\u5df2\\u5408\\u5e76" in audit_timeline_cards_source
    assert "工作台筛选" in audit_panels_source or "\\u5de5\\u4f5c\\u53f0\\u7b5b\\u9009" in audit_panels_source
    assert "可直接执行" in audit_timeline_cards_source or "\\u53ef\\u76f4\\u63a5\\u6267\\u884c" in audit_timeline_cards_source
    assert "已从 Inbox 移除" in audit_timeline_cards_source or "\\u5df2\\u4ece Inbox \\u79fb\\u9664" in audit_timeline_cards_source
    assert "window.localStorage" in app_source
    assert "URLSearchParams" in app_source
    assert "window.history.replaceState" in app_source
    assert "SUPERVISOR_AUDIT_QUERY_KEYS" in audit_state_source
    assert "SUPERVISOR_AUDIT_VIEW_DEFAULTS" in audit_state_source
    assert "normalizeSupervisorAuditViewState" in audit_state_source
    assert "buildInitialSupervisorAuditViewState" in audit_state_source
    assert "buildSupervisorAuditPreferencePayload" in audit_state_source
    assert "buildSupervisorAuditQueryPayload" in audit_state_source
    assert "buildSupervisorAuditQueryString" in audit_state_source
    assert "readSupervisorAuditQueryStateFromSearch" in audit_state_source
    assert "resolveVisibleAuditRepairReportPath" in audit_state_source
    assert "sa_category" in audit_state_source
    assert "sa_key" in audit_state_source
    assert "sa_report" in audit_state_source
    assert "sa_reports" in audit_state_source
    assert "sa_report_sort" in audit_state_source
    assert "sa_view" in audit_state_source
    assert "page" in app_source
    assert "group_focus" in app_source
    assert "view_mode" in app_source
    assert "当前建议状态" in audit_timeline_cards_source or "\\u5f53\\u524d\\u5efa\\u8bae\\u72b6\\u6001" in audit_timeline_cards_source
    assert "标记处理中" in audit_timeline_cards_source or "\\u6807\\u8bb0\\u5904\\u7406\\u4e2d" in audit_timeline_cards_source
    assert "标记已处理" in audit_timeline_cards_source or "\\u6807\\u8bb0\\u5df2\\u5904\\u7406" in audit_timeline_cards_source
    assert "恢复建议" in audit_timeline_cards_source or "\\u6062\\u590d\\u5efa\\u8bae" in audit_timeline_cards_source
    assert "清除跟踪状态" in audit_timeline_cards_source or "\\u6e05\\u9664\\u8ddf\\u8e2a\\u72b6\\u6001" in audit_timeline_cards_source
    assert "聚焦这条时间线" in audit_timeline_cards_source or "\\u805a\\u7126\\u8fd9\\u6761\\u65f6\\u95f4\\u7ebf" in audit_timeline_cards_source
    assert "复制深链接" in audit_timeline_cards_source or "\\u590d\\u5236\\u6df1\\u94fe\\u63a5" in audit_timeline_cards_source
    assert "清除聚焦" in audit_panels_source or "\\u6e05\\u9664\\u805a\\u7126" in audit_panels_source
    assert "深链接聚焦失败" in audit_panels_source or "\\u6df1\\u94fe\\u63a5\\u805a\\u7126\\u5931\\u8d25" in audit_panels_source
    assert "清除基础筛选" in audit_panels_source or "\\u6e05\\u9664\\u57fa\\u7840\\u7b5b\\u9009" in audit_panels_source
    assert "清除工作台筛选" in audit_panels_source or "\\u6e05\\u9664\\u5de5\\u4f5c\\u53f0\\u7b5b\\u9009" in audit_panels_source
    assert "移除这条深链接聚焦" in audit_panels_source or "\\u79fb\\u9664\\u8fd9\\u6761\\u6df1\\u94fe\\u63a5\\u805a\\u7126" in audit_panels_source
    assert "预览关联清单" in audit_timeline_cards_source or "\\u9884\\u89c8\\u5173\\u8054\\u6e05\\u5355" in audit_timeline_cards_source
    assert "Supervisor Audit" in app_source
    assert "export function SupervisorAuditFilterPanel" in audit_panels_source
    assert "export function SupervisorAuditTimelinePanel" in audit_panels_source
    assert "export function SupervisorAuditRepairArchivePanel" in audit_panels_source
    assert "export function SupervisorAuditChecklistArchivePanel" in audit_panels_source
    assert "export function SupervisorAuditGroupCard" in audit_timeline_cards_source
    assert "export function SupervisorAuditEventCard" in audit_timeline_cards_source
    assert "恢复语义" in audit_timeline_cards_source or "\\u6062\\u590d\\u8bed\\u4e49" in audit_timeline_cards_source
    assert "主恢复动作" in audit_timeline_cards_source or "\\u4e3b\\u6062\\u590d\\u52a8\\u4f5c" in audit_timeline_cards_source
    assert "审计时间线" in audit_panels_source or "\\u5ba1\\u8ba1\\u65f6\\u95f4\\u7ebf" in audit_panels_source
    assert "清单归档" in audit_panels_source or "\\u6e05\\u5355\\u5f52\\u6863" in audit_panels_source
    assert "关联清单预览" in audit_panels_source or "\\u5173\\u8054\\u6e05\\u5355\\u9884\\u89c8" in audit_panels_source


def test_frontend_data_page_includes_story_plan_view():
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "fetchJSON('/api/story-plans'" in section_source
    assert "Story Plans" in section_source
    assert "current_goal" in section_source
    assert "priority_threads" in section_source


def test_frontend_task_detail_includes_story_refresh_view():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")
    task_detail_panels_source = TASK_DETAIL_PANELS_PATH.read_text(encoding="utf-8-sig")

    assert "story_refresh" in section_source
    assert "normalizeStoryRefresh" in section_source
    assert "storyRefresh?.recommended_resume_from || 'story-director'" in section_source
    assert "recommended_resume_from || '-'" in task_detail_panels_source
    assert "hasReviewSummary" in task_detail_panels_source
    assert "ReviewSummarySection" in task_detail_panels_source
    assert "'Story plan refresh suggested'" in app_source


def test_frontend_task_detail_includes_task_lineage_view():
    section_source = APP_SECTIONS_PATH.read_text(encoding="utf-8-sig")

    assert "parent_task_id" in section_source
    assert "root_task_id" in section_source
    assert "trigger_source" in section_source


def test_frontend_state_test_script_covers_writing_continuation():
    package_json = json.loads((DASHBOARD_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))

    assert "test:state" in package_json["scripts"]
    assert "src/writingContinuation.test.js" in package_json["scripts"]["test:state"]
    assert "src/recoverySemantics.test.js" in package_json["scripts"]["test:state"]


def test_task_list_endpoint_returns_runtime_status(tmp_path: Path):
    project_root = make_project(tmp_path)
    app = create_app(project_root=project_root)
    task_file = project_root / ".webnovel" / "observability" / "task-runs" / "task-1.json"

    with TestClient(app) as client:
        task_file.parent.mkdir(parents=True, exist_ok=True)
        task_file.write_text(
            json.dumps(
                {
                    "id": "task-1",
                    "task_type": "plan",
                    "workflow_name": "plan",
                    "workflow_version": 1,
                    "status": "running",
                    "approval_status": "not_required",
                    "current_step": "plan",
                    "request": {"volume": "1"},
                    "project_root": str(project_root),
                    "created_at": "2026-03-16T10:00:00",
                    "updated_at": "2026-03-16T10:00:05",
                    "started_at": "2026-03-16T10:00:00",
                    "finished_at": None,
                    "interrupted_at": None,
                    "recovered_at": None,
                    "resume_target_task_id": None,
                    "resume_from_step": None,
                    "resume_reason": None,
                    "error": None,
                    "step_order": ["plan"],
                    "workflow_spec": {"steps": [{"name": "plan", "type": "llm"}]},
                    "artifacts": {"step_results": {}, "review_summary": None, "approval": {}},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (task_file.parent / "task-1.events.jsonl").write_text(
            json.dumps(
                {
                    "id": "evt-1",
                    "task_id": "task-1",
                    "level": "info",
                    "message": "awaiting_model_response",
                    "step_name": "plan",
                    "payload": {"attempt": 1, "retry_count": 0, "timeout_seconds": 300, "retryable": True},
                    "timestamp": "2026-03-16T10:00:01",
                },
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        response = client.get("/api/tasks")

    assert response.status_code == 200
    runtime = response.json()[0]["runtime_status"]
    assert runtime["phase_label"]
    assert runtime["target_label"] == "\u7b2c 1 \u5377"
    assert runtime["step_state"] == "running"
    assert runtime["attempt"] == 1
    assert "phase_detail" in runtime
    assert "waiting_seconds" in runtime
    assert "step_started_at" in runtime
    assert "waiting_since" in runtime
    assert "last_non_heartbeat_activity_at" in runtime


def test_project_info_includes_dashboard_context(tmp_path: Path):
    project_root = make_project(tmp_path)
    app = create_app(project_root=project_root)

    with TestClient(app) as client:
        response = client.get("/api/project/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["dashboard_context"]["project_root"] == str(project_root)
    assert payload["dashboard_context"]["project_initialized"] is True


def test_planning_docs_record_action_contract_targets():
    write_doc = WRITE_MAINLINE_DOC_PATH.read_text(encoding="utf-8-sig")
    supervisor_doc = SUPERVISOR_AUDIT_DOC_PATH.read_text(encoding="utf-8-sig")

    assert "operator_actions" in write_doc
    assert "resume_action" in write_doc
    assert "continuation summary" in write_doc.lower()
    assert "task detail" in write_doc.lower()
    assert "review / approval" in write_doc.lower()
    assert "supervisor cards" in write_doc.lower()
    assert "audit timeline cards" in write_doc.lower()
    assert "secondaryAction" in write_doc
    assert "next_action" in write_doc
    assert "operator_actions" in supervisor_doc
    assert "resume_action" in supervisor_doc
    assert "secondaryAction" in supervisor_doc
    assert "recovery semantics" in supervisor_doc.lower()
    assert "supervisor cards" in supervisor_doc.lower()
    assert "audit timeline rendering" in supervisor_doc.lower()
