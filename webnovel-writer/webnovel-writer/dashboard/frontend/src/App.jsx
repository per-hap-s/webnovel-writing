import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchJSON, normalizeError, postJSON, subscribeSSE } from './api.js'
import { ErrorNotice } from './appSections.jsx'
import {
    formatNumber,
} from './dashboardPageCommon.jsx'
import { ControlPage } from './controlPage.jsx'
import { DataPage } from './dataPage.jsx'
import { FilesPage } from './filesPage.jsx'
import { QualityPage } from './qualityPage.jsx'
import { SupervisorPage } from './supervisorPage.jsx'
import { SupervisorAuditPage } from './supervisorAuditPage.jsx'
import { TaskCenterPage } from './taskCenterPage.jsx'
import * as serviceStatus from './serviceStatus.js'
import { WorkbenchPage, readLandingPreference, syncDashboardQuery } from './workbenchPage.jsx'

const PROJECT_NAV_ITEMS = [
    { id: 'workbench', label: '项目工作台' },
    { id: 'control', label: '项目总览' },
    { id: 'supervisor', label: '督办台' },
    { id: 'supervisor-audit', label: '督办审计' },
    { id: 'tasks', label: '任务中心' },
    { id: 'data', label: '数据' },
    { id: 'files', label: '文件' },
    { id: 'quality', label: '质量' },
]
const WORKBENCH_TABS = [
    { id: 'hub', label: '项目主页' },
    { id: 'tools', label: '工具页' },
    { id: 'verification', label: '验证页' },
]

const UI_COPY = {
    writingEngine: '写作引擎',
    retrievalEngine: '检索引擎',
}

const DASHBOARD_PAGE_QUERY_KEY = 'page'
const BOOTSTRAP_HINT_QUERY_KEY = 'bootstrap_hint'
const LANDING_PREFERENCE_KEY = 'webnovel.dashboard.landing'
const LANDING_PREFERENCES = [
    { value: 'hub', label: '先到项目主页' },
    { value: 'auto_last', label: '自动进入上次项目' },
]

const ACTIVE_TASK_STATUSES = new Set(['queued', 'running', 'awaiting_chapter_brief_approval', 'awaiting_writeback_approval', 'retrying', 'resuming_writeback'])

export default function App() {
    const [currentProjectRoot, setCurrentProjectRoot] = useState(() => readProjectRootFromQuery())
    const [page, setPage] = useState(() => readDashboardPageFromQuery())
    const [bootstrapHint, setBootstrapHint] = useState(() => readBootstrapHintFromQuery())
    const [workbenchTab, setWorkbenchTab] = useState('hub')
    const [hubData, setHubData] = useState(null)
    const [hubLoadError, setHubLoadError] = useState(null)
    const [projectInfo, setProjectInfo] = useState(null)
    const [directorHub, setDirectorHub] = useState(null)
    const [directorHubError, setDirectorHubError] = useState(null)
    const [llmStatus, setLlmStatus] = useState(null)
    const [ragStatus, setRagStatus] = useState(null)
    const [llmStatusError, setLlmStatusError] = useState(null)
    const [ragStatusError, setRagStatusError] = useState(null)
    const [tasks, setTasks] = useState([])
    const [selectedTaskId, setSelectedTaskId] = useState(null)
    const [coreRefreshVersion, setCoreRefreshVersion] = useState(0)
    const [coreLoadError, setCoreLoadError] = useState(null)
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
            setDirectorHub(null)
            setDirectorHubError(null)
            setLlmStatus(null)
            setRagStatus(null)
            setLlmStatusError(null)
            setRagStatusError(null)
            setTasks([])
            setSelectedTaskId(null)
            setCoreLoadError(null)
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
        const [projectResult, tasksResult, directorHubResult] = await Promise.allSettled([
            fetchJSON('/api/project/info', params),
            fetchJSON('/api/tasks/summary', params),
            fetchJSON('/api/project/director-hub', params),
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

        if (directorHubResult.status === 'fulfilled') {
            setDirectorHub(directorHubResult.value)
            setDirectorHubError(null)
        } else {
            setDirectorHubError(normalizeError(directorHubResult.reason))
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

        if (llmResult.status === 'fulfilled') {
            setLlmStatus(llmResult.value)
            setLlmStatusError(null)
        } else {
            setLlmStatusError(normalizeError(llmResult.reason))
        }

        if (ragResult.status === 'fulfilled') {
            setRagStatus(ragResult.value)
            setRagStatusError(null)
        } else {
            setRagStatusError(normalizeError(ragResult.reason))
        }
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
                    <div className="brand">小说创作台</div>
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
                                emptyText="打开项目后会显示在这里"
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
                            <StatusPill tone={serviceStatus.getWritingModelTone(llmStatus, llmStatusError)} label={serviceStatus.formatWritingModelPill(llmStatus, llmStatusError, UI_COPY)} />
                            <StatusPill tone={serviceStatus.getRagTone(ragStatus, ragStatusError)} label={serviceStatus.formatRagStatusLabel(ragStatus, ragStatusError, UI_COPY)} />
                        </>
                    ) : (
                        <StatusPill tone="warning" label="工作台模式：尚未打开项目" />
                    )}
                </div>
            </aside>

            <main className="content">
                <ErrorNotice error={hubLoadError} title="工作台刷新失败" />
                {projectMode ? <ErrorNotice error={coreLoadError} title="核心数据刷新失败" /> : null}
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
                        directorHub={directorHub}
                        directorHubError={directorHubError}
                        llmStatus={serviceStatus.mergeServiceStatusWithError(llmStatus, llmStatusError)}
                        ragStatus={serviceStatus.mergeServiceStatusWithError(ragStatus, ragStatusError)}
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

function getWritingModelTone(llmStatus, loadError) {
    if (loadError) return 'warning'
    if (!llmStatus?.installed) return 'warning'
    const effectiveStatus = llmStatus?.effective_status || llmStatus?.connection_status
    if (effectiveStatus === 'failed') return 'danger'
    if (effectiveStatus === 'degraded') return 'warning'
    if (effectiveStatus === 'connected') return 'good'
    return 'warning'
}

function formatWritingModelPill(llmStatus, loadError) {
    if (loadError) {
        const suffix = llmStatus ? ` ${formatWritingModelValue(llmStatus)}` : ''
        return `${UI_COPY.writingEngine}探活异常，请稍后重试${suffix}`
    }
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
        return llmStatus.version ? `本地命令行（${llmStatus.version}）` : '本地命令行'
    }
    if (llmStatus.mode === 'api') {
        return `模型：${llmStatus.model || '未指定模型'}`
    }
    if (llmStatus.mode === 'mock') {
        return '模拟运行器'
    }
    return llmStatus.provider || '未配置'
}

function getRagTone(ragStatus, loadError) {
    const effectiveStatus = ragStatus?.effective_status || ragStatus?.connection_status
    if (loadError) return 'warning'
    if (!ragStatus?.configured) return 'warning'
    if (effectiveStatus === 'failed') return 'danger'
    if (effectiveStatus === 'connected') return 'good'
    return 'warning'
}

function formatRagStatusLabel(ragStatus, loadError) {
    const effectiveStatus = ragStatus?.effective_status || ragStatus?.connection_status
    const suffix = ragStatus?.embed_model ? ` ${ragStatus.embed_model}` : ''
    if (loadError) {
        return `${UI_COPY.retrievalEngine}探活异常，请稍后重试${suffix}`.trim()
    }
    if (!ragStatus?.configured) return `${UI_COPY.retrievalEngine}未配置`
    if (effectiveStatus === 'failed') {
        return `${UI_COPY.retrievalEngine}连接失败：${formatRagErrorSummary(ragStatus.connection_error || ragStatus.last_error)}`
    }
    if (effectiveStatus === 'connected') {
        return `${UI_COPY.retrievalEngine}已连接${suffix}`.trim()
    }
    if (effectiveStatus === 'not_configured') return `${UI_COPY.retrievalEngine}未配置`
    return `${UI_COPY.retrievalEngine}未连接${suffix}`.trim()
}

function formatRagErrorSummary(error) {
    if (!error) return '未知错误'
    const stage = error?.details?.stage ? String(error.details.stage) : 'embedding'
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
        if (!page || page === 'control') {
            parsed.searchParams.delete(DASHBOARD_PAGE_QUERY_KEY)
        } else {
            parsed.searchParams.set(DASHBOARD_PAGE_QUERY_KEY, page)
        }
    }
    return `${parsed.pathname}${parsed.search}${parsed.hash || ''}`
}

function mergeServiceStatusWithError(status, error) {
    if (!error) return status
    return {
        ...(status || {}),
        effective_status: 'degraded',
        connection_status: 'degraded',
        last_error: error,
    }
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
