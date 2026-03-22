import { useEffect, useRef, useState } from 'react'
import { ErrorNotice, ProjectBootstrapSection } from './appSections.jsx'
import { formatNumber } from './dashboardPageCommon.jsx'
import { normalizeError, postJSON } from './api.js'

export function readLandingPreference(key = 'webnovel.dashboard.landing') {
    if (typeof window === 'undefined') return 'hub'
    const value = String(window.localStorage.getItem(key) || '').trim()
    return value === 'auto_last' ? 'auto_last' : 'hub'
}

export function syncDashboardQuery({ projectRoot, page, bootstrapHint }) {
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search || '')
    if (projectRoot) {
        params.set('project_root', projectRoot)
    } else {
        params.delete('project_root')
    }
    if (!page || page === 'control') {
        params.delete('page')
    } else {
        params.set('page', page)
    }
    if (!bootstrapHint) {
        params.delete('bootstrap_hint')
    } else {
        params.set('bootstrap_hint', bootstrapHint)
    }
    const query = params.toString()
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash || ''}`
    window.history.replaceState({}, '', nextUrl)
}

function writeLandingPreference(key, value) {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(key, value)
}

export function WorkbenchPage({
    hubData,
    tab = 'hub',
    currentProjectRoot,
    landingPreferenceKey,
    landingPreferences,
    onNavigate,
    onTabChange,
    onOpenProject,
    onRefresh,
}) {
    const [message, setMessage] = useState('')
    const [error, setError] = useState(null)
    const [busyKey, setBusyKey] = useState('')
    const [draftRoot, setDraftRoot] = useState('')
    const [landingPreference, setLandingPreference] = useState(() => readLandingPreference(landingPreferenceKey))
    const createPanelRef = useRef(null)

    const currentProject = hubData?.current_project || null
    const missingCards = hubData?.missing_projects || []

    useEffect(() => {
        if (!draftRoot || !createPanelRef.current || typeof createPanelRef.current.scrollIntoView !== 'function') return
        createPanelRef.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, [draftRoot])

    async function pickFolder() {
        const response = await postJSON('/api/workbench/pick-folder', {})
        return String(response?.project_root || '').trim()
    }

    async function handleOpenProject(projectRoot, fallbackUrl = '') {
        if (!projectRoot || !onOpenProject) return
        const response = await onOpenProject(projectRoot, fallbackUrl)
        if (response?.opened) {
            setMessage('')
            setDraftRoot('')
            return
        }
        if (response?.error) {
            setError(response.error)
            return
        }
        if (response?.project_initialized !== false) {
            setError(normalizeError(new Error(response?.next_recommended_action || '打开项目失败，请稍后重试。')))
            return
        }
        setDraftRoot(projectRoot)
        setMessage(response?.next_recommended_action || '该目录尚未初始化，可以直接改为新建项目。')
    }

    async function openPickedProject() {
        setBusyKey('open-existing')
        setError(null)
        setMessage('')
        try {
            const pickedRoot = await pickFolder()
            if (!pickedRoot) return
            await handleOpenProject(pickedRoot)
        } catch (requestError) {
            setError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    async function startCreateFlow() {
        setBusyKey('pick-create')
        setError(null)
        setMessage('')
        try {
            const pickedRoot = await pickFolder()
            if (!pickedRoot) return
            setDraftRoot(pickedRoot)
            setMessage('已预填项目目录。继续填写标题和题材后即可创建项目。')
        } catch (requestError) {
            setError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    async function mutateProject(action, projectRoot) {
        setBusyKey(`${action}:${projectRoot}`)
        setError(null)
        setMessage('')
        try {
            await postJSON(`/api/workbench/${action}`, { project_root: projectRoot })
            if (action === 'remove-project' && projectRoot === currentProjectRoot) {
                onNavigate('/')
                await onRefresh({ projectRoot: '' })
                onTabChange?.('hub')
                return
            }
            await onRefresh()
        } catch (requestError) {
            setError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    async function runTool(action) {
        setBusyKey(`tool:${action}`)
        setError(null)
        setMessage('')
        try {
            await postJSON(`/api/workbench/tools/${action}`, {
                project_root: currentProjectRoot || currentProject?.project_root || '',
            })
            setMessage('已触发工具动作。')
        } catch (requestError) {
            setError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    function updateLandingPreference(nextValue) {
        writeLandingPreference(landingPreferenceKey, nextValue)
        setLandingPreference(nextValue)
    }

    return (
        <div className="page-grid workbench-layout">
            <section className="panel full-span workbench-hero">
                <div className="task-item-header workbench-hero-header">
                    <div>
                        <div className="workbench-eyebrow">工作台</div>
                        <div className="panel-title">项目工作台</div>
                        <div className="workbench-hero-copy">左侧用于快速进入项目，右侧保留项目管理、创建入口和工具动作。工作台本身不再重复堆放整套项目列表。</div>
                    </div>
                </div>
                <div className="tiny workbench-workspace">{`工作区：${hubData?.workspace_root || '未加载'}`}</div>
                <ErrorNotice error={error} />
                {message ? (
                    <div className="planning-warning subtle">
                        <div className="tiny">{message}</div>
                    </div>
                ) : null}
            </section>

            {tab === 'hub' ? (
                <>
                    <section className="panel workbench-panel">
                        <div className="panel-title">默认落地方式</div>
                        <div className="workbench-section-copy">这个偏好只保存在当前浏览器，用来决定双击启动后优先停在工作台，还是自动回到上次项目。</div>
                        <div className="workbench-preference-switch" role="tablist" aria-label="启动落地偏好">
                            {landingPreferences.map((item) => (
                                <button
                                    key={item.value}
                                    type="button"
                                    className={`workbench-preference-option ${landingPreference === item.value ? 'active' : ''}`}
                                    aria-pressed={landingPreference === item.value}
                                    onClick={() => updateLandingPreference(item.value)}
                                >
                                    {item.label}
                                </button>
                            ))}
                        </div>
                    </section>

                    <section className="panel workbench-panel">
                        <div className="panel-title">当前项目</div>
                        <div className="workbench-section-copy">这里保留当前项目的详情与管理动作。真正的快速切换入口已经收口到左侧项目轨道。</div>
                        {currentProject ? (
                            <WorkbenchProjectCard
                                project={currentProject}
                                current
                                busyKey={busyKey}
                                onOpen={() => handleOpenProject(currentProject.project_root, currentProject.dashboard_url)}
                                onPinToggle={() => mutateProject(currentProject.pinned ? 'unpin-project' : 'pin-project', currentProject.project_root)}
                                onRemove={() => mutateProject('remove-project', currentProject.project_root)}
                            />
                        ) : (
                            <div className="empty-state">当前还没有打开任何项目。</div>
                        )}
                    </section>

                    <section className="panel workbench-panel">
                        <div className="panel-title">打开已有项目</div>
                        <div className="workbench-section-copy">通过系统文件夹选择器打开已初始化项目；如果目录尚未初始化，工作台会把目录自动带入新建流程。</div>
                        <button className="primary-button workbench-button" onClick={openPickedProject} disabled={busyKey === 'open-existing'}>
                            {busyKey === 'open-existing' ? '打开中...' : '打开已有项目'}
                        </button>
                    </section>

                    <section ref={createPanelRef} className="panel full-span workbench-panel">
                        <div className="panel-title">新建项目</div>
                        <div className="workbench-section-copy">先选目录，再填写标题和题材。创建成功后会直接进入该项目工作台。</div>
                        <div className="task-row-actions workbench-inline-actions">
                            <button className="secondary-button workbench-button" onClick={startCreateFlow} disabled={busyKey === 'pick-create'}>
                                {busyKey === 'pick-create' ? '选择中...' : '先选项目目录'}
                            </button>
                        </div>
                        <div className="launcher-grid">
                            <ProjectBootstrapSection
                                currentProjectRoot={draftRoot}
                                currentTitle=""
                                currentGenre=""
                                projectInitialized={false}
                                onSuccess={(response) => {
                                    const nextUrl = response?.suggested_dashboard_url || (response?.project_root ? `/?project_root=${encodeURIComponent(response.project_root)}&bootstrap_hint=planning` : '/')
                                    onNavigate(nextUrl)
                                    void onRefresh({ projectRoot: response?.project_root || '' })
                                }}
                            />
                        </div>
                    </section>

                    <section className="panel full-span workbench-panel">
                        <div className="panel-title">失效记录</div>
                        <div className="workbench-section-copy">这里是路径失效或项目损坏的记录，只会清理工作台登记，不会删除磁盘内容。</div>
                        {missingCards.length === 0 ? (
                            <div className="empty-state">没有失效项目记录。</div>
                        ) : (
                            <div className="summary-grid">
                                {missingCards.map((project) => (
                                    <WorkbenchProjectCard
                                        key={project.project_root}
                                        project={project}
                                        busyKey={busyKey}
                                        onOpen={null}
                                        onPinToggle={() => mutateProject(project.pinned ? 'unpin-project' : 'pin-project', project.project_root)}
                                        onRemove={() => mutateProject('remove-project', project.project_root)}
                                    />
                                ))}
                            </div>
                        )}
                    </section>
                </>
            ) : (
                <section className="panel full-span workbench-panel">
                    <div className="panel-title">工具页</div>
                    <div className="workbench-section-copy">这里承接旧启动器里的常用动作，统一做成可直接执行的按钮。</div>
                    <div className="summary-grid">
                        <WorkbenchToolCard
                            title="登录 Codex CLI"
                            description="拉起登录窗口并检查当前登录状态。"
                            actionLabel="立即登录"
                            disabled={false}
                            busy={busyKey === 'tool:login-codex'}
                            onClick={() => runTool('login-codex')}
                        />
                        <WorkbenchToolCard
                            title="打开当前项目终端"
                            description="在当前项目目录打开 PowerShell 窗口。"
                            actionLabel="打开终端"
                            disabled={!currentProject}
                            busy={busyKey === 'tool:open-shell'}
                            onClick={() => runTool('open-shell')}
                        />
                        <WorkbenchToolCard
                            title="开启局域网分享"
                            description="以当前项目启动可局域网访问的创作工作台。"
                            actionLabel="开启局域网模式"
                            disabled={!currentProject}
                            busy={busyKey === 'tool:start-lan-dashboard'}
                            onClick={() => runTool('start-lan-dashboard')}
                        />
                        <WorkbenchToolCard
                            title="打开快速说明"
                            description="用记事本打开中文快速说明。"
                            actionLabel="打开说明"
                            disabled={false}
                            busy={busyKey === 'tool:open-guide'}
                            onClick={() => runTool('open-guide')}
                        />
                    </div>
                </section>
            )}
        </div>
    )
}

function WorkbenchProjectCard({ project, busyKey, current = false, onOpen, onPinToggle, onRemove }) {
    const statusLabel = project.is_missing
        ? '路径已失效'
        : project.is_corrupted
            ? 'state.json 损坏'
            : project.is_initialized
                ? `第 ${project.current_chapter || 0} 章 / ${formatNumber(project.total_words || 0)} 字`
                : '目录未初始化'

    return (
        <div className="summary-card workbench-card workbench-project-card">
            <div className="task-item-header">
                <div className="summary-card-title">{project.title || project.project_root}</div>
                <div className="task-row-actions">
                    {current ? <span className="runtime-badge success">当前项目</span> : null}
                    {project.pinned ? <span className="runtime-badge warning">已固定</span> : null}
                </div>
            </div>
            <div className="tiny task-target">{project.project_root}</div>
            <div className="summary-card-meta">{project.genre || '未填写题材'}</div>
            <div className="summary-card-meta">{statusLabel}</div>
            {project.last_opened_at ? <div className="summary-card-meta">{`最近打开：${project.last_opened_at}`}</div> : null}
            <div className="task-row-actions workbench-card-actions">
                {onOpen ? <button className="primary-button workbench-button" onClick={onOpen}>进入项目</button> : null}
                <button className="secondary-button workbench-button" onClick={onPinToggle} disabled={busyKey === `pin-project:${project.project_root}` || busyKey === `unpin-project:${project.project_root}`}>
                    {project.pinned ? '取消固定' : '固定'}
                </button>
                <button className="ghost-button workbench-button workbench-button-danger" onClick={onRemove} disabled={busyKey === `remove-project:${project.project_root}`}>移除记录</button>
            </div>
        </div>
    )
}

function WorkbenchToolCard({ title, description, actionLabel, disabled, busy, onClick }) {
    return (
        <div className="summary-card workbench-card workbench-tool-card">
            <div className="summary-card-title">{title}</div>
            <div className="summary-card-meta">{description}</div>
            <button className="primary-button workbench-button" onClick={onClick} disabled={disabled || busy}>
                {busy ? '处理中...' : actionLabel}
            </button>
        </div>
    )
}
