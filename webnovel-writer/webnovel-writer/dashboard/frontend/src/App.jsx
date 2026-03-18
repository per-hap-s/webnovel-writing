import { useEffect, useMemo, useRef, useState } from 'react'
import { fetchJSON, subscribeSSE } from './api.js'
import {
    ApiSettingsSection,
    DataPageSection,
    FilesPageSection,
    PlanningProfileSection,
    ProjectBootstrapSection,
    QualityPageSection,
    TaskCenterPageSection,
    TaskLauncherSection,
} from './appSections.jsx'

const NAV_ITEMS = [
    { id: 'control', label: '\u603b\u89c8' },
    { id: 'tasks', label: '\u4efb\u52a1' },
    { id: 'data', label: '\u6570\u636e' },
    { id: 'files', label: '\u6587\u4ef6' },
    { id: 'quality', label: '\u8d28\u91cf' },
]

const MODE_OPTIONS = [
    { value: 'standard', label: '\u6807\u51c6' },
    { value: 'fast', label: '\u5feb\u901f' },
    { value: 'minimal', label: '\u7cbe\u7b80' },
]

const TASK_TEMPLATES = [
    { key: 'init', title: '\u8865\u79cd\u9879\u76ee\u9aa8\u67b6\uff08\u65e7\u5165\u53e3\uff09', fields: ['project_root'] },
    { key: 'plan', title: '\u89c4\u5212\u5377', fields: ['volume', 'mode'] },
    { key: 'write', title: '\u64b0\u5199\u7ae0\u8282', fields: ['chapter', 'mode', 'require_manual_approval'] },
    { key: 'review', title: '\u6267\u884c\u5ba1\u67e5', fields: ['chapter_range', 'mode'] },
    { key: 'resume', title: '\u6062\u590d\u4efb\u52a1', fields: ['mode'] },
]

const PROJECT_BOOTSTRAP_TEMPLATE = {
    key: 'bootstrap',
    endpoint: '/api/project/bootstrap',
    title: '\u521b\u5efa\u9879\u76ee',
    submitLabel: '\u521b\u5efa\u9879\u76ee',
    fields: ['project_root', 'title', 'genre'],
}

const TASK_TYPE_LABELS = {
    init: '\u65e7\u521d\u59cb\u5316',
    plan: '\u89c4\u5212\u5377',
    write: '\u64b0\u5199\u7ae0\u8282',
    review: '\u6267\u884c\u5ba1\u67e5',
    resume: '\u6062\u590d\u4efb\u52a1',
}

const STATUS_LABELS = {
    queued: '\u5df2\u6392\u961f',
    running: '\u8fd0\u884c\u4e2d',
    awaiting_writeback_approval: '\u7b49\u5f85\u56de\u5199\u5ba1\u6279',
    completed: '\u5df2\u5b8c\u6210',
    failed: '\u5931\u8d25',
    interrupted: '\u5df2\u4e2d\u65ad',
    rejected: '\u5df2\u62d2\u7edd',
}

const APPROVAL_STATUS_LABELS = {
    not_required: '\u65e0\u9700\u5ba1\u6279',
    pending: '\u5f85\u6279\u51c6\u56de\u5199',
    approved: '\u5df2\u6279\u51c6',
    rejected: '\u5df2\u62d2\u7edd',
}

const STEP_LABELS = {
    init: '\u521d\u59cb\u5316',
    plan: '\u89c4\u5212',
    resume: '\u6062\u590d',
    context: '\u4e0a\u4e0b\u6587\u51c6\u5907',
    draft: '\u8349\u7a3f\u751f\u6210',
    'consistency-review': '\u4e00\u81f4\u6027\u5ba1\u67e5',
    'continuity-review': '\u8fde\u7eed\u6027\u5ba1\u67e5',
    'ooc-review': '\u89d2\u8272\u4e00\u81f4\u6027\u5ba1\u67e5',
    'review-summary': '\u5ba1\u67e5\u6c47\u603b',
    polish: '\u6da6\u8272',
    'approval-gate': '\u5ba1\u6279\u5173\u5361',
    'data-sync': '\u6570\u636e\u540c\u6b65',
    idle: '\u7a7a\u95f2',
}

const EVENT_LEVEL_LABELS = {
    info: '\u4fe1\u606f',
    warning: '\u8b66\u544a',
    error: '\u9519\u8bef',
}

const TABLE_HEADER_LABELS = {
    name: '\u540d\u79f0',
    canonical_name: '\u6807\u51c6\u540d\u79f0',
    type: '\u7c7b\u578b',
    tier: '\u5c42\u7ea7',
    last_appearance: '\u6700\u540e\u51fa\u73b0\u7ae0\u8282',
    from_entity: '\u8d77\u59cb\u5b9e\u4f53',
    to_entity: '\u76ee\u6807\u5b9e\u4f53',
    from_entity_display: '\u8d77\u59cb\u5b9e\u4f53',
    to_entity_display: '\u76ee\u6807\u5b9e\u4f53',
    type_label: '\u5173\u7cfb\u7c7b\u578b',
    chapter: '\u7ae0\u8282',
    title: '\u6807\u9898',
    location: '\u5730\u70b9',
    word_count: '\u5b57\u6570',
    end_chapter: '\u7ed3\u675f\u7ae0\u8282',
    overall_score: '\u603b\u8bc4\u5206',
    created_at: '\u521b\u5efa\u65f6\u95f4',
    template: '\u6a21\u677f',
    score: '\u5206\u6570',
    completion_rate: '\u5b8c\u6210\u7387',
    query_type: '\u67e5\u8be2\u7c7b\u578b',
    query: '\u67e5\u8be2\u5185\u5bb9',
    results_count: '\u7ed3\u679c\u6570',
    latency_ms: '\u5ef6\u8fdf(ms)',
    tool_name: '\u5de5\u5177\u540d',
    success: '\u6210\u529f',
    retry_count: '\u91cd\u8bd5\u6b21\u6570',
    source_type: '\u6765\u6e90\u7c7b\u578b',
    source_id: '\u6765\u6e90 ID',
    from_entity_name: '\u8d77\u59cb\u5b9e\u4f53',
    to_entity_name: '\u76ee\u6807\u5b9e\u4f53',
    target_label: '\u4efb\u52a1\u76ee\u6807',
}

const RELATIONSHIP_TYPE_LABELS = {
    family: '\u5bb6\u5ead',
    ally: '\u540c\u76df',
    enemy: '\u654c\u5bf9',
    mentor: '\u5e08\u53cb',
    subordinate: '\u4e0a\u4e0b\u7ea7',
    colleague: '\u540c\u4e8b',
    suspect: '\u5acc\u7591',
    investigating: '\u8c03\u67e5',
    conflict: '\u51b2\u7a81',
    owes: '\u6b20\u8d26',
    protects: '\u4fdd\u62a4',
    watches: '\u76d1\u89c6',
    warned_by: '\u9884\u8b66\u6765\u6e90',
}

const EXACT_EVENT_MESSAGES = {
    'Retry requested': '\u5df2\u8bf7\u6c42\u91cd\u8bd5',
    'Writeback approved': '\u5df2\u6279\u51c6\u56de\u5199',
    'Writeback rejected': '\u5df2\u62d2\u7edd\u56de\u5199',
    'Rejected by operator': '\u5df2\u88ab\u64cd\u4f5c\u4eba\u62d2\u7edd',
    'Schema validation failed': '\u7ed3\u6784\u6821\u9a8c\u5931\u8d25',
    'Task completed': '\u4efb\u52a1\u5df2\u5b8c\u6210',
    'Review summary persisted': '\u5ba1\u67e5\u6c47\u603b\u5df2\u5199\u5165',
    'Review gate blocked execution': '\u5ba1\u67e5\u95f8\u95e8\u963b\u6b62\u7ee7\u7eed\u6267\u884c',
    'Waiting for writeback approval': '\u7b49\u5f85\u56de\u5199\u5ba1\u6279',
    'Write target normalized': '\u5df2\u6309\u4efb\u52a1\u7ae0\u8282\u53f7\u7ea0\u6b63\u5199\u56de\u76ee\u6807',
    'Data sync completed': '\u5199\u56de\u540c\u6b65\u5b8c\u6210',
    'Data sync payload enriched': '\u5df2\u8865\u9f50\u5199\u56de\u6240\u9700\u7684\u7ed3\u6784\u5316\u4fe1\u606f',
    'Plan writeback completed': '\u5377\u89c4\u5212\u5199\u56de\u5b8c\u6210',
    'Core setting docs synced': '\u6838\u5fc3\u8bbe\u5b9a\u96c6\u5df2\u66f4\u65b0',
    'Chapter body written': '\u6b63\u6587\u5df2\u5199\u5165',
    'Step writeback failed': '\u6b65\u9aa4\u5199\u56de\u5931\u8d25',
    'Resume target resolved': '\u5df2\u786e\u5b9a\u9700\u8981\u6062\u590d\u7684\u4efb\u52a1',
    'Resume target scheduled': '\u5df2\u91cd\u65b0\u6392\u5165\u6062\u590d\u961f\u5217',
    'Resume target already running': '\u76ee\u6807\u4efb\u52a1\u6b63\u5728\u8fd0\u884c\uff0c\u65e0\u9700\u91cd\u590d\u6062\u590d',
    'Resume schedule failed': '\u6062\u590d\u6392\u7a0b\u5931\u8d25',
    'Task scheduled for resume': '\u4efb\u52a1\u5df2\u51c6\u5907\u6062\u590d',
    'Task auto-completed during resume recovery': '\u6062\u590d\u68c0\u67e5\u65f6\u68c0\u6d4b\u5230\u4efb\u52a1\u5df2\u5b8c\u6210',
    'Resume target failed': '\u6062\u590d\u76ee\u6807\u6267\u884c\u5931\u8d25',
    'Workflow spec not found': '\u672a\u627e\u5230\u5de5\u4f5c\u6d41\u5951\u7ea6',
    'Workflow parse failed': '\u5de5\u4f5c\u6d41\u5951\u7ea6\u89e3\u6790\u5931\u8d25',
    'Workflow config error': '\u5de5\u4f5c\u6d41\u914d\u7f6e\u6709\u8bef',
    'Task execution failed': '\u4efb\u52a1\u6267\u884c\u5931\u8d25',
    plan_blocked: '\u89c4\u5212\u5f85\u8865\u4fe1\u606f',
    writeback_rollback_started: '\u5f00\u59cb\u56de\u6eda\u5931\u8d25\u5199\u56de',
    writeback_rollback_finished: '\u5931\u8d25\u5199\u56de\u5df2\u56de\u6eda',
}

Object.assign(EXACT_EVENT_MESSAGES, {
    'Review summary prepared': '\u5ba1\u67e5\u6c47\u603b\u5df2\u751f\u6210',
    'prompt_compiled': '\u63d0\u793a\u8bcd\u5df2\u7ec4\u88c5\u5b8c\u6210',
    'request_dispatched': '\u5df2\u5411\u4e0a\u6e38\u53d1\u51fa\u8bf7\u6c42',
    'awaiting_model_response': '\u6b63\u5728\u7b49\u5f85\u6a21\u578b\u54cd\u5e94',
    'response_received': '\u5df2\u6536\u5230\u6a21\u578b\u54cd\u5e94',
    'parsing_output': '\u6b63\u5728\u89e3\u6790\u8f93\u51fa',
    'step_heartbeat': '\u6b65\u9aa4\u4ecd\u5728\u8fd0\u884c',
    'step_retry_scheduled': '\u5df2\u5b89\u6392\u6b65\u9aa4\u91cd\u8bd5',
    'step_retry_started': '\u6b65\u9aa4\u91cd\u8bd5\u5f00\u59cb',
    'step_waiting_approval': '\u7b49\u5f85\u4eba\u5de5\u6279\u51c6\u56de\u5199',
    'step_auto_retried': '\u6b65\u9aa4\u5df2\u81ea\u52a8\u91cd\u8bd5',
    'raw_output_parse_failed': '\u539f\u59cb\u8f93\u51fa\u89e3\u6790\u5931\u8d25',
    'json_extraction_recovered': '\u5df2\u4ece\u539f\u59cb\u8f93\u51fa\u4e2d\u6062\u590d JSON',
})

const UI_COPY = {
    overviewPlanningTitle: '\u89c4\u5212\u5fc5\u586b\u4fe1\u606f',
    projectCreateHint: '\u4ec5\u7528\u4e8e\u65b0\u7a7a\u76ee\u5f55\u521b\u5efa\u9879\u76ee\uff1b\u5982\u679c\u4f60\u662f\u4ece\u684c\u9762\u542f\u52a8\u5668\u8fdb\u5165\uff0c\u901a\u5e38\u4e0d\u7528\u518d\u70b9\u201c\u521b\u5efa\u9879\u76ee\u201d\u3002',
    taskEntryHint: '\u4e3b\u94fe\u5efa\u8bae\u6309\u201c\u89c4\u5212\u5377 -> \u64b0\u5199\u7ae0\u8282 -> \u6267\u884c\u5ba1\u67e5 / \u6062\u590d\u4efb\u52a1\u201d\u4f7f\u7528\uff1b\u201c\u8865\u79cd\u9879\u76ee\u9aa8\u67b6\uff08\u65e7\u5165\u53e3\uff09\u201d\u53ea\u7528\u4e8e\u517c\u5bb9\u65e7\u9879\u76ee\u3002',
    planningHint: '\u5148\u628a\u8fd9\u91cc\u7684\u89c4\u5212\u4fe1\u606f\u8865\u9f50\uff0c\u518d\u8fd0\u884c\u201c\u89c4\u5212\u5377\u201d\u3002\u5982\u679c\u4fe1\u606f\u4e0d\u8db3\uff0c\u7cfb\u7edf\u4f1a\u63d0\u793a\u4f60\u56de\u5230\u8fd9\u91cc\u7ee7\u7eed\u8865\u8d44\u6599\u3002',
    planBlockedStatus: '\u5df2\u5b8c\u6210 / \u5f85\u8865\u8d44\u6599',
    planBlockedStep: '\u5f85\u8865\u8d44\u6599',
    approvalNotApplicable: '\u4e0d\u9002\u7528',
    approvalNotRequired: '\u672c\u4efb\u52a1\u65e0\u9700\u4f60\u5904\u7406',
    approvalNotReached: '\u5c1a\u672a\u8fdb\u5165\u5ba1\u6279',
    approvalPending: '\u7b49\u4f60\u6279\u51c6\u56de\u5199',
    approvalApproved: '\u5df2\u6279\u51c6',
    approvalApprovedWritingBack: '\u4f60\u5df2\u6279\u51c6\uff0c\u7cfb\u7edf\u6b63\u5728\u5199\u56de',
    approvalApprovedCompleted: '\u5df2\u6279\u51c6\uff0c\u5199\u56de\u5df2\u5b8c\u6210',
    approvalRejected: '\u5df2\u62d2\u7edd\u56de\u5199',
    unknownSystemEvent: '\u7cfb\u7edf\u4e8b\u4ef6',
    unknownSystemEventWithDetail: '\u7cfb\u7edf\u4e8b\u4ef6\uff08\u8bf7\u67e5\u770b\u8be6\u60c5\u533a\uff09',
    writingEngine: '\u5199\u4f5c\u5f15\u64ce',
    retrievalEngine: '\u68c0\u7d22\u5f15\u64ce',
}

export default function App() {
    const [page, setPage] = useState('control')
    const [projectInfo, setProjectInfo] = useState(null)
    const [llmStatus, setLlmStatus] = useState(null)
    const [ragStatus, setRagStatus] = useState(null)
    const [tasks, setTasks] = useState([])
    const [selectedTaskId, setSelectedTaskId] = useState(null)
    const [refreshToken, setRefreshToken] = useState(0)
    const [connected, setConnected] = useState(false)
    const refreshDebounceRef = useRef(null)
    const lastStatusRefreshRef = useRef(0)

    useEffect(() => {
        reloadCore()
    }, [refreshToken])

    useEffect(() => {
        reloadServiceStatus()
        const dispose = subscribeSSE(
            () => {
                if (refreshDebounceRef.current) {
                    window.clearTimeout(refreshDebounceRef.current)
                }
                refreshDebounceRef.current = window.setTimeout(() => {
                    refreshDebounceRef.current = null
                    setRefreshToken((value) => value + 1)
                    if (Date.now() - lastStatusRefreshRef.current > 60000) {
                        reloadServiceStatus()
                    }
                }, 250)
            },
            {
                onOpen: () => setConnected(true),
                onError: () => setConnected(false),
            },
        )
        const statusTimer = window.setInterval(() => {
            reloadServiceStatus()
        }, 60000)
        return () => {
            dispose()
            window.clearInterval(statusTimer)
            if (refreshDebounceRef.current) {
                window.clearTimeout(refreshDebounceRef.current)
                refreshDebounceRef.current = null
            }
            setConnected(false)
        }
    }, [])

    function reloadCore() {
        fetchJSON('/api/project/info').then(setProjectInfo).catch(() => setProjectInfo(null))
        fetchJSON('/api/tasks').then((items) => {
            setTasks(items)
            setSelectedTaskId((currentId) => {
                if (items.length === 0) return null
                if (currentId && items.some((item) => item.id === currentId)) return currentId
                return items[0].id
            })
        }).catch(() => setTasks([]))
    }

    function reloadServiceStatus() {
        lastStatusRefreshRef.current = Date.now()
        fetchJSON('/api/llm/status').then(setLlmStatus).catch(() => setLlmStatus(null))
        fetchJSON('/api/rag/status').then(setRagStatus).catch(() => setRagStatus(null))
    }

    const selectedTask = useMemo(() => tasks.find((item) => item.id === selectedTaskId) || null, [tasks, selectedTaskId])
    const projectMeta = projectInfo?.project_info || projectInfo || {}
    const dashboardContext = projectInfo?.dashboard_context || {}
    const projectTitle = projectMeta?.project_name || projectMeta?.title || dashboardContext?.title || '\u672a\u52a0\u8f7d\u9879\u76ee'

    return (
        <div className="shell">
            <aside className="sidebar">
                <div>
                    <div className="brand">{'\u5c0f\u8bf4\u63a7\u5236\u53f0'}</div>
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
                    <StatusPill tone={connected ? 'good' : 'danger'} label={connected ? '\u5b9e\u65f6\u540c\u6b65\u5df2\u8fde\u63a5' : '\u5b9e\u65f6\u540c\u6b65\u5df2\u65ad\u5f00'} />
                    <StatusPill tone={getWritingModelTone(llmStatus)} label={formatWritingModelPill(llmStatus)} />
                    <StatusPill tone={getRagTone(ragStatus)} label={formatRagStatusLabel(ragStatus)} />
                </div>
            </aside>

            <main className="content">
                {page === 'control' && (
                    <ControlPage
                        projectInfo={projectInfo}
                        llmStatus={llmStatus}
                        ragStatus={ragStatus}
                        onTaskCreated={(task) => {
                            setTasks((items) => [task, ...items.filter((item) => item.id !== task.id)])
                            setSelectedTaskId(task.id)
                            setPage('tasks')
                            setRefreshToken((value) => value + 1)
                        }}
                        onProjectBootstrapped={(response) => {
                            if (response?.project_switch_required && response?.project_root) {
                                const nextUrl = response.suggested_dashboard_url || `/?project_root=${encodeURIComponent(response.project_root)}`
                                window.location.assign(nextUrl)
                                return
                            }
                            setPage('control')
                            setRefreshToken((value) => value + 1)
                        }}
                    />
                )}
                {page === 'tasks' && (
                    <TaskCenterPage
                        tasks={tasks}
                        selectedTask={selectedTask}
                        onSelectTask={setSelectedTaskId}
                        onMutated={() => setRefreshToken((value) => value + 1)}
                        onNavigateOverview={() => setPage('control')}
                    />
                )}
                {page === 'data' && <DataPage refreshToken={refreshToken} />}
                {page === 'files' && <FilesPage refreshToken={refreshToken} />}
                {page === 'quality' && <QualityPage refreshToken={refreshToken} onMutated={() => setRefreshToken((value) => value + 1)} />}
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
    if (!llmStatus?.installed) return '\u672a\u914d\u7f6e\u53ef\u7528\u7684\u5199\u4f5c\u5f15\u64ce'
    const effectiveStatus = llmStatus?.effective_status || llmStatus?.connection_status
    if (effectiveStatus === 'failed') return `${UI_COPY.writingEngine}\u8fde\u63a5\u5931\u8d25 ${formatWritingModelValue(llmStatus)}`
    if (effectiveStatus === 'degraded') return `${UI_COPY.writingEngine}\u63a2\u6d3b\u5f02\u5e38\uff0c\u4f46\u6700\u8fd1\u8fd0\u884c\u6210\u529f ${formatWritingModelValue(llmStatus)}`
    if (effectiveStatus === 'connected') return `${UI_COPY.writingEngine}\u5df2\u8fde\u63a5 ${formatWritingModelValue(llmStatus)}`
    return `${UI_COPY.writingEngine}\u5df2\u914d\u7f6e ${formatWritingModelValue(llmStatus)}`
}

function formatWritingModelValue(llmStatus) {
    if (!llmStatus) return '\u672a\u914d\u7f6e'
    if (llmStatus.mode === 'cli') {
        return llmStatus.version ? `\u672c\u5730 CLI\uff08${llmStatus.version}\uff09` : '\u672c\u5730 CLI'
    }
    if (llmStatus.mode === 'api') {
        const model = llmStatus.model || '\u672a\u6307\u5b9a\u6a21\u578b'
        return `\u6a21\u578b\uff1a${model}`
    }
    if (llmStatus.mode === 'mock') {
        return '\u6a21\u62df\u8fd0\u884c\u5668'
    }
    return llmStatus.provider || '\u672a\u914d\u7f6e'
}

function formatWritingModelDetail(llmStatus) {
    if (!llmStatus?.installed) return '\u672a\u914d\u7f6e'
    const effectiveStatus = llmStatus?.effective_status || llmStatus?.connection_status
    const statusSuffix = effectiveStatus === 'connected'
        ? '\uff08\u5df2\u8054\u901a\uff09'
        : effectiveStatus === 'degraded'
            ? '\uff08\u63a2\u6d3b\u5f02\u5e38\uff0c\u6700\u8fd1\u6267\u884c\u6210\u529f\uff09'
        : effectiveStatus === 'failed'
            ? '\uff08\u8fde\u63a5\u5931\u8d25\uff09'
            : '\uff08\u5df2\u914d\u7f6e\uff09'
    if (llmStatus.mode === 'cli') {
        const base = llmStatus.binary ? `\u672c\u5730 CLI\uff08${llmStatus.binary}\uff09` : '\u672c\u5730 CLI'
        return `${base}${statusSuffix}`
    }
    if (llmStatus.mode === 'api') {
        const model = llmStatus.model || '\u672a\u6307\u5b9a\u6a21\u578b'
        return `\u6a21\u578b\uff1a${model}${statusSuffix}`
    }
    return `${llmStatus.provider || '\u5df2\u914d\u7f6e'}${statusSuffix}`
}

function getRagTone(ragStatus) {
    if (!ragStatus?.configured) return 'warning'
    if (ragStatus?.connection_status === 'failed') return 'danger'
    if (ragStatus?.connection_status === 'connected') return 'good'
    return 'warning'
}

function formatRagStatusLabel(ragStatus) {
    if (!ragStatus?.configured) return `${UI_COPY.retrievalEngine}\u672a\u914d\u7f6e`
    if (ragStatus?.connection_status === 'failed') return `${UI_COPY.retrievalEngine}\u8fde\u63a5\u5931\u8d25\uff1a${formatRagErrorSummary(ragStatus.connection_error || ragStatus.last_error)}`
    if (ragStatus?.connection_status === 'connected') return `${UI_COPY.retrievalEngine}\u5df2\u8fde\u63a5 ${ragStatus?.embed_model || ''}`.trim()
    return `${UI_COPY.retrievalEngine}\u5df2\u914d\u7f6e ${ragStatus?.embed_model || ''}`.trim()
}

function formatRagDetail(ragStatus) {
    if (!ragStatus?.configured) return '\u672a\u914d\u7f6e'
    if (ragStatus?.connection_status === 'failed') return '\u8fde\u63a5\u5931\u8d25'
    if (ragStatus?.connection_status === 'connected') return '\u5df2\u8054\u901a'
    return '\u5df2\u914d\u7f6e'
}

function formatRagErrorSummary(error) {
    if (!error) return '\u672a\u77e5\u9519\u8bef'
    const stage = error?.details?.stage ? `${error.details.stage}` : '\u68c0\u7d22'
    const code = error?.code || 'UNKNOWN'
    return `${stage} / ${code}`
}

function ControlPage({ projectInfo, llmStatus, ragStatus, onTaskCreated, onProjectBootstrapped }) {
    const projectMeta = projectInfo?.project_info || projectInfo || {}
    const dashboardContext = projectInfo?.dashboard_context || {}

    return (
        <div className="page-grid">
            <section className="panel hero-panel">
                <div className="panel-title">{'\u9879\u76ee\u6982\u89c8'}</div>
                <div className="metric-grid">
                    <MetricCard label={'\u603b\u5b57\u6570'} value={formatNumber(projectInfo?.progress?.total_words || 0)} />
                    <MetricCard label={'\u5f53\u524d\u7ae0\u8282'} value={`\u7b2c ${projectInfo?.progress?.current_chapter || 0} \u7ae0`} />
                    <MetricCard label={'\u9898\u6750'} value={projectMeta?.genre || '\u672a\u77e5'} />
                    <MetricCard label={UI_COPY.writingEngine} value={formatWritingModelDetail(llmStatus)} />
                    <MetricCard label={UI_COPY.retrievalEngine} value={formatRagDetail(ragStatus)} />
                </div>
                {(ragStatus?.connection_status === 'failed' || ragStatus?.last_error) && <div className="empty-state">{`${UI_COPY.retrievalEngine}\u6700\u8fd1\u9519\u8bef\uff1a`}{formatRagErrorSummary(ragStatus.connection_error || ragStatus.last_error)}</div>}
            </section>
            <section className="panel">
                <div className="panel-title">{'\u9879\u76ee\u521b\u5efa'}</div>
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
                <div className="panel-title">{'\u4efb\u52a1\u5165\u53e3'}</div>
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
                <div className="panel-title">{UI_COPY.overviewPlanningTitle}</div>
                <div className="empty-state">{UI_COPY.planningHint}</div>
                <PlanningProfileSection onSaved={() => onProjectBootstrapped()} />
            </section>
            <section className="panel full-span">
                <div className="panel-title">{'API \u63a5\u5165\u8bbe\u7f6e'}</div>
                <div className="empty-state">{'\u5728\u8fd9\u91cc\u586b\u5199\u5199\u4f5c\u6a21\u578b\u548c RAG \u63a5\u53e3\u914d\u7f6e\uff0c\u4fdd\u5b58\u540e\u4f1a\u5199\u5165\u9879\u76ee\u6839\u76ee\u5f55 `.env` \u5e76\u7acb\u5373\u5237\u65b0\u5f53\u524d\u9762\u677f\u72b6\u6001\u3002'}</div>
                <ApiSettingsSection
                    llmStatus={llmStatus}
                    ragStatus={ragStatus}
                    onSaved={() => onProjectBootstrapped()}
                />
            </section>
        </div>
    )
}

function MetricCard({ label, value }) {
    return (
        <div className="metric-card">
            <div className="metric-label">{label}</div>
            <div className="metric-value">{value}</div>
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

function SimpleTable({ rows, columns }) {
    if (!rows.length) return <div className="empty-state">{'\u6682\u65e0\u6570\u636e'}</div>
    return (
        <div className="table-wrap">
            <table>
                <thead>
                    <tr>
                        {columns.map((column) => <th key={column}>{translateColumnLabel(column)}</th>)}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, index) => (
                        <tr key={row.id || row.chapter || index}>
                            {columns.map((column) => <td key={column}>{formatCell(resolveColumnValue(row, column), column)}</td>)}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}

function translateTaskType(value) {
    return TASK_TYPE_LABELS[value] || value || '-'
}

function translateTaskStatus(value) {
    return STATUS_LABELS[value] || value || '-'
}

function isPlanBlockedTask(task) {
    return Boolean(task?.task_type === 'plan' && task?.status === 'completed' && task?.artifacts?.plan_blocked)
}

function resolveTaskStatusLabel(task) {
    if (isPlanBlockedTask(task)) return UI_COPY.planBlockedStatus
    return translateTaskStatus(task?.status)
}

function resolveCurrentStepLabel(task) {
    if (isPlanBlockedTask(task)) return UI_COPY.planBlockedStep
    const runtimeStep = task?.runtime_status?.step_key
    if (['completed', 'failed'].includes(task?.status) && task?.runtime_status?.phase_label) {
        return task.runtime_status.phase_label
    }
    if (['completed', 'failed'].includes(task?.status) && runtimeStep) {
        return translateStepName(runtimeStep)
    }
    return translateStepName(task?.current_step || runtimeStep || 'idle')
}

function translateApprovalStatus(value) {
    if (value === 'n/a') return UI_COPY.approvalNotApplicable
    return APPROVAL_STATUS_LABELS[value] || value || '-'
}

function resolveApprovalStatusLabel(task) {
    const approvalStatus = task?.approval_status || 'n/a'
    if (task?.task_type !== 'write') return translateApprovalStatus(approvalStatus)
    if (!task?.request?.require_manual_approval) return UI_COPY.approvalNotRequired
    if (approvalStatus === 'approved') {
        if (task?.status === 'completed') return UI_COPY.approvalApprovedCompleted
        if (['queued', 'running'].includes(task?.status) && ['approval-gate', 'data-sync'].includes(task?.current_step)) {
            return UI_COPY.approvalApprovedWritingBack
        }
        return UI_COPY.approvalApproved
    }
    if (approvalStatus === 'pending' || task?.status === 'awaiting_writeback_approval') return UI_COPY.approvalPending
    if (approvalStatus === 'rejected') return UI_COPY.approvalRejected
    return UI_COPY.approvalNotReached
}

function resolveTaskTargetLabel(task) {
    if (task?.runtime_status?.target_label) return task.runtime_status.target_label
    const request = task?.request || {}
    if (task?.task_type === 'plan') {
        return `\u7b2c ${request.volume || 1} \u5377`
    }
    if (task?.task_type === 'write' && request.chapter) {
        return `\u7b2c ${request.chapter} \u7ae0`
    }
    if (task?.task_type === 'review' && request.chapter_range) {
        return `\u7b2c ${request.chapter_range} \u7ae0`
    }
    if (task?.task_type === 'resume') {
        return request.chapter ? `\u6062\u590d\u7b2c ${request.chapter} \u7ae0` : '\u6062\u590d\u6700\u8fd1\u4e2d\u65ad\u4efb\u52a1'
    }
    return '-'
}

function translateStepName(value) {
    if (value === 'task') return '\u4efb\u52a1'
    return STEP_LABELS[value] || value || '-'
}

function translateEventLevel(value) {
    return EVENT_LEVEL_LABELS[value] || value || '-'
}

function translateColumnLabel(column) {
    return TABLE_HEADER_LABELS[column] || column
}

function translateKnownValue(value) {
    if (typeof value !== 'string') return value
    if (TASK_TYPE_LABELS[value]) return TASK_TYPE_LABELS[value]
    if (STATUS_LABELS[value]) return STATUS_LABELS[value]
    if (APPROVAL_STATUS_LABELS[value]) return APPROVAL_STATUS_LABELS[value]
    if (STEP_LABELS[value]) return STEP_LABELS[value]
    if (EVENT_LEVEL_LABELS[value]) return EVENT_LEVEL_LABELS[value]
    if (RELATIONSHIP_TYPE_LABELS[value]) return RELATIONSHIP_TYPE_LABELS[value]
    if (value === 'plot') return '\u5267\u60c5\u6a21\u677f'
    return value
}

function translateEventMessage(message) {
    if (!message) return '-'
    if (EXACT_EVENT_MESSAGES[message]) return EXACT_EVENT_MESSAGES[message]

    const queuedMatch = message.match(/^Task queued[:\uff1a](.+)$/)
    if (queuedMatch) return `\u4efb\u52a1\u5df2\u52a0\u5165\u961f\u5217\uff1a${translateTaskType(queuedMatch[1])}`

    const stepStartMatch = message.match(/^Step started[:\uff1a](.+)$/)
    if (stepStartMatch) return `\u6b65\u9aa4\u5f00\u59cb\uff1a${translateStepName(stepStartMatch[1])}`

    const stepDoneMatch = message.match(/^Step completed[:\uff1a](.+)$/)
    if (stepDoneMatch) return `\u6b65\u9aa4\u5b8c\u6210\uff1a${translateStepName(stepDoneMatch[1])}`

    const stepFailedMatch = message.match(/^Step failed[:\uff1a](.+)$/)
    if (stepFailedMatch) return `\u6b65\u9aa4\u5931\u8d25\uff1a${translateStepName(stepFailedMatch[1])}`

    return /^[\x00-\x7F\s:._/-]+$/.test(message) ? UI_COPY.unknownSystemEventWithDetail : message
}

function resolveColumnValue(row, column) {
    if (row[column] !== undefined && row[column] !== null && row[column] !== '') return row[column]
    if (column === 'name') return row.name ?? row.canonical_name
    if (column === 'tier') return row.tier ?? row.importance ?? row.level
    if (column === 'location') return row.location ?? row.scene_location ?? row.place
    return row[column]
}

function formatCell(value, column) {
    if (value === null || value === undefined || value === '') return '-'
    if (typeof value === 'boolean') return value ? '\u662f' : '\u5426'
    if (typeof value === 'object') return JSON.stringify(value)
    if (column === 'chapter') return String(value)
    if (column === 'type') return String(translateKnownValue(value))
    if (isDateTimeColumn(column)) return formatTimestampShort(value)
    return String(translateKnownValue(value))
}

function isDateTimeColumn(column) {
    return ['created_at', 'updated_at', 'last_event_at', 'last_activity_at'].includes(column)
}

function formatTimestampShort(value) {
    if (!value) return '-'
    const text = String(value)
    const normalized = text.endsWith('Z') ? text : `${text.replace(' ', 'T')}`
    const parsed = new Date(normalized)
    if (Number.isNaN(parsed.getTime())) {
        return text.replace('T', ' ').replace(/\.\d+/, '')
    }
    const year = parsed.getFullYear()
    const month = String(parsed.getMonth() + 1).padStart(2, '0')
    const day = String(parsed.getDate()).padStart(2, '0')
    const hour = String(parsed.getHours()).padStart(2, '0')
    const minute = String(parsed.getMinutes()).padStart(2, '0')
    const second = String(parsed.getSeconds()).padStart(2, '0')
    return `${year}-${month}-${day} ${hour}:${minute}:${second}`
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString('zh-CN')
}
