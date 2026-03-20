import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchJSON, normalizeError, postJSON, subscribeSSE } from './api.js'
import {
    ApiSettingsSection,
    DataPageSection,
    ErrorNotice,
    FilesPageSection,
    PlanningProfileSection,
    ProjectBootstrapSection,
    QualityPageSection,
    TaskCenterPageSection,
    TaskLauncherSection,
} from './appSections.jsx'
import {
    MetricCard,
    SimpleTable,
    formatCell,
    formatNumber,
    resolveApprovalStatusLabel,
    resolveCurrentStepLabel,
    resolveTaskStatusLabel,
    resolveTaskTargetLabel,
    translateColumnLabel,
    translateEventLevel,
    translateEventMessage,
    translateStepName,
    translateTaskStatus,
    translateTaskType,
} from './dashboardPageCommon.jsx'
import { executeOperatorAction as executeRuntimeOperatorAction } from './operatorActionRuntime.js'
import { SupervisorPage } from './supervisorPage.jsx'
import { SupervisorAuditPage } from './supervisorAuditPage.jsx'
import { buildWritingTaskListSummary, supportsWritingTaskContinuation } from './writingTaskListSummary.js'

const NAV_ITEMS = [
    { id: 'control', label: '总览' },
    { id: 'supervisor', label: '督办' },
    { id: 'supervisor-audit', label: '督办审计' },
    { id: 'tasks', label: '任务' },
    { id: 'data', label: '数据' },
    { id: 'files', label: '文件' },
    { id: 'quality', label: '质量' },
]

const MODE_OPTIONS = [
    { value: 'standard', label: '标准' },
    { value: 'fast', label: '快速' },
    { value: 'minimal', label: '精简' },
]

const TASK_TEMPLATES = [
    { key: 'init', title: '补种项目骨架（旧入口）', fields: ['project_root'] },
    { key: 'plan', title: '规划卷', fields: ['volume', 'mode'] },
    { key: 'write', title: '撰写章节', fields: ['chapter', 'mode', 'require_manual_approval'] },
    { key: 'guarded-write', title: '护栏推进一章', fields: ['chapter', 'mode', 'require_manual_approval'] },
    { key: 'guarded-batch-write', title: '护栏批量推进', fields: ['start_chapter', 'max_chapters', 'mode', 'require_manual_approval'] },
    { key: 'review', title: '执行审查', fields: ['chapter_range', 'mode'] },
    { key: 'resume', title: '恢复任务', fields: ['mode'] },
]

const DASHBOARD_PAGE_QUERY_KEY = 'page'

const UI_COPY = {
    overviewPlanningTitle: '规划必填信息',
    projectCreateHint: '仅用于新空目录创建项目；如果你是从桌面启动器进入，通常不用再点“创建项目”。',
    taskEntryHint: '主链建议按“规划卷 -> 撰写章节 -> 执行审查 / 恢复任务”使用；“补种项目骨架（旧入口）”只用于兼容旧项目。',
    planningHint: '先把这里的规划信息补齐，再运行“规划卷”。如果信息不足，系统会提示你回到这里继续补资料。',
    writingEngine: '写作引擎',
    retrievalEngine: '检索引擎',
    overviewMainlineTitle: '写作主链',
    overviewMainlineEmpty: '暂无可展示的写作主链任务；创建 write / guarded / resume 任务后会在这里展示解释摘要。',
    viewTask: '查看任务',
    suggestedNextStep: '建议下一步',
}

export default function App() {
    const [page, setPage] = useState(() => readDashboardPageFromQuery())
    const [projectInfo, setProjectInfo] = useState(null)
    const [llmStatus, setLlmStatus] = useState(null)
    const [ragStatus, setRagStatus] = useState(null)
    const [tasks, setTasks] = useState([])
    const [selectedTaskId, setSelectedTaskId] = useState(null)
    const [coreRefreshVersion, setCoreRefreshVersion] = useState(0)
    const [coreLoadError, setCoreLoadError] = useState(null)
    const [statusLoadError, setStatusLoadError] = useState(null)
    const [connected, setConnected] = useState(false)
    const coreRefreshTimerRef = useRef(null)
    const coreRefreshInFlightRef = useRef(false)
    const coreRefreshPendingRef = useRef(false)
    const coreRefreshSeqRef = useRef(0)
    const statusRefreshSeqRef = useRef(0)
    const optimisticTasksRef = useRef(new Map())

    useEffect(() => {
        void flushCoreRefresh()
    }, [])

    useEffect(() => {
        writeDashboardPageToQuery(page)
    }, [page])

    useEffect(() => {
        void reloadServiceStatus()
        const dispose = subscribeSSE(
            () => {
                if (coreRefreshTimerRef.current) {
                    window.clearTimeout(coreRefreshTimerRef.current)
                }
                coreRefreshTimerRef.current = window.setTimeout(() => {
                    coreRefreshTimerRef.current = null
                    void flushCoreRefresh()
                }, 250)
            },
            {
                onOpen: () => setConnected(true),
                onError: () => setConnected(false),
            },
        )
        const statusTimer = window.setInterval(() => {
            void reloadServiceStatus()
        }, 60000)
        return () => {
            dispose()
            window.clearInterval(statusTimer)
            if (coreRefreshTimerRef.current) {
                window.clearTimeout(coreRefreshTimerRef.current)
                coreRefreshTimerRef.current = null
            }
            coreRefreshSeqRef.current += 1
            statusRefreshSeqRef.current += 1
            setConnected(false)
        }
    }, [])

    function scheduleCoreRefresh() {
        if (coreRefreshTimerRef.current) {
            window.clearTimeout(coreRefreshTimerRef.current)
        }
        coreRefreshTimerRef.current = window.setTimeout(() => {
            coreRefreshTimerRef.current = null
            void flushCoreRefresh()
        }, 250)
    }

    async function flushCoreRefresh() {
        if (coreRefreshInFlightRef.current) {
            coreRefreshPendingRef.current = true
            return
        }

        coreRefreshInFlightRef.current = true
        try {
            do {
                coreRefreshPendingRef.current = false
                const refreshId = ++coreRefreshSeqRef.current
                await reloadCore(refreshId)
                if (refreshId === coreRefreshSeqRef.current) {
                    setCoreRefreshVersion((value) => value + 1)
                }
            } while (coreRefreshPendingRef.current)
        } finally {
            coreRefreshInFlightRef.current = false
        }
    }

    async function reloadCore(refreshId) {
        const [projectResult, tasksResult] = await Promise.allSettled([
            fetchJSON('/api/project/info'),
            fetchJSON('/api/tasks'),
        ])
        if (refreshId !== coreRefreshSeqRef.current) return

        const errors = []
        if (projectResult.status === 'fulfilled') {
            setProjectInfo(projectResult.value)
        } else {
            errors.push(normalizeError(projectResult.reason))
        }

        if (tasksResult.status === 'fulfilled') {
            const mergedItems = mergeFetchedTasksWithOptimistic(tasksResult.value, optimisticTasksRef.current)
            setTasks(mergedItems)
            setSelectedTaskId((currentId) => {
                if (mergedItems.length === 0) return null
                if (currentId && mergedItems.some((item) => item.id === currentId)) return currentId
                return mergedItems[0].id
            })
        } else {
            errors.push(normalizeError(tasksResult.reason))
        }

        setCoreLoadError(errors[0] || null)
    }

    async function reloadServiceStatus() {
        const refreshId = ++statusRefreshSeqRef.current
        const [llmResult, ragResult] = await Promise.allSettled([
            fetchJSON('/api/llm/status'),
            fetchJSON('/api/rag/status'),
        ])
        if (refreshId !== statusRefreshSeqRef.current) return

        const errors = []
        if (llmResult.status === 'fulfilled') {
            setLlmStatus(llmResult.value)
        } else {
            errors.push(normalizeError(llmResult.reason))
        }

        if (ragResult.status === 'fulfilled') {
            setRagStatus(ragResult.value)
        } else {
            errors.push(normalizeError(ragResult.reason))
        }

        setStatusLoadError(errors[0] || null)
    }

    function handleTaskCreated(task) {
        if (!task?.id) {
            scheduleCoreRefresh()
            return
        }
        optimisticTasksRef.current.set(task.id, task)
        setTasks((items) => [task, ...items.filter((item) => item.id !== task.id)])
        setSelectedTaskId(task.id)
        setPage('tasks')
        scheduleCoreRefresh()
    }

    function handleOpenTask(taskId) {
        setSelectedTaskId(taskId)
        setPage('tasks')
    }

    const selectedTask = useMemo(() => tasks.find((item) => item.id === selectedTaskId) || null, [tasks, selectedTaskId])
    const projectMeta = projectInfo?.project_info || projectInfo || {}
    const dashboardContext = projectInfo?.dashboard_context || {}
    const projectTitle = projectMeta?.project_name || projectMeta?.title || dashboardContext?.title || '未加载项目'

    return (
        <div className="shell">
            <aside className="sidebar">
                <div>
                    <div className="brand">小说控制台</div>
                    <div className="project-title">{projectTitle}</div>
                </div>
                <nav className="nav">
                    {NAV_ITEMS.map((item) => (
                        <button
                            key={item.id}
                            className={`nav-button ${page === item.id ? 'active' : ''}`}
                            onClick={() => setPage(item.id)}
                        >
                            {item.label}
                        </button>
                    ))}
                </nav>
                <div className="status-stack">
                    <StatusPill tone={connected ? 'good' : 'danger'} label={connected ? '实时同步已连接' : '实时同步已断开'} />
                    <StatusPill tone={getWritingModelTone(llmStatus)} label={formatWritingModelPill(llmStatus)} />
                    <StatusPill tone={getRagTone(ragStatus)} label={formatRagStatusLabel(ragStatus)} />
                </div>
            </aside>

            <main className="content">
                <ErrorNotice error={coreLoadError} title="核心数据刷新失败" />
                <ErrorNotice error={statusLoadError} title="模型状态刷新失败" />
                {page === 'control' && (
                    <ControlPage
                        projectInfo={projectInfo}
                        llmStatus={llmStatus}
                        ragStatus={ragStatus}
                        tasks={tasks}
                        onTaskCreated={handleTaskCreated}
                        onProjectBootstrapped={(response) => {
                            if (response?.project_switch_required && response?.project_root) {
                                const nextUrl = response.suggested_dashboard_url || `/?project_root=${encodeURIComponent(response.project_root)}`
                                window.location.assign(nextUrl)
                                return
                            }
                            setPage('control')
                            scheduleCoreRefresh()
                        }}
                        onOpenTask={handleOpenTask}
                        onTasksMutated={scheduleCoreRefresh}
                    />
                )}
                {page === 'supervisor' && (
                    <SupervisorPage
                        projectInfo={projectInfo}
                        tasks={tasks}
                        onTaskCreated={handleTaskCreated}
                        onOpenTask={handleOpenTask}
                        onTasksMutated={scheduleCoreRefresh}
                    />
                )}
                {page === 'supervisor-audit' && (
                    <SupervisorAuditPage
                        projectInfo={projectInfo}
                        tasks={tasks}
                        onTaskCreated={handleTaskCreated}
                        onOpenTask={handleOpenTask}
                        onTasksMutated={scheduleCoreRefresh}
                    />
                )}
                {page === 'tasks' && (
                    <TaskCenterPage
                        tasks={tasks}
                        selectedTask={selectedTask}
                        onSelectTask={setSelectedTaskId}
                        onMutated={scheduleCoreRefresh}
                        onNavigateOverview={() => setPage('control')}
                    />
                )}
                {page === 'data' && <DataPage refreshToken={coreRefreshVersion} />}
                {page === 'files' && <FilesPage refreshToken={coreRefreshVersion} />}
                {page === 'quality' && <QualityPage refreshToken={coreRefreshVersion} onMutated={scheduleCoreRefresh} />}
            </main>
        </div>
    )
}

function StatusPill({ tone, label }) {
    return <div className={`status-pill ${tone}`}>{label}</div>
}

function getWritingModelTone(llmStatus) {
    if (!llmStatus?.installed) return 'warning'
    const effectiveStatus = llmStatus?.effective_status || llmStatus?.connection_status
    if (effectiveStatus === 'failed') return 'danger'
    if (effectiveStatus === 'degraded') return 'warning'
    if (effectiveStatus === 'connected') return 'good'
    return 'warning'
}

function formatWritingModelPill(llmStatus) {
    if (!llmStatus?.installed) return '未配置可用的写作引擎'
    const effectiveStatus = llmStatus?.effective_status || llmStatus?.connection_status
    if (effectiveStatus === 'failed') return `${UI_COPY.writingEngine}连接失败 ${formatWritingModelValue(llmStatus)}`
    if (effectiveStatus === 'degraded') return `${UI_COPY.writingEngine}探活异常，但最近运行成功 ${formatWritingModelValue(llmStatus)}`
    if (effectiveStatus === 'connected') return `${UI_COPY.writingEngine}已连接 ${formatWritingModelValue(llmStatus)}`
    return `${UI_COPY.writingEngine}已配置 ${formatWritingModelValue(llmStatus)}`
}

function formatWritingModelValue(llmStatus) {
    if (!llmStatus) return '未配置'
    if (llmStatus.mode === 'cli') {
        return llmStatus.version ? `本地 CLI（${llmStatus.version}）` : '本地 CLI'
    }
    if (llmStatus.mode === 'api') {
        return `模型：${llmStatus.model || '未指定模型'}`
    }
    if (llmStatus.mode === 'mock') {
        return '模拟运行器'
    }
    return llmStatus.provider || '未配置'
}

function formatWritingModelDetail(llmStatus) {
    if (!llmStatus?.installed) return '未配置'
    const effectiveStatus = llmStatus?.effective_status || llmStatus?.connection_status
    const statusSuffix = effectiveStatus === 'connected'
        ? '（已联通）'
        : effectiveStatus === 'degraded'
            ? '（探活异常，最近执行成功）'
            : effectiveStatus === 'failed'
                ? '（连接失败）'
                : '（已配置）'
    if (llmStatus.mode === 'cli') {
        const base = llmStatus.binary ? `本地 CLI（${llmStatus.binary}）` : '本地 CLI'
        return `${base}${statusSuffix}`
    }
    if (llmStatus.mode === 'api') {
        return `模型：${llmStatus.model || '未指定模型'}${statusSuffix}`
    }
    return `${llmStatus.provider || '已配置'}${statusSuffix}`
}

function getRagTone(ragStatus) {
    if (!ragStatus?.configured) return 'warning'
    if (ragStatus?.connection_status === 'failed') return 'danger'
    if (ragStatus?.connection_status === 'connected') return 'good'
    return 'warning'
}

function formatRagStatusLabel(ragStatus) {
    if (!ragStatus?.configured) return `${UI_COPY.retrievalEngine}未配置`
    if (ragStatus?.connection_status === 'failed') {
        return `${UI_COPY.retrievalEngine}连接失败：${formatRagErrorSummary(ragStatus.connection_error || ragStatus.last_error)}`
    }
    if (ragStatus?.connection_status === 'connected') {
        return `${UI_COPY.retrievalEngine}已连接 ${ragStatus?.embed_model || ''}`.trim()
    }
    return `${UI_COPY.retrievalEngine}已配置 ${ragStatus?.embed_model || ''}`.trim()
}

function formatRagDetail(ragStatus) {
    if (!ragStatus?.configured) return '未配置'
    if (ragStatus?.connection_status === 'failed') return '连接失败'
    if (ragStatus?.connection_status === 'connected') return '已联通'
    return '已配置'
}

function formatRagErrorSummary(error) {
    if (!error) return '未知错误'
    const stage = error?.details?.stage ? String(error.details.stage) : '检索'
    const code = error?.code || 'UNKNOWN'
    return `${stage} / ${code}`
}

function readDashboardPageFromQuery() {
    if (typeof window === 'undefined') return 'control'
    const params = new URLSearchParams(window.location.search || '')
    const value = String(params.get(DASHBOARD_PAGE_QUERY_KEY) || '').trim()
    return NAV_ITEMS.some((item) => item.id === value) ? value : 'control'
}

function writeDashboardPageToQuery(page) {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search || '')
    const value = String(page || 'control').trim()
    if (!value || value === 'control') {
        params.delete(DASHBOARD_PAGE_QUERY_KEY)
    } else {
        params.set(DASHBOARD_PAGE_QUERY_KEY, value)
    }
    const query = params.toString()
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`
    window.history.replaceState({}, '', nextUrl)
}

function compareTaskFreshness(left, right) {
    const leftTime = Date.parse(String(left?.runtime_status?.last_event_at || left?.updated_at || '')) || 0
    const rightTime = Date.parse(String(right?.runtime_status?.last_event_at || right?.updated_at || '')) || 0
    if (leftTime !== rightTime) return rightTime - leftTime
    return String(left?.id || '').localeCompare(String(right?.id || ''))
}

function mergeFetchedTasksWithOptimistic(items, optimisticTasks) {
    const fetchedItems = Array.isArray(items) ? items : []
    if (!(optimisticTasks instanceof Map) || optimisticTasks.size === 0) {
        return fetchedItems
    }

    const fetchedIds = new Set(fetchedItems.map((item) => item?.id).filter(Boolean))
    fetchedIds.forEach((taskId) => optimisticTasks.delete(taskId))

    const pendingItems = Array.from(optimisticTasks.values())
        .filter((item) => item?.id && !fetchedIds.has(item.id))

    if (pendingItems.length === 0) return fetchedItems

    return [...pendingItems, ...fetchedItems]
}

function mapContinuationToneToBadgeTone(tone) {
    if (tone === 'success') return 'success'
    if (tone === 'warning') return 'warning'
    if (tone === 'danger') return 'danger'
    return 'muted'
}

function ControlPage({ projectInfo, llmStatus, ragStatus, tasks, onTaskCreated, onProjectBootstrapped, onOpenTask, onTasksMutated }) {
    const projectMeta = projectInfo?.project_info || projectInfo || {}
    const dashboardContext = projectInfo?.dashboard_context || {}
    const [submittingActionKey, setSubmittingActionKey] = useState('')
    const [actionError, setActionError] = useState(null)

    const writingTaskCards = useMemo(() => (
        (tasks || [])
            .filter((task) => supportsWritingTaskContinuation(task))
            .sort(compareTaskFreshness)
            .slice(0, 3)
            .map((task) => ({
                task,
                summary: buildWritingTaskListSummary({ task }),
            }))
            .filter((item) => item.summary)
    ), [tasks])

    async function executeOverviewAction(action) {
        if (!action || action.disabled || action.kind === 'complete-noop') return
        const actionKey = action.id || `${action.kind}:${action.taskId || action.taskType || action.label}`
        setActionError(null)
        setSubmittingActionKey(actionKey)
        try {
            await executeRuntimeOperatorAction({
                action,
                postJSON,
                onOpenTask,
                onTasksMutated: () => onTasksMutated?.(),
                onTaskCreated: (response) => {
                    if (response?.id) {
                        onTaskCreated?.(response)
                        return
                    }
                    onTasksMutated?.()
                },
            })
        } catch (err) {
            setActionError(normalizeError(err))
        } finally {
            setSubmittingActionKey('')
        }
    }

    return (
        <div className="page-grid">
            <section className="panel hero-panel">
                <div className="panel-title">项目概览</div>
                <div className="metric-grid">
                    <MetricCard label="总字数" value={formatNumber(projectInfo?.progress?.total_words || 0)} />
                    <MetricCard label="当前章节" value={`第 ${projectInfo?.progress?.current_chapter || 0} 章`} />
                    <MetricCard label="题材" value={projectMeta?.genre || '未知'} />
                    <MetricCard label={UI_COPY.writingEngine} value={formatWritingModelDetail(llmStatus)} />
                    <MetricCard label={UI_COPY.retrievalEngine} value={formatRagDetail(ragStatus)} />
                </div>
                {(ragStatus?.connection_status === 'failed' || ragStatus?.last_error) && (
                    <div className="empty-state">{`${UI_COPY.retrievalEngine}最近错误：${formatRagErrorSummary(ragStatus.connection_error || ragStatus.last_error)}`}</div>
                )}
            </section>

            <section className="panel">
                <div className="panel-title">项目创建</div>
                <div className="empty-state">{UI_COPY.projectCreateHint}</div>
                <div className="launcher-grid">
                    <ProjectBootstrapSection
                        currentProjectRoot={dashboardContext.project_root || ''}
                        currentTitle={projectMeta?.title || projectMeta?.project_name || dashboardContext?.title || ''}
                        currentGenre={projectMeta?.genre || dashboardContext?.genre || ''}
                        projectInitialized={Boolean(dashboardContext.project_initialized)}
                        onSuccess={onProjectBootstrapped}
                    />
                </div>
            </section>

            <section className="panel">
                <div className="panel-title">任务入口</div>
                <div className="empty-state">{UI_COPY.taskEntryHint}</div>
                <div className="launcher-grid">
                    {TASK_TEMPLATES.map((template) => (
                        <TaskLauncherSection
                            key={template.key}
                            template={template}
                            onCreated={onTaskCreated}
                            MODE_OPTIONS={MODE_OPTIONS}
                            suggestedChapter={Math.max(1, Number(projectInfo?.progress?.current_chapter || 0) + 1)}
                        />
                    ))}
                </div>
            </section>

            <section className="panel full-span">
                <div className="panel-title">{UI_COPY.overviewMainlineTitle}</div>
                <ErrorNotice error={actionError} />
                {writingTaskCards.length === 0 ? (
                    <div className="empty-state">{UI_COPY.overviewMainlineEmpty}</div>
                ) : (
                    <div className="summary-grid">
                        {writingTaskCards.map(({ task, summary }) => (
                            <WritingTaskOverviewCard
                                key={task.id}
                                task={task}
                                summary={summary}
                                submitting={Boolean(summary.primaryAction && submittingActionKey === (summary.primaryAction.id || `${summary.primaryAction.kind}:${summary.primaryAction.taskId || summary.primaryAction.taskType || summary.primaryAction.label}`))}
                                onOpenTask={onOpenTask}
                                onAction={executeOverviewAction}
                            />
                        ))}
                    </div>
                )}
            </section>

            <section className="panel full-span">
                <div className="panel-title">{UI_COPY.overviewPlanningTitle}</div>
                <div className="empty-state">{UI_COPY.planningHint}</div>
                <PlanningProfileSection onSaved={() => onProjectBootstrapped()} />
            </section>

            <section className="panel full-span">
                <div className="panel-title">API 接入设置</div>
                <div className="empty-state">在这里填写写作模型和 RAG 接口配置，保存后会写入项目根目录 `.env` 并立即刷新当前面板状态。</div>
                <ApiSettingsSection llmStatus={llmStatus} ragStatus={ragStatus} onSaved={() => onProjectBootstrapped()} />
            </section>
        </div>
    )
}

function WritingTaskOverviewCard({ task, summary, submitting, onOpenTask, onAction }) {
    const recommendedLabel = summary.primaryActionLabel || summary.nextStep || UI_COPY.viewTask

    return (
        <div className="summary-card">
            <div className="task-item-header">
                <div className="summary-card-title">{translateTaskType(task.task_type)}</div>
                <span className={`runtime-badge ${mapContinuationToneToBadgeTone(summary.tone)}`}>{summary.continuationLabel}</span>
            </div>
            <div className="tiny task-target">{resolveTaskTargetLabel(task)}</div>
            <div className="summary-card-meta">{resolveTaskStatusLabel(task)}</div>
            <div className="summary-card-meta">{summary.reasonLabel}</div>
            <div className="summary-card-meta">{`${UI_COPY.suggestedNextStep}：${recommendedLabel}`}</div>
            <div className="button-row">
                {summary.primaryAction ? (
                    <button
                        className="primary-button"
                        onClick={() => onAction(summary.primaryAction)}
                        disabled={submitting || summary.primaryAction.disabled}
                        title={summary.primaryAction.reason || summary.primaryAction.label}
                    >
                        {submitting ? '处理中...' : summary.primaryActionLabel}
                    </button>
                ) : (
                    <button className="secondary-button" onClick={() => onOpenTask(task.id)}>
                        {UI_COPY.viewTask}
                    </button>
                )}
                {summary.primaryAction ? (
                    <button className="secondary-button" onClick={() => onOpenTask(task.id)}>
                        {UI_COPY.viewTask}
                    </button>
                ) : null}
            </div>
        </div>
    )
}

function TaskCenterPage({ tasks, selectedTask, onSelectTask, onMutated, onNavigateOverview }) {
    return (
        <TaskCenterPageSection
            tasks={tasks}
            selectedTask={selectedTask}
            onSelectTask={onSelectTask}
            onMutated={onMutated}
            onNavigateOverview={onNavigateOverview}
            MetricCard={MetricCard}
            translateTaskType={translateTaskType}
            translateTaskStatus={translateTaskStatus}
            translateStepName={translateStepName}
            translateEventLevel={translateEventLevel}
            translateEventMessage={translateEventMessage}
            resolveTaskStatusLabel={resolveTaskStatusLabel}
            resolveCurrentStepLabel={resolveCurrentStepLabel}
            resolveApprovalStatusLabel={resolveApprovalStatusLabel}
            resolveTargetLabel={resolveTaskTargetLabel}
        />
    )
}

function DataPage({ refreshToken }) {
    return <DataPageSection SimpleTable={SimpleTable} refreshToken={refreshToken} />
}

function FilesPage({ refreshToken }) {
    return <FilesPageSection refreshToken={refreshToken} />
}

function QualityPage({ refreshToken, onMutated }) {
    return <QualityPageSection refreshToken={refreshToken} onMutated={onMutated} SimpleTable={SimpleTable} translateColumnLabel={translateColumnLabel} formatCell={formatCell} />
}
