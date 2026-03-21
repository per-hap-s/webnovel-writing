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
import { WorkbenchPage, readLandingPreference, syncDashboardQuery } from './workbenchPage.jsx'
import { buildWritingTaskListSummary, supportsWritingTaskContinuation } from './writingTaskListSummary.js'

const PROJECT_NAV_ITEMS = [
    { id: 'workbench', label: '项目工作台' },
    { id: 'control', label: '总览' },
    { id: 'supervisor', label: '督办' },
    { id: 'supervisor-audit', label: '督办审计' },
    { id: 'tasks', label: '任务' },
    { id: 'data', label: '数据' },
    { id: 'files', label: '文件' },
    { id: 'quality', label: '质量' },
]
const WORKBENCH_TABS = [
    { id: 'hub', label: '项目主页' },
    { id: 'tools', label: '工具页' },
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
const BOOTSTRAP_HINT_QUERY_KEY = 'bootstrap_hint'
const LANDING_PREFERENCE_KEY = 'webnovel.dashboard.landing'
const LANDING_PREFERENCES = [
    { value: 'hub', label: '先到项目主页' },
    { value: 'auto_last', label: '自动进入上次项目' },
]

const ACTIVE_TASK_STATUSES = new Set(['queued', 'running', 'awaiting_writeback_approval', 'retrying', 'resuming_writeback'])

const UI_COPY = {
    overviewPlanningTitle: '规划必填信息',
    projectCreateHint: '双击启动后会先进入工作台，在这里打开已有项目或新建项目。',
    taskEntryHint: '主链建议按“规划卷 -> 撰写章节 -> 执行审查 / 恢复任务”使用；“补种项目骨架（旧入口）”只用于兼容旧项目。',
    planningHint: '先把这里的规划信息补齐，再运行“规划卷”。如果信息不足，系统会提示你回到这里继续补资料。',
    writingEngine: '写作引擎',
    retrievalEngine: '检索引擎',
    overviewMainlineTitle: '主线任务',
    overviewMainlineEmpty: '暂无可展示的主线任务；创建 write / guarded / resume 任务后会在这里显示下一步建议。',
    viewTask: '查看任务',
    suggestedNextStep: '建议下一步',
}

export default function App() {
    const [currentProjectRoot, setCurrentProjectRoot] = useState(() => readProjectRootFromQuery())
    const [page, setPage] = useState(() => readDashboardPageFromQuery())
    const [bootstrapHint, setBootstrapHint] = useState(() => readBootstrapHintFromQuery())
    const [workbenchTab, setWorkbenchTab] = useState('hub')
    const [hubData, setHubData] = useState(null)
    const [hubLoadError, setHubLoadError] = useState(null)
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
    const autoRedirectedRef = useRef(false)
    const lastSseActivityAtRef = useRef(0)
    const projectMode = Boolean(currentProjectRoot)
    const effectivePage = projectMode ? page : 'workbench'

    useEffect(() => {
        syncDashboardQuery({ projectRoot: currentProjectRoot, page: effectivePage, bootstrapHint })
    }, [currentProjectRoot, effectivePage, bootstrapHint])

    useEffect(() => {
        void reloadHub()
    }, [currentProjectRoot])

    useEffect(() => {
        if (currentProjectRoot || !hubData || autoRedirectedRef.current) return
        if (readLandingPreference() !== 'auto_last') return
        const targetUrl = hubData?.current_project?.dashboard_url
        if (!targetUrl) return
        autoRedirectedRef.current = true
        applyDashboardUrl(forceProjectDashboardUrl(targetUrl, 'control'))
    }, [hubData, currentProjectRoot])

    useEffect(() => {
        if (!projectMode) {
            coreRefreshSeqRef.current += 1
            statusRefreshSeqRef.current += 1
            optimisticTasksRef.current.clear()
            lastSseActivityAtRef.current = 0
            setProjectInfo(null)
            setLlmStatus(null)
            setRagStatus(null)
            setTasks([])
            setSelectedTaskId(null)
            setCoreLoadError(null)
            setStatusLoadError(null)
            setConnected(false)
            return
        }
        void flushCoreRefresh()
    }, [projectMode, currentProjectRoot])

    useEffect(() => {
        if (!projectMode) return () => {}
        void reloadServiceStatus()
        const dispose = subscribeSSE(
            () => {
                lastSseActivityAtRef.current = Date.now()
                if (coreRefreshTimerRef.current) {
                    window.clearTimeout(coreRefreshTimerRef.current)
                }
                coreRefreshTimerRef.current = window.setTimeout(() => {
                    coreRefreshTimerRef.current = null
                    void flushCoreRefresh()
                }, 250)
            },
            {
                onOpen: () => {
                    lastSseActivityAtRef.current = Date.now()
                    setConnected(true)
                },
                onHeartbeat: () => {
                    lastSseActivityAtRef.current = Date.now()
                    setConnected(true)
                },
                onOverflow: () => {
                    lastSseActivityAtRef.current = Date.now()
                    setConnected(false)
                    scheduleCoreRefresh()
                },
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
    }, [projectMode, currentProjectRoot])

    useEffect(() => {
        if (!projectMode) return () => {}
        const hasActiveTasks = tasks.some((task) => ACTIVE_TASK_STATUSES.has(String(task?.status || '')))
        const isSseStale = !lastSseActivityAtRef.current || (Date.now() - lastSseActivityAtRef.current) > 20000
        const intervalMs = (hasActiveTasks || isSseStale) ? 3000 : 20000
        const timer = window.setInterval(() => {
            void flushCoreRefresh()
        }, intervalMs)
        return () => window.clearInterval(timer)
    }, [projectMode, currentProjectRoot, tasks])

    function scheduleCoreRefresh() {
        if (!projectMode) return
        if (coreRefreshTimerRef.current) {
            window.clearTimeout(coreRefreshTimerRef.current)
        }
        coreRefreshTimerRef.current = window.setTimeout(() => {
            coreRefreshTimerRef.current = null
            void flushCoreRefresh()
        }, 250)
    }

    async function flushCoreRefresh() {
        if (!projectMode) return
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
        const params = { project_root: currentProjectRoot }
        const [projectResult, tasksResult] = await Promise.allSettled([
            fetchJSON('/api/project/info', params),
            fetchJSON('/api/tasks/summary', params),
        ])
        if (refreshId !== coreRefreshSeqRef.current) return

        const errors = []
        if (projectResult.status === 'fulfilled') {
            setProjectInfo(projectResult.value)
        } else {
            errors.push(normalizeError(projectResult.reason))
        }

        if (tasksResult.status === 'fulfilled') {
            const mergedItems = sortTaskSummaries(mergeFetchedTasksWithOptimistic(tasksResult.value, optimisticTasksRef.current))
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
        const params = { project_root: currentProjectRoot }
        const refreshId = ++statusRefreshSeqRef.current
        const [llmResult, ragResult] = await Promise.allSettled([
            fetchJSON('/api/llm/status', params),
            fetchJSON('/api/rag/status', params),
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

    async function reloadHub(options = {}) {
        try {
            const explicitProjectRoot = Object.prototype.hasOwnProperty.call(options, 'projectRoot')
                ? options.projectRoot
                : currentProjectRoot
            const params = explicitProjectRoot ? { project_root: explicitProjectRoot } : {}
            const payload = await fetchJSON('/api/workbench/hub', params)
            setHubData(payload)
            setHubLoadError(null)
        } catch (error) {
            setHubLoadError(normalizeError(error))
        }
    }

    function applyDashboardUrl(nextUrl) {
        const parsed = new URL(nextUrl, window.location.origin)
        const nextProjectRoot = String(parsed.searchParams.get('project_root') || '').trim()
        const nextPage = String(parsed.searchParams.get(DASHBOARD_PAGE_QUERY_KEY) || (nextProjectRoot ? 'control' : 'workbench')).trim()
        const nextHint = String(parsed.searchParams.get(BOOTSTRAP_HINT_QUERY_KEY) || '').trim()
        setCurrentProjectRoot(nextProjectRoot)
        setPage(nextProjectRoot ? nextPage || 'control' : 'workbench')
        setBootstrapHint(nextHint)
    }

    async function openWorkbenchProject(projectRoot, fallbackUrl = '') {
        try {
            const response = await postJSON('/api/workbench/open-project', { project_root: projectRoot })
            if (response?.opened) {
                const nextUrl = forceProjectDashboardUrl(
                    response?.suggested_dashboard_url || fallbackUrl || `/?project_root=${encodeURIComponent(projectRoot)}`,
                    'control',
                )
                applyDashboardUrl(nextUrl)
                await reloadHub({ projectRoot })
            }
            return response
        } catch (error) {
            const normalizedError = normalizeError(error)
            setHubLoadError(normalizedError)
            return {
                opened: false,
                error: normalizedError,
            }
        }
    }

    function openWorkbenchPanel(nextTab) {
        setWorkbenchTab(nextTab)
        setPage('workbench')
    }

    function handleTaskCreated(task) {
        if (!task?.id) {
            scheduleCoreRefresh()
            return
        }
        optimisticTasksRef.current.set(task.id, task)
        setTasks((items) => sortTaskSummaries([task, ...items.filter((item) => item.id !== task.id)]))
        setSelectedTaskId(task.id)
        setPage('tasks')
        scheduleCoreRefresh()
    }

    function handleOpenTask(taskId) {
        setSelectedTaskId(taskId)
        setPage('tasks')
        if (!tasks.some((item) => item.id === taskId)) {
            scheduleCoreRefresh()
        }
    }

    const selectedTask = useMemo(() => tasks.find((item) => item.id === selectedTaskId) || null, [tasks, selectedTaskId])
    const projectMeta = projectInfo?.project_info || projectInfo || {}
    const dashboardContext = projectInfo?.dashboard_context || {}
    const currentWorkbenchProject = hubData?.current_project || null
    const pinnedWorkbenchProjects = useMemo(
        () => dedupeWorkbenchProjects(hubData?.pinned_projects || [], [currentWorkbenchProject?.project_root]),
        [hubData, currentWorkbenchProject],
    )
    const recentWorkbenchProjects = useMemo(
        () => dedupeWorkbenchProjects(
            hubData?.recent_projects || hubData?.projects || [],
            [currentWorkbenchProject?.project_root, ...pinnedWorkbenchProjects.map((item) => item.project_root)],
        ),
        [hubData, currentWorkbenchProject, pinnedWorkbenchProjects],
    )
    const projectTitle = hubData?.current_project?.title || projectMeta?.project_name || projectMeta?.title || dashboardContext?.title || '未打开项目'

    return (
        <div className="shell">
            <aside className="sidebar">
                <div className="sidebar-header">
                    <div className="brand">小说控制台</div>
                    <div className="project-title">{projectTitle}</div>
                </div>
                <div className="sidebar-scroll">
                    <section className="sidebar-section">
                        <div className="sidebar-section-label">工作台</div>
                        <nav className="nav">
                            {WORKBENCH_TABS.map((item) => (
                                <button
                                    key={item.id}
                                    className={`nav-button ${effectivePage === 'workbench' && workbenchTab === item.id ? 'active' : ''}`}
                                    onClick={() => openWorkbenchPanel(item.id)}
                                >
                                    {item.label}
                                </button>
                            ))}
                        </nav>
                    </section>
                    {projectMode ? (
                        <section className="sidebar-section">
                            <div className="sidebar-section-label">项目页</div>
                            <nav className="nav">
                                {PROJECT_NAV_ITEMS.filter((item) => item.id !== 'workbench').map((item) => (
                                    <button
                                        key={item.id}
                                        className={`nav-button ${effectivePage === item.id ? 'active' : ''}`}
                                        onClick={() => setPage(item.id)}
                                    >
                                        {item.label}
                                    </button>
                                ))}
                            </nav>
                        </section>
                    ) : null}
                    <section className="sidebar-section sidebar-project-section">
                        <div className="sidebar-section-label">项目轨道</div>
                        <div className="sidebar-project-groups">
                            <SidebarProjectGroup
                                title="当前项目"
                                emptyText="还没有当前项目"
                                projects={currentWorkbenchProject ? [currentWorkbenchProject] : []}
                                markCurrent
                                onOpenProject={openWorkbenchProject}
                            />
                            <SidebarProjectGroup
                                title="固定项目"
                                emptyText="还没有固定项目"
                                projects={pinnedWorkbenchProjects}
                                onOpenProject={openWorkbenchProject}
                            />
                            <SidebarProjectGroup
                                title="最近项目"
                                emptyText="打开已有项目后会出现在这里"
                                projects={recentWorkbenchProjects}
                                onOpenProject={openWorkbenchProject}
                            />
                        </div>
                    </section>
                </div>
                <div className="status-stack">
                    {projectMode ? (
                        <>
                            <StatusPill tone={connected ? 'good' : 'danger'} label={connected ? '实时同步已连接' : '实时同步已断开'} />
                            <StatusPill tone={getWritingModelTone(llmStatus)} label={formatWritingModelPill(llmStatus)} />
                            <StatusPill tone={getRagTone(ragStatus)} label={formatRagStatusLabel(ragStatus)} />
                        </>
                    ) : (
                        <StatusPill tone="warning" label="工作台模式：尚未打开项目" />
                    )}
                </div>
            </aside>

            <main className="content">
                <ErrorNotice error={hubLoadError} title="工作台刷新失败" />
                {projectMode ? <ErrorNotice error={coreLoadError} title="核心数据刷新失败" /> : null}
                {projectMode ? <ErrorNotice error={statusLoadError} title="模型状态刷新失败" /> : null}
                {effectivePage === 'workbench' && (
                    <WorkbenchPage
                        hubData={hubData}
                        tab={workbenchTab}
                        currentProjectRoot={currentProjectRoot}
                        landingPreferenceKey={LANDING_PREFERENCE_KEY}
                        landingPreferences={LANDING_PREFERENCES}
                        onTabChange={setWorkbenchTab}
                        onNavigate={applyDashboardUrl}
                        onOpenProject={openWorkbenchProject}
                        onRefresh={reloadHub}
                    />
                )}
                {effectivePage === 'control' && projectMode && (
                    <ControlPage
                        projectInfo={projectInfo}
                        llmStatus={llmStatus}
                        ragStatus={ragStatus}
                        tasks={tasks}
                        bootstrapHint={bootstrapHint}
                        onTaskCreated={handleTaskCreated}
                        onProjectBootstrapped={(response) => {
                            if (response?.suggested_dashboard_url || response?.project_root) {
                                const nextUrl = response?.suggested_dashboard_url || `/?project_root=${encodeURIComponent(response.project_root)}&bootstrap_hint=planning`
                                applyDashboardUrl(nextUrl)
                            }
                            void reloadHub()
                            scheduleCoreRefresh()
                        }}
                        onApiSettingsSaved={() => {
                            void reloadHub()
                            void reloadServiceStatus()
                            scheduleCoreRefresh()
                        }}
                        onOpenTask={handleOpenTask}
                        onTasksMutated={scheduleCoreRefresh}
                        onPlanningProfileSaved={() => {
                            setBootstrapHint('')
                            void flushCoreRefresh()
                        }}
                    />
                )}
                {effectivePage === 'supervisor' && projectMode && (
                    <SupervisorPage
                        projectInfo={projectInfo}
                        tasks={tasks}
                        onTaskCreated={handleTaskCreated}
                        onOpenTask={handleOpenTask}
                        onTasksMutated={scheduleCoreRefresh}
                    />
                )}
                {effectivePage === 'supervisor-audit' && projectMode && (
                    <SupervisorAuditPage
                        projectInfo={projectInfo}
                        tasks={tasks}
                        onTaskCreated={handleTaskCreated}
                        onOpenTask={handleOpenTask}
                        onTasksMutated={scheduleCoreRefresh}
                    />
                )}
                {effectivePage === 'tasks' && projectMode && (
                    <TaskCenterPage
                        tasks={tasks}
                        selectedTask={selectedTask}
                        selectedTaskId={selectedTaskId}
                        currentProjectRoot={currentProjectRoot}
                        onSelectTask={setSelectedTaskId}
                        onMutated={scheduleCoreRefresh}
                        onNavigateOverview={() => setPage('control')}
                    />
                )}
                {effectivePage === 'data' && projectMode && <DataPage refreshToken={coreRefreshVersion} />}
                {effectivePage === 'files' && projectMode && <FilesPage refreshToken={coreRefreshVersion} />}
                {effectivePage === 'quality' && projectMode && <QualityPage refreshToken={coreRefreshVersion} onMutated={scheduleCoreRefresh} />}
            </main>
        </div>
    )
}

function StatusPill({ tone, label }) {
    return <div className={`status-pill ${tone}`}>{label}</div>
}

function SidebarProjectGroup({ title, projects, emptyText, onOpenProject, markCurrent = false }) {
    return (
        <section className="sidebar-project-group">
            <div className="sidebar-project-group-title">{title}</div>
            {projects.length ? (
                <div className="sidebar-project-list">
                    {projects.map((project) => (
                        <SidebarProjectCard key={project.project_root} project={project} current={markCurrent} onOpenProject={onOpenProject} />
                    ))}
                </div>
            ) : (
                <div className="sidebar-project-empty">{emptyText}</div>
            )}
        </section>
    )
}

function SidebarProjectCard({ project, current = false, onOpenProject }) {
    const summary = resolveSidebarProjectSummary(project)
    const badges = []
    if (current) badges.push('当前')
    if (project?.pinned) badges.push('已固定')

    return (
        <button
            type="button"
            className={`sidebar-project-card ${current ? 'active' : ''}`}
            onClick={() => onOpenProject?.(project.project_root, project.dashboard_url)}
        >
            <div className="sidebar-project-card-title">{project?.title || project?.project_root || '未命名项目'}</div>
            <div className="sidebar-project-card-meta">{summary}</div>
            {badges.length ? (
                <div className="sidebar-project-card-badges">
                    {badges.map((badge) => (
                        <span key={badge} className="runtime-badge muted">
                            {badge}
                        </span>
                    ))}
                </div>
            ) : null}
        </button>
    )
}

function resolveSidebarProjectSummary(project) {
    if (!project) return '等待打开'
    if (project.is_missing) return '路径失效'
    if (project.is_corrupted) return '项目状态损坏'
    if (!project.is_initialized) return '目录未初始化'
    if (project.current_chapter) return `第 ${project.current_chapter} 章`
    if (project.total_words) return `${formatNumber(project.total_words)} 字`
    return project.genre || '可直接进入'
}

function dedupeWorkbenchProjects(items, blockedRoots = []) {
    const blocked = new Set((blockedRoots || []).filter(Boolean))
    const seen = new Set()
    const source = Array.isArray(items) ? items : []
    return source.filter((item) => {
        const root = String(item?.project_root || '').trim()
        if (!root || blocked.has(root) || seen.has(root)) return false
        seen.add(root)
        return true
    })
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
    if (typeof window === 'undefined') return 'workbench'
    const params = new URLSearchParams(window.location.search || '')
    const value = String(params.get(DASHBOARD_PAGE_QUERY_KEY) || '').trim()
    return PROJECT_NAV_ITEMS.some((item) => item.id === value) ? value : 'control'
}

function readBootstrapHintFromQuery() {
    if (typeof window === 'undefined') return ''
    const params = new URLSearchParams(window.location.search || '')
    return String(params.get(BOOTSTRAP_HINT_QUERY_KEY) || '').trim()
}

function readProjectRootFromQuery() {
    if (typeof window === 'undefined') return ''
    const params = new URLSearchParams(window.location.search || '')
    return String(params.get('project_root') || '').trim()
}

function compareTaskFreshness(left, right) {
    const leftTime = Date.parse(String(left?.runtime_status?.last_event_at || left?.updated_at || '')) || 0
    const rightTime = Date.parse(String(right?.runtime_status?.last_event_at || right?.updated_at || '')) || 0
    if (leftTime !== rightTime) return rightTime - leftTime
    return String(left?.id || '').localeCompare(String(right?.id || ''))
}

function sortTaskSummaries(items) {
    return [...(Array.isArray(items) ? items : [])].sort((left, right) => {
        const leftPriority = Number(left?.list_priority ?? 99)
        const rightPriority = Number(right?.list_priority ?? 99)
        if (leftPriority !== rightPriority) return leftPriority - rightPriority
        return compareTaskFreshness(left, right)
    })
}

function forceProjectDashboardUrl(nextUrl, page = 'control') {
    const parsed = new URL(nextUrl, window.location.origin)
    if (parsed.searchParams.get('project_root')) {
        parsed.searchParams.set(DASHBOARD_PAGE_QUERY_KEY, page)
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash || ''}`
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

function ControlPage({ projectInfo, llmStatus, ragStatus, tasks, bootstrapHint, onTaskCreated, onProjectBootstrapped, onApiSettingsSaved, onOpenTask, onTasksMutated, onPlanningProfileSaved }) {
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
                {bootstrapHint === 'planning' ? (
                    <div className="planning-warning subtle">
                        <div className="subsection-title">下一步建议</div>
                        <div className="tiny">项目已初始化。下一步先确认并保存规划信息，再运行 `plan`，不需要先手工改总纲。</div>
                    </div>
                ) : null}
                <div className="empty-state">{UI_COPY.planningHint}</div>
                <PlanningProfileSection onSaved={() => onPlanningProfileSaved?.()} />
            </section>

            <section className="panel full-span">
                <div className="panel-title">API 接入设置</div>
                <div className="empty-state">在这里填写写作模型和 RAG 接口配置，保存后会写入项目根目录 `.env` 并立即刷新当前面板状态。</div>
                <ApiSettingsSection llmStatus={llmStatus} ragStatus={ragStatus} onSaved={() => onApiSettingsSaved?.()} />
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
                <button className="secondary-button" onClick={() => onOpenTask(task.id)}>
                    {UI_COPY.viewTask}
                </button>
                <button
                    className={summary.primaryAction ? 'primary-button' : 'secondary-button'}
                    onClick={() => summary.primaryAction && onAction(summary.primaryAction)}
                    disabled={!summary.primaryAction || submitting || summary.primaryAction.disabled}
                    title={summary.primaryAction ? (summary.primaryAction.reason || summary.primaryAction.label) : '当前任务暂无可执行的下一步'}
                >
                    {submitting ? '处理中...' : (summary.primaryActionLabel || '执行下一步')}
                </button>
            </div>
        </div>
    )
}

function TaskCenterPage({ tasks, selectedTask, selectedTaskId, currentProjectRoot, onSelectTask, onMutated, onNavigateOverview }) {
    return (
        <TaskCenterPageSection
            tasks={tasks}
            selectedTask={selectedTask}
            selectedTaskId={selectedTaskId}
            currentProjectRoot={currentProjectRoot}
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
