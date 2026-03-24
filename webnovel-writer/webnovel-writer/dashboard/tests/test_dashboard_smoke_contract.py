from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC_ROOT = DASHBOARD_ROOT / "frontend" / "src"
APP_PATH = DASHBOARD_ROOT / "frontend" / "src" / "App.jsx"
APP_SECTIONS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "appSections.jsx"
DATA_PAGE_SECTION_PATH = DASHBOARD_ROOT / "frontend" / "src" / "dataPageSection.jsx"
AUDIT_STATE_PATH = DASHBOARD_ROOT / "frontend" / "src" / "supervisorAuditState.js"
TASK_DETAIL_PANELS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "taskDetailPanels.jsx"
WRITING_CONTINUATION_PATH = DASHBOARD_ROOT / "frontend" / "src" / "writingContinuation.js"
RECOVERY_SEMANTICS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "recoverySemantics.js"
SUPERVISOR_CARDS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "supervisorCards.jsx"
SUPERVISOR_AUDIT_PANELS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "supervisorAuditPanels.jsx"
AUDIT_TIMELINE_CARDS_PATH = DASHBOARD_ROOT / "frontend" / "src" / "auditTimelineCards.jsx"
WRITE_MAINLINE_DOC_PATH = DASHBOARD_ROOT.parent / "docs" / "write-mainline-next-phase.md"
SUPERVISOR_AUDIT_DOC_PATH = DASHBOARD_ROOT.parent / "docs" / "supervisor-audit-maintenance.md"


def _read_frontend_sources(*names: str) -> str:
    paths = [FRONTEND_SRC_ROOT / name for name in names] if names else sorted(FRONTEND_SRC_ROOT.glob("*.*"))
    return "\n".join(
        path.read_text(encoding="utf-8-sig")
        for path in paths
        if path.is_file()
    )


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
    source = _read_frontend_sources(
        "taskLauncherSection.jsx",
        "projectBootstrapSection.jsx",
        "planningProfileSection.jsx",
        "filesPageSection.jsx",
        "dashboardPageCommon.jsx",
    )
    app_source = _read_frontend_sources("App.jsx", "controlPage.jsx", "dashboardPageCommon.jsx")

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
    message_source = _read_frontend_sources("dashboardPageCommon.jsx")
    section_source = _read_frontend_sources("taskCenterPageSection.jsx", "taskCenterTaskDetail.jsx", "taskCenterRuntime.js", "filesPageSection.jsx")

    assert "fetchJSON(`/api/tasks/${selectedTaskId}/detail`, requestParams)" in section_source
    assert "translateEventMessage(event.message)" in section_source
    assert "translateEventLevel(event.level)" in section_source
    assert "translateStepName(event.step_name || 'task')" in section_source
    assert "runtime_status?.phase_label" in section_source
    assert "runtime_status?.target_label" in section_source
    assert "runtime_status?.phase_detail" in section_source
    assert "runtime_status?.waiting_seconds" in section_source
    assert "buildRuntimeSummary(task)" in section_source
    assert "buildEventPayloadTags" in section_source
    assert "tree-folder-toggle" in section_source
    assert "'Review gate blocked execution'" in message_source
    assert "'Write target normalized'" in message_source
    assert "writeback_rollback_started" in message_source
    assert "writeback_rollback_finished" in message_source
    assert "prompt_compiled:" in message_source
    assert "awaiting_model_response:" in message_source
    assert "step_heartbeat:" in message_source
    assert "step_retry_started:" in message_source
    assert "step_waiting_approval:" in message_source
    assert "'Resume target scheduled'" in message_source
    assert "'Workflow config error'" in message_source
    assert "'Guarded runner blocked by story refresh'" in message_source
    assert "'Guarded runner completed one chapter'" in message_source
    assert "'Guarded batch child task created'" in message_source
    assert "'Guarded batch stopped by child outcome'" in message_source
    assert "'Guarded batch completed requested chapters'" in message_source


def test_frontend_task_detail_includes_guarded_runner_view():
    section_source = _read_frontend_sources("taskCenterPageSection.jsx", "taskCenterTaskDetail.jsx", "writingTaskDerived.js", "writingTaskListSummary.js")
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
    assert "最近成功章节" in task_detail_panels_source or "\\u6700\\u8fd1\\u6210\\u529f\\u7ae0\\u8282" in task_detail_panels_source
    assert "护栏批量推进结果" in task_detail_panels_source or "\\u62a4\\u680f\\u6279\\u91cf\\u63a8\\u8fdb\\u7ed3\\u679c" in task_detail_panels_source
    assert "buildWriteContinuation" in continuation_source
    assert "buildGuardedWriteContinuation" in continuation_source
    assert "buildGuardedBatchContinuation" in continuation_source
    assert "buildResumeContinuation" in continuation_source


def test_frontend_control_page_includes_supervisor_panel():
    app_source = APP_PATH.read_text(encoding="utf-8-sig")
    supervisor_source = _read_frontend_sources("supervisorPage.jsx")
    recovery_source = RECOVERY_SEMANTICS_PATH.read_text(encoding="utf-8-sig")
    supervisor_cards_source = SUPERVISOR_CARDS_PATH.read_text(encoding="utf-8-sig")

    assert "{ id: 'supervisor'" in app_source
    assert "{ id: 'supervisor-audit'" in app_source
    assert "effectivePage === 'supervisor'" in app_source
    assert "effectivePage === 'supervisor-audit'" in app_source
    assert "<SupervisorPage" in app_source
    assert "<SupervisorAuditPage" in app_source
    assert "fetchJSON('/api/supervisor/recommendations?include_dismissed=true')" in supervisor_source
    assert "postJSON('/api/supervisor/dismiss'" in supervisor_source
    assert "postJSON('/api/supervisor/dismiss-batch'" in supervisor_source
    assert "postJSON('/api/supervisor/undismiss'" in supervisor_source
    assert "postJSON('/api/supervisor/undismiss-batch'" in supervisor_source
    assert "postJSON('/api/supervisor/tracking'" in supervisor_source
    assert "postJSON('/api/supervisor/tracking/clear'" in supervisor_source
    assert "postJSON('/api/supervisor/checklists'" in supervisor_source
    assert "fetchJSON('/api/supervisor/checklists'" in supervisor_source
    assert "rawSupervisorItems" in supervisor_source
    assert "setRawSupervisorItems" in supervisor_source
    assert "selectedSupervisorKeys" in supervisor_source
    assert "toggleSupervisorSelection" in supervisor_source
    assert "setSelectionForItems" in supervisor_source
    assert "handleBatchSupervisorDismiss" in supervisor_source
    assert "handleBatchSupervisorUndismiss" in supervisor_source
    assert "checklistMarkdown" in supervisor_source
    assert "buildSupervisorChecklistMarkdown" in supervisor_source
    assert "downloadTextFile" in supervisor_source
    assert "handleCopyChecklist" in supervisor_source
    assert "handleDownloadChecklist" in supervisor_source
    assert "handleSaveChecklistToProject" in supervisor_source
    assert "savedChecklistMeta" in supervisor_source
    assert "checklistTitle" in supervisor_source
    assert "checklistNote" in supervisor_source
    assert "trackingDrafts" in supervisor_source
    assert "resolveTrackingDraft" in supervisor_source
    assert "updateTrackingDraft" in supervisor_source
    assert "handleSupervisorTrackingSave" in supervisor_source
    assert "handleSupervisorTrackingClear" in supervisor_source
    assert "statusFilter" in supervisor_source
    assert "setStatusFilter" in supervisor_source
    assert "supervisorStatusSummary" in supervisor_source
    assert "recentChecklists" in supervisor_source
    assert "selectedChecklistPath" in supervisor_source
    assert "refreshSupervisorChecklists" in supervisor_source
    assert "handleDownloadSavedChecklist" in supervisor_source
    assert "batchDismissReason" in supervisor_source
    assert "batchDismissNote" in supervisor_source
    assert "categoryFilter" in supervisor_source
    assert "sortMode" in supervisor_source
    assert "SUPERVISOR_SORT_OPTIONS" in supervisor_source
    assert "SUPERVISOR_STATUS_FILTER_OPTIONS" in supervisor_source
    assert "supervisorItems.map((item) => {" in supervisor_source
    assert "dismissedSupervisorItems.map((item) => {" in supervisor_source
    assert "resolveSupervisorItemOperatorActions(item)" in supervisor_source
    assert "sortSupervisorItems" in supervisor_source
    assert "extractSupervisorChapter" in supervisor_source
    assert "item.categoryLabel" in supervisor_source
    assert "SUPERVISOR_DISMISS_REASON_OPTIONS" in supervisor_source
    assert "formatSupervisorDismissReason" in supervisor_source
    assert "formatSupervisorTrackingStatus" in supervisor_source
    assert "dismissalReason" in supervisor_source
    assert "dismissalNote" in supervisor_source
    assert "trackingStatus" in supervisor_source
    assert "trackingNote" in supervisor_source
    assert "linkedTaskId" in supervisor_source
    assert "linkedChecklistPath" in supervisor_source
    assert "SUPERVISOR_TRACKING_STATUS_OPTIONS" in supervisor_source
    assert "item.rationale" in supervisor_source
    assert "item.actionLabel" in supervisor_source
    assert "item.secondaryLabel" in supervisor_source
    assert "handleSupervisorDismiss" in supervisor_source
    assert "handleSupervisorUndismiss" in supervisor_source
    assert "item.title ||" in supervisor_source
    assert "selectedChecklist?.content" in supervisor_source
    assert "dismissedAt" in supervisor_source
    assert "handleSupervisorAction" in supervisor_source
    assert "resolveSupervisorItemOperatorActions" in supervisor_source
    assert "renderOperatorActionButtons" in supervisor_source
    assert "resolveSupervisorRecoverySemantics" in supervisor_source
    assert "SupervisorActiveCard" in supervisor_source
    assert "SupervisorDismissedCard" in supervisor_source
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
    audit_page_source = _read_frontend_sources("supervisorAuditPage.jsx", "supervisorAuditPageState.js", "supervisorAuditDerived.js")
    audit_state_source = AUDIT_STATE_PATH.read_text(encoding="utf-8-sig")
    audit_panels_source = SUPERVISOR_AUDIT_PANELS_PATH.read_text(encoding="utf-8-sig")
    audit_timeline_cards_source = AUDIT_TIMELINE_CARDS_PATH.read_text(encoding="utf-8-sig")
    supervisor_cards_source = SUPERVISOR_CARDS_PATH.read_text(encoding="utf-8-sig")

    assert "export function SupervisorAuditPage" in audit_page_source
    assert "SupervisorAuditTimelinePanel" in audit_page_source
    assert "SupervisorAuditRepairArchivePanel" in audit_page_source
    assert "SupervisorAuditChecklistArchivePanel" in audit_page_source
    assert "auditItems" in audit_page_source
    assert "auditLogEntries" in audit_page_source
    assert "auditHealth" in audit_page_source
    assert "auditRepairPreview" in audit_page_source
    assert "auditRepairReports" in audit_page_source
    assert "auditChecklists" in audit_page_source
    assert "auditRepairReportFilter" in audit_page_source
    assert "auditRepairReportSortMode" in audit_page_source
    assert "report_filter" in audit_page_source
    assert "report_path" in audit_page_source
    assert "report_sort" in audit_page_source
    assert "selectedAuditRepairReportPath" in audit_page_source
    assert "auditCategoryFilter" in audit_page_source
    assert "auditActionFilter" in audit_page_source
    assert "auditStatusFilter" in audit_page_source
    assert "auditChapterFilter" in audit_page_source
    assert "auditViewMode" in audit_page_source
    assert "auditGroupFocus" in audit_page_source
    assert "auditFocusedStableKey" in audit_page_source
    assert "SUPERVISOR_AUDIT_PREFERENCES_KEY" in audit_page_source
    assert "DASHBOARD_PAGE_QUERY_KEY" in audit_page_source
    assert "SUPERVISOR_AUDIT_QUERY_KEYS" in audit_state_source
    assert "buildInitialSupervisorAuditViewState" in audit_page_source
    assert "buildSupervisorAuditPreferencePayload" in audit_state_source
    assert "buildSupervisorAuditQueryPayload" in audit_state_source
    assert "buildSupervisorAuditQueryString" in audit_page_source
    assert "readSupervisorAuditQueryStateFromSearch" in audit_state_source
    assert "resolveVisibleAuditRepairReportPath" in audit_state_source
    assert "fetchJSON('/api/supervisor/audit-log'" in audit_page_source
    assert "fetchJSON('/api/supervisor/audit-health'" in audit_page_source
    assert "fetchJSON('/api/supervisor/audit-repair-preview'" in audit_page_source
    assert "fetchJSON('/api/supervisor/audit-repair-reports'" in audit_page_source
    assert "auditActionOptions" in audit_page_source
    assert "auditGroupFocusOptions" in audit_page_source
    assert "filteredAuditLogEntries" in audit_page_source
    assert "filteredGroupedAuditLogEntries" in audit_page_source
    assert "auditRepairReportSummary" in audit_page_source
    assert "sortedAuditRepairReports" in audit_page_source
    assert "selectedVisibleAuditRepairReport" in audit_page_source
    assert "setSelectedAuditRepairReportPath(nextVisiblePath)" in audit_page_source
    assert "formatSupervisorAuditAction" in audit_page_source
    assert "formatSupervisorAuditStatusSnapshot" in audit_page_source
    assert "buildAuditTaskRuntimeSummary" in audit_page_source
    assert "readSupervisorAuditPreferences" in audit_page_source
    assert "writeSupervisorAuditPreferences" in audit_page_source
    assert "readSupervisorAuditQueryState" in audit_page_source
    assert "writeSupervisorAuditQueryState" in audit_page_source
    assert "buildSupervisorAuditGroupAnchorId" in audit_page_source
    assert "buildSupervisorAuditMarkdown" in audit_page_source
    assert "buildSupervisorAuditHealthMarkdown" in audit_page_source
    assert "buildSupervisorAuditRepairPreviewMarkdown" in audit_page_source
    assert "handleDownloadAuditMarkdown" in audit_page_source
    assert "handleDownloadAuditJson" in audit_page_source
    assert "handleDownloadAuditHealthMarkdown" in audit_page_source
    assert "handleDownloadAuditHealthJson" in audit_page_source
    assert "handleDownloadAuditRepairPreviewMarkdown" in audit_page_source
    assert "handleDownloadAuditRepairPreviewJson" in audit_page_source
    assert "handleDownloadAuditRepairReport" in audit_page_source
    assert "formatSupervisorAuditSchemaState" in audit_page_source
    assert "buildSupervisorAuditSchemaLabel" in audit_page_source
    assert "formatSupervisorAuditHealthIssueLabel" in audit_page_source
    assert "formatSupervisorAuditRepairActionLabel" in audit_page_source
    assert "AUDIT_REPAIR_REPORT_SORT_OPTIONS" in audit_page_source
    assert "formatAuditRepairReportSummary" in audit_page_source
    assert "schemaWarning" in audit_page_source
    assert "schemaState" in audit_page_source
    assert "audit-health-issue:" in audit_panels_source
    assert "audit-repair-preview:" in audit_panels_source
    assert "audit-repair-report:" in audit_panels_source
    assert "当前命中" in audit_panels_source or r"\u5f53\u524d\u547d\u4e2d" in audit_panels_source
    assert "仅人工复核" in audit_panels_source or r"\u4ec5\u4eba\u5de5\u590d\u6838" in audit_panels_source
    assert "排序方式" in audit_panels_source or r"\u6392\u5e8f\u65b9\u5f0f" in audit_panels_source
    assert "handleAuditGroupAction" in audit_page_source
    assert "handleAuditGroupTracking" in audit_page_source
    assert "handleAuditGroupUndismiss" in audit_page_source
    assert "handleAuditGroupTrackingClear" in audit_page_source
    assert "auditRefreshToken" in audit_page_source
    assert "setAuditRefreshToken((current) => current + 1)" in audit_page_source
    assert "handleCopyAuditGroupLink" in audit_page_source
    assert "auditFocusState" in audit_page_source
    assert "handleResetAuditEventFilters" in audit_page_source
    assert "handleResetAuditGroupFilters" in audit_page_source
    assert "selectedAuditChecklistPath" in audit_page_source
    assert "selectedAuditChecklist" in audit_page_source
    assert "setSelectedAuditChecklistPath" in audit_page_source
    assert "handleDownloadAuditChecklist" in audit_page_source
    assert "auditItemsByStableKey" in audit_page_source
    assert "linkedTask" in audit_page_source
    assert "resolveSupervisorRecoverySemantics(currentAuditItem)" in audit_panels_source
    assert "primaryActionLabel" in audit_timeline_cards_source
    assert "primaryActionLabel" in supervisor_cards_source
    assert "linkedChecklist" in audit_page_source
    assert "entry.detail" in audit_timeline_cards_source
    assert "entry.rationale" in audit_timeline_cards_source
    assert "entry.actionLabel" in audit_timeline_cards_source
    assert "entry.secondaryLabel" in audit_timeline_cards_source
    assert "entry.badge" in audit_timeline_cards_source
    assert "entry.priority" in audit_timeline_cards_source
    assert "entry.tone" in audit_timeline_cards_source
    assert "sourceTask" in audit_page_source
    assert "source-task:" in audit_timeline_cards_source
    assert "linked-task:" in audit_timeline_cards_source
    assert "audit-group:" in audit_panels_source
    assert "mergedCount" in audit_page_source
    assert "compactedEntries" in audit_page_source
    assert "compactedEventCount" in audit_page_source
    assert "latestStatusSnapshot" in audit_page_source
    assert "按建议分组" in audit_panels_source or "\\u6309\\u5efa\\u8bae\\u5206\\u7ec4" in audit_panels_source
    assert "原始事件流" in audit_panels_source or "\\u539f\\u59cb\\u4e8b\\u4ef6\\u6d41" in audit_panels_source
    assert "建议时间线" in audit_page_source or "\\u5efa\\u8bae\\u65f6\\u95f4\\u7ebf" in audit_page_source
    assert "已合并" in audit_timeline_cards_source or "\\u5df2\\u5408\\u5e76" in audit_timeline_cards_source
    assert "工作台聚焦" in audit_panels_source or "\\u5de5\\u4f5c\\u53f0\\u805a\\u7126" in audit_panels_source
    assert "可直接执行" in audit_timeline_cards_source or "\\u53ef\\u76f4\\u63a5\\u6267\\u884c" in audit_timeline_cards_source
    assert "已从建议列表移除" in audit_timeline_cards_source or "\\u5df2\\u4ece\\u5efa\\u8bae\\u5217\\u8868\\u79fb\\u9664" in audit_timeline_cards_source
    assert "window.localStorage" in audit_page_source
    assert "URLSearchParams" in app_source
    assert "window.history.replaceState" in audit_page_source
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
    assert "group_focus" in audit_page_source
    assert "view_mode" in audit_page_source
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
    assert "清除工作台聚焦" in audit_panels_source or "\\u6e05\\u9664\\u5de5\\u4f5c\\u53f0\\u805a\\u7126" in audit_panels_source
    assert "移除这条深链接聚焦" in audit_panels_source or "\\u79fb\\u9664\\u8fd9\\u6761\\u6df1\\u94fe\\u63a5\\u805a\\u7126" in audit_panels_source
    assert "预览关联清单" in audit_timeline_cards_source or "\\u9884\\u89c8\\u5173\\u8054\\u6e05\\u5355" in audit_timeline_cards_source
    assert "督办审计视图" in audit_page_source or "SupervisorAuditPage" in audit_page_source
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
    section_source = DATA_PAGE_SECTION_PATH.read_text(encoding="utf-8-sig")

    assert "fetchJSON('/api/story-plans'" in section_source
    assert "多章规划摘要" in section_source
    assert "current_goal" in section_source
    assert "priority_threads" in section_source


def test_frontend_task_detail_includes_story_refresh_view():
    message_source = _read_frontend_sources("dashboardPageCommon.jsx")
    section_source = _read_frontend_sources("taskCenterTaskDetail.jsx", "writingTaskDerived.js")
    task_detail_panels_source = TASK_DETAIL_PANELS_PATH.read_text(encoding="utf-8-sig")

    assert "story_refresh" in section_source
    assert "normalizeStoryRefresh" in section_source
    assert "storyRefresh?.recommended_resume_from || 'story-director'" in task_detail_panels_source or "storyRefresh?.recommended_resume_from || 'story-director'" in _read_frontend_sources("taskCenterTaskDetail.jsx")
    assert "recommended_resume_from || '-'" in task_detail_panels_source
    assert "hasReviewSummary" in task_detail_panels_source
    assert "ReviewSummarySection" in task_detail_panels_source
    assert "'Story plan refresh suggested'" in message_source


def test_frontend_task_detail_includes_task_lineage_view():
    section_source = _read_frontend_sources("taskCenterTaskDetail.jsx", "taskCenterVisibleTasks.js")

    assert "parent_task_id" in section_source
    assert "root_task_id" in section_source


def test_frontend_state_test_script_covers_writing_continuation():
    package_json = json.loads((DASHBOARD_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))

    assert "test:state" in package_json["scripts"]
    assert "src/recoverySemantics.test.js" in package_json["scripts"]["test:state"]
    assert "test:ui" in package_json["scripts"]
    assert "src/writingContinuation.test.js" in package_json["scripts"]["test:ui"]


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
