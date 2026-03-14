import { useEffect, useMemo, useState } from 'react'
import { fetchJSON, subscribeSSE } from './api.js'
import {
    ApiSettingsSection,
    DataPageSection,
    FilesPageSection,
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
    { key: 'init', title: '\u5206\u6790\u73b0\u6709\u9879\u76ee', fields: ['project_root'] },
    { key: 'plan', title: '\u89c4\u5212\u5377', fields: ['volume', 'mode'] },
    { key: 'write', title: '\u64b0\u5199\u7ae0\u8282', fields: ['chapter', 'mode', 'require_manual_approval'] },
    { key: 'review', title: '\u6267\u884c\u5ba1\u67e5', fields: ['chapter_range', 'mode'] },
    { key: 'resume', title: '\u6062\u590d\u6d41\u7a0b', fields: ['mode'] },
]

const PROJECT_BOOTSTRAP_TEMPLATE = {
    key: 'bootstrap',
    endpoint: '/api/project/bootstrap',
    title: '\u521b\u5efa\u9879\u76ee',
    submitLabel: '\u521b\u5efa\u9879\u76ee',
    fields: ['project_root', 'title', 'genre'],
}

const TASK_TYPE_LABELS = {
    init: '\u521d\u59cb\u5316',
    plan: '\u89c4\u5212',
    write: '\u5199\u4f5c',
    review: '\u5ba1\u67e5',
    resume: '\u6062\u590d',
}

const STATUS_LABELS = {
    queued: '\u5df2\u6392\u961f',
    running: '\u8fd0\u884c\u4e2d',
    awaiting_writeback_approval: '\u7b49\u5f85\u56de\u5199\u5ba1\u6279',
    completed: '\u5df2\u5b8c\u6210',
    failed: '\u5931\u8d25',
    rejected: '\u5df2\u62d2\u7edd',
}

const APPROVAL_STATUS_LABELS = {
    not_required: '\u65e0\u9700\u5ba1\u6279',
    pending: '\u5f85\u5ba1\u6279',
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
    canonical_name: '\u6807\u51c6\u540d\u79f0',
    type: '\u7c7b\u578b',
    tier: '\u5c42\u7ea7',
    last_appearance: '\u6700\u540e\u51fa\u73b0\u7ae0\u8282',
    from_entity: '\u8d77\u59cb\u5b9e\u4f53',
    to_entity: '\u76ee\u6807\u5b9e\u4f53',
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

    useEffect(() => {
        reloadAll()
    }, [refreshToken])

    useEffect(() => {
        const dispose = subscribeSSE(
            () => setRefreshToken((value) => value + 1),
            {
                onOpen: () => setConnected(true),
                onError: () => setConnected(false),
            },
        )
        return () => {
            dispose()
            setConnected(false)
        }
    }, [])

    function reloadAll() {
        fetchJSON('/api/project/info').then(setProjectInfo).catch(() => setProjectInfo(null))
        fetchJSON('/api/llm/status').then(setLlmStatus).catch(() => setLlmStatus(null))
        fetchJSON('/api/rag/status').then(setRagStatus).catch(() => setRagStatus(null))
        fetchJSON('/api/tasks').then((items) => {
            setTasks(items)
            if (!selectedTaskId && items.length > 0) {
                setSelectedTaskId(items[0].id)
            }
        }).catch(() => setTasks([]))
    }

    const selectedTask = useMemo(() => tasks.find((item) => item.id === selectedTaskId) || null, [tasks, selectedTaskId])
    const projectMeta = projectInfo?.project_info || projectInfo || {}
    const projectTitle = projectMeta?.project_name || projectMeta?.title || '\u672a\u52a0\u8f7d\u9879\u76ee'

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
                            setSelectedTaskId(task.id)
                            setPage('tasks')
                            setRefreshToken((value) => value + 1)
                        }}
                        onProjectBootstrapped={() => {
                            setPage('control')
                            setRefreshToken((value) => value + 1)
                        }}
                    />
                )}
                {page === 'tasks' && (
                    <TaskCenterPage tasks={tasks} selectedTask={selectedTask} onSelectTask={setSelectedTaskId} onMutated={() => setRefreshToken((value) => value + 1)} />
                )}
                {page === 'data' && <DataPage />}
                {page === 'files' && <FilesPage />}
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
    if (llmStatus?.connection_status === 'failed') return 'danger'
    if (llmStatus?.connection_status === 'connected') return 'good'
    return 'warning'
}

function formatWritingModelPill(llmStatus) {
    if (!llmStatus?.installed) return '\u672a\u914d\u7f6e\u53ef\u7528\u7684\u5199\u4f5c\u6a21\u578b'
    if (llmStatus?.connection_status === 'failed') return `\u5199\u4f5c\u6a21\u578b\u8fde\u63a5\u5931\u8d25 ${formatWritingModelValue(llmStatus)}`
    if (llmStatus?.connection_status === 'connected') return `\u5199\u4f5c\u6a21\u578b\u5df2\u8054\u901a ${formatWritingModelValue(llmStatus)}`
    return `\u5199\u4f5c\u6a21\u578b\u5df2\u914d\u7f6e ${formatWritingModelValue(llmStatus)}`
}

function formatWritingModelValue(llmStatus) {
    if (!llmStatus) return '\u672a\u914d\u7f6e'
    if (llmStatus.mode === 'cli') {
        return llmStatus.version ? `Codex CLI (${llmStatus.version})` : 'Codex CLI'
    }
    if (llmStatus.mode === 'api') {
        const model = llmStatus.model || '\u672a\u6307\u5b9a\u6a21\u578b'
        return `API / ${model}`
    }
    if (llmStatus.mode === 'mock') {
        return 'Mock Runner'
    }
    return llmStatus.provider || '\u672a\u914d\u7f6e'
}

function formatWritingModelDetail(llmStatus) {
    if (!llmStatus?.installed) return '\u672a\u914d\u7f6e'
    const statusSuffix = llmStatus?.connection_status === 'connected'
        ? '\uff08\u5df2\u8054\u901a\uff09'
        : llmStatus?.connection_status === 'failed'
            ? '\uff08\u8fde\u63a5\u5931\u8d25\uff09'
            : '\uff08\u5df2\u914d\u7f6e\uff09'
    if (llmStatus.mode === 'cli') {
        const base = llmStatus.binary ? `Codex CLI (${llmStatus.binary})` : 'Codex CLI'
        return `${base}${statusSuffix}`
    }
    if (llmStatus.mode === 'api') {
        const model = llmStatus.model || '\u672a\u6307\u5b9a\u6a21\u578b'
        return `API / ${model}${statusSuffix}`
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
    if (!ragStatus?.configured) return 'RAG \u672a\u914d\u7f6e'
    if (ragStatus?.connection_status === 'failed') return `RAG \u8fde\u63a5\u5931\u8d25: ${formatRagErrorSummary(ragStatus.connection_error || ragStatus.last_error)}`
    if (ragStatus?.connection_status === 'connected') return `RAG \u5df2\u8054\u901a ${ragStatus?.embed_model || ''}`.trim()
    return `RAG \u5df2\u914d\u7f6e ${ragStatus?.embed_model || ''}`.trim()
}

function formatRagDetail(ragStatus) {
    if (!ragStatus?.configured) return '\u672a\u914d\u7f6e'
    if (ragStatus?.connection_status === 'failed') return '\u8fde\u63a5\u5931\u8d25'
    if (ragStatus?.connection_status === 'connected') return '\u5df2\u8054\u901a'
    return '\u5df2\u914d\u7f6e'
}

function formatRagErrorSummary(error) {
    if (!error) return 'unknown'
    const stage = error?.details?.stage ? `${error.details.stage}` : 'rag'
    const code = error?.code || 'UNKNOWN'
    return `${stage}/${code}`
}

function ControlPage({ projectInfo, llmStatus, ragStatus, onTaskCreated, onProjectBootstrapped }) {
    const projectMeta = projectInfo?.project_info || projectInfo || {}

    return (
        <div className="page-grid">
            <section className="panel hero-panel">
                <div className="panel-title">{'\u9879\u76ee\u6982\u89c8'}</div>
                <div className="metric-grid">
                    <MetricCard label={'\u603b\u5b57\u6570'} value={formatNumber(projectInfo?.progress?.total_words || 0)} />
                    <MetricCard label={'\u5f53\u524d\u7ae0\u8282'} value={`\u7b2c ${projectInfo?.progress?.current_chapter || 0} \u7ae0`} />
                    <MetricCard label={'\u9898\u6750'} value={projectMeta?.genre || '\u672a\u77e5'} />
                    <MetricCard label={'\u5199\u4f5c\u6a21\u578b'} value={formatWritingModelDetail(llmStatus)} />
                    <MetricCard label="RAG" value={formatRagDetail(ragStatus)} />
                </div>
                {(ragStatus?.connection_status === 'failed' || ragStatus?.last_error) && <div className="empty-state">{'RAG \u6700\u8fd1\u9519\u8bef\uff1a'}{formatRagErrorSummary(ragStatus.connection_error || ragStatus.last_error)}</div>}
            </section>
            <section className="panel">
                <div className="panel-title">{'\u9879\u76ee\u521b\u5efa'}</div>
                <div className="empty-state">{'\u7528\u4e8e\u7a7a\u76ee\u5f55\u7684\u672c\u5730\u521d\u59cb\u5316\uff0c\u4e0d\u4f9d\u8d56\u5199\u4f5c\u6a21\u578b\u3002'}</div>
                <div className="launcher-grid">
                    <TaskLauncherSection template={PROJECT_BOOTSTRAP_TEMPLATE} onSuccess={onProjectBootstrapped} MODE_OPTIONS={MODE_OPTIONS} />
                </div>
            </section>
            <section className="panel">
                <div className="panel-title">{'\u4efb\u52a1\u5165\u53e3'}</div>
                <div className="empty-state">{'\u5206\u6790\u3001\u89c4\u5212\u3001\u5199\u4f5c\u3001\u5ba1\u67e5\u90fd\u4f1a\u4f7f\u7528\u5f53\u524d\u5199\u4f5c\u6a21\u578b\uff1b\u53ef\u5728 Codex CLI \u548c API \u4e4b\u95f4\u5207\u6362\u3002'}</div>
                <div className="launcher-grid">
                    {TASK_TEMPLATES.map((template) => (
                        <TaskLauncherSection key={template.key} template={template} onCreated={onTaskCreated} MODE_OPTIONS={MODE_OPTIONS} />
                    ))}
                </div>
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

function TaskCenterPage({ tasks, selectedTask, onSelectTask, onMutated }) {
    return (
        <TaskCenterPageSection
            tasks={tasks}
            selectedTask={selectedTask}
            onSelectTask={onSelectTask}
            onMutated={onMutated}
            MetricCard={MetricCard}
            translateTaskType={translateTaskType}
            translateTaskStatus={translateTaskStatus}
            translateApprovalStatus={translateApprovalStatus}
            translateStepName={translateStepName}
            translateEventLevel={translateEventLevel}
            translateEventMessage={translateEventMessage}
        />
    )
}

function DataPage() {
    return <DataPageSection SimpleTable={SimpleTable} />
}

function FilesPage() {
    return <FilesPageSection />
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

function translateApprovalStatus(value) {
    if (value === 'n/a') return '\u4e0d\u9002\u7528'
    return APPROVAL_STATUS_LABELS[value] || value || '-'
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

    return message
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
    return String(translateKnownValue(value))
}

function formatNumber(value) {
    return Number(value || 0).toLocaleString('zh-CN')
}
