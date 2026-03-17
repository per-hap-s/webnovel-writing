import { useEffect, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'

const LLM_PROVIDER_OPTIONS = [
    { value: 'openai-compatible', label: 'OpenAI Compatible' },
    { value: 'openai', label: 'OpenAI Official' },
    { value: 'azure-openai', label: 'Azure OpenAI' },
]

const DEFAULT_LAUNCHER_FORM = {
    project_root: '',
    title: '',
    genre: '玄幻',
    chapter: 1,
    chapter_range: '1-3',
    volume: '1',
    mode: 'standard',
    require_manual_approval: true,
}

export function TaskLauncherSection({ template, onCreated, onSuccess, MODE_OPTIONS }) {
    const [form, setForm] = useState(DEFAULT_LAUNCHER_FORM)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState(null)

    async function submit() {
        setSubmitting(true)
        setError(null)
        try {
            const payload = {}
            template.fields.forEach((field) => {
                payload[field] = form[field]
            })
            const response = await postJSON(template.endpoint || `/api/tasks/${template.key}`, payload)
            if (onSuccess) {
                onSuccess(response)
            } else if (onCreated) {
                onCreated(response)
            }
        } catch (err) {
            setError(normalizeError(err))
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <div className="launcher-card">
            <div className="launcher-title">{template.title}</div>
            <div className="field-stack">
                {template.fields.includes('project_root') && (
                    <Field label="项目根目录">
                        <input value={form.project_root} onChange={(event) => setForm({ ...form, project_root: event.target.value })} placeholder="留空则使用当前项目" />
                    </Field>
                )}
                {template.fields.includes('title') && (
                    <Field label="小说标题">
                        <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="留空则使用目录名" />
                    </Field>
                )}
                {template.fields.includes('genre') && (
                    <Field label="题材">
                        <input value={form.genre} onChange={(event) => setForm({ ...form, genre: event.target.value })} placeholder="玄幻" />
                    </Field>
                )}
                {template.fields.includes('chapter') && (
                    <Field label="章节编号">
                        <input type="number" value={form.chapter} onChange={(event) => setForm({ ...form, chapter: Number(event.target.value) })} />
                    </Field>
                )}
                {template.fields.includes('chapter_range') && (
                    <Field label="章节范围">
                        <input value={form.chapter_range} onChange={(event) => setForm({ ...form, chapter_range: event.target.value })} />
                    </Field>
                )}
                {template.fields.includes('volume') && (
                    <Field label="卷">
                        <input value={form.volume} onChange={(event) => setForm({ ...form, volume: event.target.value })} />
                    </Field>
                )}
                {template.fields.includes('mode') && (
                    <Field label="模式">
                        <select value={form.mode} onChange={(event) => setForm({ ...form, mode: event.target.value })}>
                            {MODE_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                        </select>
                    </Field>
                )}
                {template.fields.includes('require_manual_approval') && (
                    <label className="checkbox-row">
                        <input
                            type="checkbox"
                            checked={form.require_manual_approval}
                            onChange={(event) => setForm({ ...form, require_manual_approval: event.target.checked })}
                        />
                        回写前需要人工确认
                    </label>
                )}
            </div>
            <ErrorNotice error={error} />
            <button className="primary-button" onClick={submit} disabled={submitting}>{submitting ? '提交中...' : (template.submitLabel || '创建任务')}</button>
        </div>
    )
}

export function ProjectBootstrapSection({
    currentProjectRoot,
    currentTitle,
    currentGenre,
    projectInitialized,
    onSuccess,
}) {
    const [form, setForm] = useState(() => buildBootstrapForm(currentProjectRoot, currentTitle, currentGenre))
    const [prefillKey, setPrefillKey] = useState('')
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState(null)

    const nextPrefillKey = `${currentProjectRoot || ''}|${currentTitle || ''}|${currentGenre || ''}|${projectInitialized ? '1' : '0'}`

    useEffect(() => {
        if (nextPrefillKey === prefillKey) return
        setForm(buildBootstrapForm(currentProjectRoot, currentTitle, currentGenre))
        setPrefillKey(nextPrefillKey)
        setError(null)
    }, [currentProjectRoot, currentTitle, currentGenre, projectInitialized, nextPrefillKey, prefillKey])

    const normalizedCurrentRoot = normalizePath(currentProjectRoot)
    const normalizedTargetRoot = normalizePath(form.project_root || currentProjectRoot)
    const targetingCurrentProject = Boolean(projectInitialized && normalizedCurrentRoot && normalizedTargetRoot === normalizedCurrentRoot)

    async function submit() {
        if (targetingCurrentProject) return
        setSubmitting(true)
        setError(null)
        try {
            const response = await postJSON('/api/project/bootstrap', {
                project_root: form.project_root,
                title: form.title,
                genre: form.genre,
            })
            if (onSuccess) onSuccess(response)
        } catch (err) {
            setError(normalizeError(err))
        } finally {
            setSubmitting(false)
        }
    }

    return (
        <div className="launcher-card">
            <div className="launcher-title">创建项目</div>
            {projectInitialized ? (
                <div className="tiny">
                    当前已经打开一个已初始化项目。这里已按当前项目预填；如果要新建，请先把“项目根目录”改成新的空目录。
                </div>
            ) : (
                <div className="tiny">
                    当前目录还未初始化，可以直接在这里创建项目。
                </div>
            )}
            <div className="field-stack">
                <Field label="项目根目录">
                    <input value={form.project_root} onChange={(event) => setForm({ ...form, project_root: event.target.value })} placeholder="请输入新的项目目录" />
                </Field>
                <Field label="小说标题">
                    <input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} placeholder="留空则使用目录名" />
                </Field>
                <Field label="题材">
                    <input value={form.genre} onChange={(event) => setForm({ ...form, genre: event.target.value })} placeholder="玄幻" />
                </Field>
            </div>
            {targetingCurrentProject ? (
                <div className="planning-warning subtle">
                    <div className="tiny">当前项目已初始化，不能对当前目录重复创建。请先修改“项目根目录”为新的空目录。</div>
                </div>
            ) : null}
            <ErrorNotice error={error} />
            <button className="primary-button" onClick={submit} disabled={submitting || targetingCurrentProject}>
                {submitting ? '创建中...' : '创建项目'}
            </button>
        </div>
    )
}

export function PlanningProfileSection({ onSaved }) {
    const [form, setForm] = useState({})
    const [fieldSpecs, setFieldSpecs] = useState([])
    const [readiness, setReadiness] = useState(null)
    const [lastBlocked, setLastBlocked] = useState(null)
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState(false)
    const [error, setError] = useState(null)
    const [message, setMessage] = useState('')

    useEffect(() => {
        let active = true
        async function loadProfile() {
            setLoading(true)
            try {
                const response = await fetchJSON('/api/project/planning-profile')
                if (!active) return
                setForm(response.profile || {})
                setFieldSpecs(response.field_specs || [])
                setReadiness(response.readiness || null)
                setLastBlocked(response.last_blocked || null)
                setError(null)
            } catch (err) {
                if (!active) return
                setError(normalizeError(err))
            } finally {
                if (active) setLoading(false)
            }
        }
        loadProfile()
        return () => {
            active = false
        }
    }, [])

    async function saveProfile() {
        setSaving(true)
        setError(null)
        setMessage('')
        try {
            const response = await postJSON('/api/project/planning-profile', form)
            setForm(response.profile || {})
            setFieldSpecs(response.field_specs || [])
            setReadiness(response.readiness || null)
            setLastBlocked(response.last_blocked || null)
            setMessage('规划必填信息已保存，总纲与 readiness 已同步更新。')
            if (onSaved) onSaved(response)
        } catch (err) {
            setError(normalizeError(err))
        } finally {
            setSaving(false)
        }
    }

    const missingItems = readiness?.missing_items || []

    return (
        <div className="planning-profile">
            <div className="planning-status-row">
                <div className={`planning-pill ${readiness?.ok ? 'ready' : 'blocked'}`}>
                    {readiness?.ok ? '已满足 plan 条件' : '待补信息'}
                </div>
                <div className="tiny">
                    {readiness ? `已填写 ${readiness.completed_fields || 0}/${readiness.total_required_fields || 0}` : '正在读取 readiness...'}
                </div>
            </div>
            {missingItems.length > 0 ? (
                <div className="planning-warning">
                    <div className="subsection-title">缺失项清单</div>
                    <div className="planning-tags">
                        {missingItems.map((item) => (
                            <span key={item.field || item.label} className="planning-tag">{item.label}</span>
                        ))}
                    </div>
                </div>
            ) : null}
            {lastBlocked?.blocking_items?.length ? (
                <div className="planning-warning subtle">
                    <div className="subsection-title">最近一次 plan 阻断</div>
                    <div className="tiny">{lastBlocked.reason || '信息不足'}</div>
                    <div className="planning-tags">
                        {lastBlocked.blocking_items.map((item, index) => (
                            <span key={`${item.field || item.label}-${index}`} className="planning-tag">{item.label}</span>
                        ))}
                    </div>
                </div>
            ) : null}
            <div className="planning-grid">
                {fieldSpecs.map((field) => {
                    const value = form[field.name] || ''
                    return (
                        <Field key={field.name} label={field.label}>
                            {field.multiline ? (
                                <textarea
                                    rows={field.name === 'rules_outline' ? 4 : 3}
                                    value={value}
                                    onChange={(event) => setForm({ ...form, [field.name]: event.target.value })}
                                    placeholder={field.format_hint || '请输入内容'}
                                />
                            ) : (
                                <input
                                    value={value}
                                    onChange={(event) => setForm({ ...form, [field.name]: event.target.value })}
                                    placeholder={field.format_hint || '请输入内容'}
                                />
                            )}
                            {field.format_hint ? <div className="tiny">{field.format_hint}</div> : null}
                        </Field>
                    )
                })}
            </div>
            <ErrorNotice error={error} />
            {message ? <div className="success-text">{message}</div> : null}
            <button className="primary-button" onClick={saveProfile} disabled={loading || saving}>
                {saving ? '保存中...' : '保存规划信息'}
            </button>
        </div>
    )
}


export function ApiSettingsSection({ llmStatus, ragStatus, onSaved }) {
    const [llmForm, setLlmForm] = useState({ provider: 'openai-compatible', base_url: '', model: '', api_key: '' })
    const [ragForm, setRagForm] = useState({ base_url: '', embed_model: '', rerank_model: '', api_key: '' })
    const [savedLlm, setSavedLlm] = useState({ provider: 'openai-compatible', base_url: '', model: '', has_api_key: false })
    const [savedRag, setSavedRag] = useState({ base_url: '', embed_model: '', rerank_model: '', has_api_key: false })
    const [meta, setMeta] = useState({
        llmHasKey: false,
        llmMasked: '',
        ragHasKey: false,
        ragMasked: '',
    })
    const [loading, setLoading] = useState(true)
    const [saving, setSaving] = useState({ llm: false, rag: false })
    const [message, setMessage] = useState({ llm: '', rag: '' })
    const [error, setError] = useState({ llm: null, rag: null })

    function normalizeLLM(source, hasApiKey = false) {
        return {
            provider: (source.provider || 'openai-compatible').trim() || 'openai-compatible',
            base_url: (source.base_url || '').trim(),
            model: (source.model || '').trim(),
            has_api_key: Boolean(hasApiKey),
        }
    }

    function normalizeRAG(source, hasApiKey = false) {
        return {
            base_url: (source.base_url || '').trim(),
            embed_model: (source.embed_model || '').trim(),
            rerank_model: (source.rerank_model || '').trim(),
            has_api_key: Boolean(hasApiKey),
        }
    }

    useEffect(() => {
        let active = true
        async function loadSettings() {
            setLoading(true)
            try {
                const [llm, rag] = await Promise.all([
                    fetchJSON('/api/settings/llm'),
                    fetchJSON('/api/settings/rag'),
                ])
                if (!active) return

                const nextLlm = normalizeLLM(llm, llm.has_api_key)
                const nextRag = normalizeRAG(rag, rag.has_api_key)

                setLlmForm({
                    provider: nextLlm.provider,
                    base_url: nextLlm.base_url,
                    model: nextLlm.model,
                    api_key: '',
                })
                setRagForm({
                    base_url: nextRag.base_url,
                    embed_model: nextRag.embed_model,
                    rerank_model: nextRag.rerank_model,
                    api_key: '',
                })
                setSavedLlm(nextLlm)
                setSavedRag(nextRag)
                setMeta({
                    llmHasKey: Boolean(llm.has_api_key),
                    llmMasked: llm.api_key_masked || '',
                    ragHasKey: Boolean(rag.has_api_key),
                    ragMasked: rag.api_key_masked || '',
                })
            } catch (err) {
                if (!active) return
                const normalized = normalizeError(err)
                setError({ llm: normalized, rag: normalized })
            } finally {
                if (active) setLoading(false)
            }
        }
        loadSettings()
        return () => {
            active = false
        }
    }, [])

    const llmDirty =
        llmForm.provider.trim() !== savedLlm.provider ||
        llmForm.base_url.trim() !== savedLlm.base_url ||
        llmForm.model.trim() !== savedLlm.model ||
        Boolean(llmForm.api_key.trim())

    const ragDirty =
        ragForm.base_url.trim() !== savedRag.base_url ||
        ragForm.embed_model.trim() !== savedRag.embed_model ||
        ragForm.rerank_model.trim() !== savedRag.rerank_model ||
        Boolean(ragForm.api_key.trim())

    const llmProviderOptions = LLM_PROVIDER_OPTIONS.some((option) => option.value === llmForm.provider)
        ? LLM_PROVIDER_OPTIONS
        : [{ value: llmForm.provider, label: `\u81ea\u5b9a\u4e49\uff1a${llmForm.provider}` }, ...LLM_PROVIDER_OPTIONS]

    async function saveSection(kind) {
        if ((kind === 'llm' && !llmDirty) || (kind === 'rag' && !ragDirty)) {
            return
        }

        setSaving((current) => ({ ...current, [kind]: true }))
        setError((current) => ({ ...current, [kind]: null }))
        setMessage((current) => ({ ...current, [kind]: '' }))
        try {
            if (kind === 'llm') {
                const response = await postJSON('/api/settings/llm', llmForm)
                const nextSettings = normalizeLLM(response.settings || llmForm, response.settings?.has_api_key)
                setLlmForm({
                    provider: nextSettings.provider,
                    base_url: nextSettings.base_url,
                    model: nextSettings.model,
                    api_key: '',
                })
                setSavedLlm(nextSettings)
                setMeta((current) => ({
                    ...current,
                    llmHasKey: Boolean(response.settings?.has_api_key),
                    llmMasked: response.settings?.api_key_masked || current.llmMasked,
                }))
                setMessage((current) => ({ ...current, llm: '\u5199\u4f5c\u6a21\u578b API \u8bbe\u7f6e\u5df2\u4fdd\u5b58' }))
            } else {
                const response = await postJSON('/api/settings/rag', ragForm)
                const nextSettings = normalizeRAG(response.settings || ragForm, response.settings?.has_api_key)
                setRagForm({
                    base_url: nextSettings.base_url,
                    embed_model: nextSettings.embed_model,
                    rerank_model: nextSettings.rerank_model,
                    api_key: '',
                })
                setSavedRag(nextSettings)
                setMeta((current) => ({
                    ...current,
                    ragHasKey: Boolean(response.settings?.has_api_key),
                    ragMasked: response.settings?.api_key_masked || current.ragMasked,
                }))
                setMessage((current) => ({ ...current, rag: 'RAG API \u8bbe\u7f6e\u5df2\u4fdd\u5b58' }))
            }
            if (onSaved) onSaved()
        } catch (err) {
            setError((current) => ({ ...current, [kind]: normalizeError(err) }))
        } finally {
            setSaving((current) => ({ ...current, [kind]: false }))
        }
    }

    return (
        <div className="settings-grid">
            <div className="launcher-card settings-card">
                <div className="launcher-title">{'\u5199\u4f5c\u6a21\u578b API'}</div>
                <div className="muted">{'\u7528\u4e8e\u89c4\u5212\u3001\u5199\u4f5c\u3001\u5ba1\u67e5\u7b49\u5de5\u4f5c\u6d41\u8c03\u7528\u7684\u5927\u6a21\u578b\u63a5\u53e3\u3002'}</div>
                <div className="tiny">{'\u5f53\u524d\u72b6\u6001\uff1a'}{translateConnection(llmStatus)}</div>
                {loading ? <div className="tiny">{'\u6b63\u5728\u8bfb\u53d6\u5f53\u524d\u914d\u7f6e...'}</div> : null}
                <div className="field-stack">
                    <Field label="Provider">
                        <select value={llmForm.provider} onChange={(event) => setLlmForm({ ...llmForm, provider: event.target.value })}>
                            {llmProviderOptions.map((option) => (
                                <option key={option.value} value={option.value}>{option.label}</option>
                            ))}
                        </select>
                    </Field>
                    <Field label="Base URL">
                        <input value={llmForm.base_url} onChange={(event) => setLlmForm({ ...llmForm, base_url: event.target.value })} placeholder="https://api.openai.com/v1" />
                    </Field>
                    <Field label={'\u6a21\u578b\u540d\u79f0'}>
                        <input value={llmForm.model} onChange={(event) => setLlmForm({ ...llmForm, model: event.target.value })} placeholder={'\u4f8b\u5982\uff1agpt-4.1-mini'} />
                    </Field>
                    <Field label="API Key">
                        <input type="password" value={llmForm.api_key} onChange={(event) => setLlmForm({ ...llmForm, api_key: event.target.value })} placeholder={meta.llmHasKey ? `\u7559\u7a7a\u5219\u4fdd\u7559\u5f53\u524d Key\uff08${meta.llmMasked}\uff09` : '\u8f93\u5165\u65b0\u7684 API Key'} />
                    </Field>
                </div>
                <div className="tiny">{'\u4fdd\u5b58\u4f4d\u7f6e\uff1a\u9879\u76ee\u6839\u76ee\u5f55 `.env`\u3002\u7559\u7a7a\u4e0d\u8986\u76d6\u5df2\u6709 Key\u3002'}</div>
                <ErrorNotice error={error.llm} />
                {message.llm ? <div className="success-text">{message.llm}</div> : null}
                <button className="primary-button" onClick={() => saveSection('llm')} disabled={saving.llm || loading || !llmDirty}>
                    {saving.llm ? '\u4fdd\u5b58\u4e2d...' : '\u4fdd\u5b58\u5199\u4f5c\u6a21\u578b API'}
                </button>
            </div>

            <div className="launcher-card settings-card">
                <div className="launcher-title">RAG API</div>
                <div className="muted">{'\u7528\u4e8e Embedding\u3001Rerank \u548c\u68c0\u7d22\u94fe\u8def\u7684\u63a5\u53e3\u914d\u7f6e\u3002'}</div>
                <div className="tiny">{'\u5f53\u524d\u72b6\u6001\uff1a'}{translateConnection(ragStatus)}</div>
                {loading ? <div className="tiny">{'\u6b63\u5728\u8bfb\u53d6\u5f53\u524d\u914d\u7f6e...'}</div> : null}
                <div className="field-stack">
                    <Field label="Base URL">
                        <input value={ragForm.base_url} onChange={(event) => setRagForm({ ...ragForm, base_url: event.target.value })} placeholder="https://api.siliconflow.cn/v1" />
                    </Field>
                    <Field label={'Embedding \u6a21\u578b'}>
                        <input value={ragForm.embed_model} onChange={(event) => setRagForm({ ...ragForm, embed_model: event.target.value })} placeholder={'\u4f8b\u5982\uff1aBAAI/bge-m3'} />
                    </Field>
                    <Field label={'Rerank \u6a21\u578b'}>
                        <input value={ragForm.rerank_model} onChange={(event) => setRagForm({ ...ragForm, rerank_model: event.target.value })} placeholder={'\u4f8b\u5982\uff1aBAAI/bge-reranker-v2-m3'} />
                    </Field>
                    <Field label="API Key">
                        <input type="password" value={ragForm.api_key} onChange={(event) => setRagForm({ ...ragForm, api_key: event.target.value })} placeholder={meta.ragHasKey ? `\u7559\u7a7a\u5219\u4fdd\u7559\u5f53\u524d Key\uff08${meta.ragMasked}\uff09` : '\u8f93\u5165\u65b0\u7684 API Key'} />
                    </Field>
                </div>
                <div className="tiny">{'\u4fdd\u5b58\u4f4d\u7f6e\uff1a\u9879\u76ee\u6839\u76ee\u5f55 `.env`\u3002\u5f53\u524d\u5b9e\u73b0\u9ed8\u8ba4 Embedding \u548c Rerank \u5171\u7528\u540c\u4e00\u7ec4 RAG Key\u3002'}</div>
                <ErrorNotice error={error.rag} />
                {message.rag ? <div className="success-text">{message.rag}</div> : null}
                <button className="primary-button" onClick={() => saveSection('rag')} disabled={saving.rag || loading || !ragDirty}>
                    {saving.rag ? '\u4fdd\u5b58\u4e2d...' : '\u4fdd\u5b58 RAG API'}
                </button>
            </div>
        </div>
    )
}

function translateConnection(status) {
    if (!status) return '\u672a\u68c0\u6d4b'
    const effectiveStatus = status.effective_status || status.connection_status
    if (effectiveStatus === 'connected') return '\u5df2\u8fde\u63a5'
    if (effectiveStatus === 'degraded') return '\u63a2\u6d3b\u5f02\u5e38\uff0c\u6700\u8fd1\u6267\u884c\u6210\u529f'
    if (effectiveStatus === 'failed') return '\u8fde\u63a5\u5931\u8d25'
    if (effectiveStatus === 'not_configured') return '\u672a\u914d\u7f6e'
    return effectiveStatus || '\u672a\u68c0\u6d4b'
}


export function TaskCenterPageSection({
    tasks,
    selectedTask,
    onSelectTask,
    onMutated,
    onNavigateOverview,
    MetricCard,
    translateTaskType,
    translateTaskStatus,
    translateApprovalStatus,
    translateStepName,
    translateEventLevel,
    translateEventMessage,
    resolveTaskStatusLabel,
    resolveCurrentStepLabel,
}) {
    const [events, setEvents] = useState([])
    const [actionError, setActionError] = useState(null)
    const [runtimeNow, setRuntimeNow] = useState(() => Date.now())

    useEffect(() => {
        if (!tasks.some(isRuntimeActiveTask)) return undefined
        setRuntimeNow(Date.now())
        const timer = window.setInterval(() => setRuntimeNow(Date.now()), 1000)
        return () => window.clearInterval(timer)
    }, [tasks])

    useEffect(() => {
        if (!selectedTask?.id) return
        fetchJSON(`/api/tasks/${selectedTask.id}/events`).then(setEvents).catch(() => setEvents([]))
    }, [selectedTask?.id, selectedTask?.updated_at])

    async function perform(path, body) {
        setActionError(null)
        try {
            await postJSON(path, body)
            onMutated()
        } catch (err) {
            setActionError(normalizeError(err))
        }
    }

    return (
        <div className="split-layout">
            <section className="panel list-panel">
                <div className="panel-title">任务监控</div>
                <div className="task-list">
                    {tasks.map((task) => {
                        const liveTask = withLiveRuntimeStatus(task, runtimeNow)
                        return (
                        <button key={task.id} className={`task-item ${selectedTask?.id === task.id ? 'active' : ''}`} onClick={() => onSelectTask(task.id)}>
                            <div className="task-item-header">
                                <div>{translateTaskType(liveTask.task_type)}</div>
                                <span className={`runtime-badge ${resolveRuntimeBadgeTone(liveTask)}`}>{resolveRuntimeBadgeLabel(liveTask)}</span>
                            </div>
                            <div className="muted">{resolveTaskStatusLabel ? resolveTaskStatusLabel(liveTask) : translateTaskStatus(liveTask.status)}</div>
                            <div className="tiny">{resolveCurrentStepLabel ? resolveCurrentStepLabel(liveTask) : translateStepName(liveTask.current_step || 'idle')}</div>
                            <div className="tiny runtime-summary">{buildRuntimeSummary(liveTask)}</div>
                        </button>
                    )})}
                    {tasks.length === 0 && <div className="empty-state">暂无任务</div>}
                </div>
            </section>
            <section className="panel detail-panel">
                <div className="panel-title">任务详情</div>
                {!selectedTask && <div className="empty-state">请选择任务查看详情</div>}
                {selectedTask && (() => {
                    const liveSelectedTask = withLiveRuntimeStatus(selectedTask, runtimeNow)
                    return (
                    <>
                        <div className="detail-grid">
                            <MetricCard label="状态" value={resolveTaskStatusLabel ? resolveTaskStatusLabel(liveSelectedTask) : translateTaskStatus(liveSelectedTask.status)} />
                            <MetricCard label="当前步骤" value={resolveCurrentStepLabel ? resolveCurrentStepLabel(liveSelectedTask) : translateStepName(liveSelectedTask.current_step || 'idle')} />
                            <MetricCard label="审批" value={translateApprovalStatus(liveSelectedTask.approval_status || 'n/a')} />
                            <MetricCard label="类型" value={translateTaskType(liveSelectedTask.task_type)} />
                        </div>
                        {liveSelectedTask?.artifacts?.plan_blocked ? (
                            <div className="planning-warning">
                                <div className="subsection-title">待补信息</div>
                                <div className="tiny">规划任务未失败，但当前输入不足，需先补录后再重新运行 plan。</div>
                                <div className="planning-tags">
                                    {(liveSelectedTask.artifacts.blocking_items || []).map((item, index) => (
                                        <span key={`${item.field || item.label}-${index}`} className="planning-tag">{item.label || item.field || '未命名缺失项'}</span>
                                    ))}
                                </div>
                                {onNavigateOverview ? <button className="secondary-button" onClick={onNavigateOverview}>前往总览补录</button> : null}
                            </div>
                        ) : null}
                        <div className="subsection">
                            <div className="subsection-title">实时运行状态</div>
                            <div className="detail-grid">
                                <MetricCard label="当前阶段" value={liveSelectedTask.runtime_status?.phase_label || (resolveCurrentStepLabel ? resolveCurrentStepLabel(liveSelectedTask) : translateStepName(liveSelectedTask.current_step || 'idle'))} />
                                <MetricCard label="阶段说明" value={liveSelectedTask.runtime_status?.phase_detail || '暂无'} />
                                <MetricCard label="运行状态" value={resolveRuntimeBadgeLabel(liveSelectedTask)} />
                                <MetricCard label="已运行时长" value={formatRuntimeDuration(liveSelectedTask.runtime_status?.running_seconds)} />
                                <MetricCard label="已等待时长" value={formatRuntimeDuration(liveSelectedTask.runtime_status?.waiting_seconds)} />
                                <MetricCard label="当前尝试" value={formatCountValue(liveSelectedTask.runtime_status?.attempt)} />
                                <MetricCard label="重试次数" value={formatCountValue(liveSelectedTask.runtime_status?.retry_count, true)} />
                                <MetricCard label="超时预算" value={formatTimeoutValue(liveSelectedTask.runtime_status?.timeout_seconds)} />
                                <MetricCard label="最近事件" value={liveSelectedTask.runtime_status?.last_event_label || '暂无'} />
                                <MetricCard label="最近更新时间" value={formatTimestampShort(liveSelectedTask.runtime_status?.last_event_at || liveSelectedTask.updated_at || '-')} />
                                <MetricCard label="最近活动" value={formatTimestampShort(liveSelectedTask.runtime_status?.last_activity_at || '-')} />
                                <MetricCard label="错误码" value={liveSelectedTask.runtime_status?.error_code || '-'} />
                                <MetricCard label="HTTP 状态" value={liveSelectedTask.runtime_status?.http_status || '-'} />
                                <MetricCard label="是否可重试" value={formatRetryableValue(liveSelectedTask.runtime_status?.retryable)} />
                            </div>
                        </div>
                        <div className="button-row">
                            <button className="secondary-button" onClick={() => perform(`/api/tasks/${liveSelectedTask.id}/retry`, {})}>重试</button>
                            {liveSelectedTask.status === 'awaiting_writeback_approval' && (
                                <>
                                    <button className="primary-button" onClick={() => perform('/api/review/approve', { task_id: liveSelectedTask.id, reason: '由仪表盘批准回写' })}>批准回写</button>
                                    <button className="danger-button" onClick={() => perform('/api/review/reject', { task_id: liveSelectedTask.id, reason: '由仪表盘拒绝回写' })}>拒绝回写</button>
                                </>
                            )}
                        </div>
                        <ErrorNotice error={actionError} />
                        <ErrorNotice error={liveSelectedTask.error || null} title="任务失败原因" />
                        <div className="subsection">
                            <div className="subsection-title">步骤输出</div>
                            <pre className="code-block">{JSON.stringify(liveSelectedTask.artifacts?.step_results || {}, null, 2)}</pre>
                        </div>
                        <div className="subsection">
                            <div className="subsection-title">事件流</div>
                            <div className="event-list">
                                {events.map((event) => (
                                    <div key={event.id} className={`event-card ${event.level}`}>
                                        <div className="event-meta">[{translateEventLevel(event.level)}] {translateStepName(event.step_name || 'task')} · {formatTimestampShort(event.timestamp)}</div>
                                        <div>{translateEventMessage(event.message)}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </>
                )})()}
            </section>
        </div>
    )
}

export function DataPageSection({ SimpleTable, refreshToken }) {
    const [entities, setEntities] = useState([])
    const [relationships, setRelationships] = useState([])
    const [chapters, setChapters] = useState([])

    useEffect(() => {
        fetchJSON('/api/entities').then(setEntities).catch(() => setEntities([]))
        fetchJSON('/api/relationships', { limit: 80 }).then(setRelationships).catch(() => setRelationships([]))
        fetchJSON('/api/chapters').then(setChapters).catch(() => setChapters([]))
    }, [refreshToken])

    return (
        <div className="page-grid">
            <section className="panel">
                <div className="panel-title">实体</div>
                {chapters.length > 0 && entities.length === 0 ? <div className="tiny">当前已有章节，但暂未看到结构化实体；如本章未抽取到结果，会在对应任务事件流里显示 warning。</div> : null}
                <SimpleTable rows={entities} columns={['name', 'type', 'tier', 'last_appearance']} />
            </section>
            <section className="panel">
                <div className="panel-title">关系</div>
                {chapters.length > 0 && relationships.length === 0 ? <div className="tiny">当前已有章节，但暂未看到结构化关系；请同时检查对应写作任务的 `data-sync` 事件。</div> : null}
                <SimpleTable rows={relationships} columns={['from_entity', 'to_entity', 'type', 'chapter']} />
            </section>
            <section className="panel full-span">
                <div className="panel-title">章节</div>
                <SimpleTable rows={chapters} columns={['chapter', 'title', 'word_count']} />
            </section>
        </div>
    )
}

export function FilesPageSection({ refreshToken }) {
    const [tree, setTree] = useState({})
    const [selectedPath, setSelectedPath] = useState('')
    const [fileDetail, setFileDetail] = useState({ path: '', content: '', exists: false, is_binary: false, encoding: 'utf-8' })
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)

    useEffect(() => {
        fetchJSON('/api/files/tree').then((result) => {
            setTree(result)
            setError(null)
        }).catch((err) => {
            setTree({})
            setError(normalizeError(err))
        })
    }, [refreshToken])

    useEffect(() => {
        if (!selectedPath) {
            setFileDetail({ path: '', content: '', exists: false, is_binary: false, encoding: 'utf-8' })
            return
        }
        setLoading(true)
        fetchJSON('/api/files/read', { path: selectedPath }).then((result) => {
            setFileDetail({
                path: result.path || selectedPath,
                content: typeof result.content === 'string' ? result.content : '',
                exists: Boolean(result.exists),
                is_binary: Boolean(result.is_binary),
                encoding: result.encoding || 'utf-8',
            })
            setError(null)
        }).catch((err) => {
            setFileDetail({ path: selectedPath, content: '', exists: false, is_binary: false, encoding: 'utf-8' })
            setError(normalizeError(err))
        }).finally(() => setLoading(false))
    }, [selectedPath, refreshToken])

    const previewText = !selectedPath
        ? '请选择左侧文件'
        : loading
            ? '读取中...'
            : fileDetail.is_binary
                ? `该文件为二进制或非 UTF-8 文本，当前编码：${fileDetail.encoding}`
                : fileDetail.exists
                    ? (fileDetail.content === '' ? '无内容' : fileDetail.content)
                    : '读取失败'

    return (
        <div className="split-layout">
            <section className="panel list-panel">
                <div className="panel-title">文档树</div>
                <FileTree tree={tree} onSelect={setSelectedPath} />
            </section>
            <section className="panel detail-panel">
                <div className="panel-title">{selectedPath || '选择文件'}</div>
                <ErrorNotice error={error} />
                <pre className="code-block large">{previewText}</pre>
            </section>
        </div>
    )
}

export function QualityPageSection({ refreshToken, onMutated, SimpleTable, translateColumnLabel, formatCell }) {
    const [invalidFacts, setInvalidFacts] = useState([])
    const [reviewMetrics, setReviewMetrics] = useState([])
    const [ragQueries, setRagQueries] = useState([])
    const [toolStats, setToolStats] = useState([])
    const [checklistScores, setChecklistScores] = useState([])
    const [actionError, setActionError] = useState(null)

    useEffect(() => {
        fetchJSON('/api/invalid-facts', { limit: 50 }).then(setInvalidFacts).catch(() => setInvalidFacts([]))
        fetchJSON('/api/review-metrics', { limit: 20 }).then(setReviewMetrics).catch(() => setReviewMetrics([]))
        fetchJSON('/api/rag-queries', { limit: 40 }).then(setRagQueries).catch(() => setRagQueries([]))
        fetchJSON('/api/tool-stats', { limit: 40 }).then(setToolStats).catch(() => setToolStats([]))
        fetchJSON('/api/checklist-scores', { limit: 40 }).then(setChecklistScores).catch(() => setChecklistScores([]))
    }, [refreshToken])

    async function resolveInvalid(id, action) {
        setActionError(null)
        try {
            await postJSON('/api/review/confirm-invalid-facts', { ids: [id], action })
            onMutated()
        } catch (err) {
            setActionError(normalizeError(err))
        }
    }

    return (
        <div className="page-grid">
            <section className="panel full-span">
                <div className="panel-title">失效事实审批</div>
                <ErrorNotice error={actionError} />
                <div className="approval-list">
                    {invalidFacts.map((item) => (
                        <div key={item.id} className="approval-card">
                            <div>
                                <strong>{translateColumnLabel('source_type')}：{formatCell(item.source_type)} / {translateColumnLabel('source_id')}：{item.source_id}</strong>
                                <div className="muted">{item.reason}</div>
                            </div>
                            <div className="button-row">
                                <button className="primary-button" onClick={() => resolveInvalid(item.id, 'confirm')}>确认冻结</button>
                                <button className="secondary-button" onClick={() => resolveInvalid(item.id, 'dismiss')}>忽略</button>
                            </div>
                        </div>
                    ))}
                    {invalidFacts.length === 0 && <div className="empty-state">暂无待处理失效事实</div>}
                </div>
            </section>
            <section className="panel">
                <div className="panel-title">审查指标</div>
                <SimpleTable rows={reviewMetrics} columns={['end_chapter', 'overall_score', 'created_at']} />
            </section>
            <section className="panel">
                <div className="panel-title">清单评分</div>
                <SimpleTable rows={checklistScores} columns={['chapter', 'template', 'score', 'completion_rate']} />
            </section>
            <section className="panel">
                <div className="panel-title">RAG 查询</div>
                <SimpleTable rows={ragQueries} columns={['query_type', 'query', 'results_count', 'latency_ms']} />
            </section>
            <section className="panel">
                <div className="panel-title">工具统计</div>
                <SimpleTable rows={toolStats} columns={['tool_name', 'success', 'retry_count', 'created_at']} />
            </section>
        </div>
    )
}

function resolveRuntimeBadgeLabel(task) {
    if (task?.artifacts?.plan_blocked) return '待补信息'
    const stepState = task?.runtime_status?.step_state
    if (stepState === 'retrying') return '重试中'
    if (stepState === 'waiting_approval') return '待审批'
    if (stepState === 'failed') return '已失败'
    if (stepState === 'completed') return '已完成'
    if (stepState === 'running') return '运行中'
    return '待执行'
}

function resolveRuntimeBadgeTone(task) {
    if (task?.artifacts?.plan_blocked) return 'warning'
    const stepState = task?.runtime_status?.step_state
    if (stepState === 'running') return 'info'
    if (stepState === 'retrying') return 'warning'
    if (stepState === 'waiting_approval') return 'warning'
    if (stepState === 'failed') return 'danger'
    if (stepState === 'completed') return 'success'
    return 'muted'
}

function buildRuntimeSummary(task) {
    if (task?.artifacts?.plan_blocked) return '需先回总览补录规划信息'
    const runtime = task?.runtime_status || {}
    const parts = []
    if (runtime.phase_label) parts.push(runtime.phase_label)
    if (runtime.phase_detail) parts.push(runtime.phase_detail)
    if (runtime.step_state === 'retrying' && runtime.attempt) {
        parts.push(`第 ${runtime.attempt} 次尝试`)
    } else if (runtime.step_state === 'running' && runtime.running_seconds > 0) {
        parts.push(formatRuntimeDuration(runtime.running_seconds))
    } else if (runtime.step_state === 'failed' && runtime.error_code) {
        parts.push(runtime.error_code)
    } else if (runtime.step_state === 'waiting_approval') {
        parts.push('等待人工批准回写')
    } else if (runtime.step_state === 'completed' && runtime.running_seconds > 0) {
        parts.push(`耗时 ${formatRuntimeDuration(runtime.running_seconds)}`)
    }
    if (!parts.length) return '暂无实时状态'
    return parts.join(' · ')
}

function isRuntimeActiveTask(task) {
    const stepState = task?.runtime_status?.step_state
    return stepState === 'running' || stepState === 'retrying'
}

function withLiveRuntimeStatus(task, nowMs) {
    if (!task?.runtime_status || !isRuntimeActiveTask(task)) return task
    const runtime = task.runtime_status
    const referenceMs = parseTimestampToMs(runtime.last_activity_at || runtime.last_event_at || task.updated_at)
    if (!Number.isFinite(referenceMs)) return task
    const elapsedSeconds = Math.max(0, Math.floor((nowMs - referenceMs) / 1000))
    if (elapsedSeconds <= 0) return task
    const runningSeconds = Math.max(0, Number(runtime.running_seconds || 0)) + elapsedSeconds
    const waitingSeconds = shouldTickWaiting(runtime)
        ? Math.max(0, Number(runtime.waiting_seconds || 0)) + elapsedSeconds
        : Math.max(0, Number(runtime.waiting_seconds || 0))
    return {
        ...task,
        runtime_status: {
            ...runtime,
            running_seconds: runningSeconds,
            waiting_seconds: waitingSeconds,
        },
    }
}

function shouldTickWaiting(runtime) {
    return ['llm_request_started', 'request_dispatched', 'awaiting_model_response', 'step_heartbeat'].includes(runtime?.last_event_message)
        || Number(runtime?.waiting_seconds || 0) > 0
}

function parseTimestampToMs(value) {
    if (!value) return Number.NaN
    const parsed = new Date(String(value).includes('T') ? String(value) : String(value).replace(' ', 'T'))
    return parsed.getTime()
}

function formatRuntimeDuration(seconds) {
    const total = Number(seconds || 0)
    if (!Number.isFinite(total) || total <= 0) return '-'
    const hours = Math.floor(total / 3600)
    const minutes = Math.floor((total % 3600) / 60)
    const remainSeconds = total % 60
    if (hours > 0) return `${hours}小时${minutes}分${remainSeconds}秒`
    if (minutes > 0) return `${minutes}分${remainSeconds}秒`
    return `${remainSeconds}秒`
}

function formatTimeoutValue(seconds) {
    const total = Number(seconds || 0)
    if (!Number.isFinite(total) || total <= 0) return '-'
    return `${total} 秒`
}

function formatCountValue(value, allowZero = false) {
    if (value === null || value === undefined || value === '') return '-'
    const count = Number(value)
    if (!Number.isFinite(count)) return String(value)
    if (!allowZero && count <= 0) return '-'
    return String(count)
}

function formatRetryableValue(value) {
    if (value === null || value === undefined) return '-'
    return value ? '是' : '否'
}

function formatTimestampShort(value) {
    if (!value || value === '-') return '-'
    const text = String(value)
    const normalized = text.includes('T') ? text : text.replace(' ', 'T')
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

function buildBootstrapForm(projectRoot, title, genre) {
    return {
        ...DEFAULT_LAUNCHER_FORM,
        project_root: projectRoot || '',
        title: title || '',
        genre: genre || '玄幻',
    }
}

function normalizePath(value) {
    return String(value || '').trim().replace(/[\\/]+$/, '').toLowerCase()
}

function Field({ label, children }) {
    return (
        <label className="field">
            <span>{label}</span>
            {children}
        </label>
    )
}

function ErrorNotice({ error, title = '操作失败' }) {
    if (!error) return null

    const normalized = normalizeError(error)
    const detailText = buildErrorDetailText(normalized)

    return (
        <div className="error-panel" role="alert">
            <div className="error-title">{title}</div>
            <div className="error-text">{normalized.displayMessage}</div>
            <div className="error-meta">错误码：{normalized.code || 'REQUEST_FAILED'}</div>
            {detailText ? (
                <details className="error-details">
                    <summary>查看原始详情</summary>
                    <pre className="error-details-block">{detailText}</pre>
                </details>
            ) : null}
        </div>
    )
}

function buildErrorDetailText(error) {
    const lines = []

    if (error.statusCode) {
        lines.push(`HTTP 状态：${error.statusCode}`)
    }
    if (error.rawMessage && error.rawMessage !== error.displayMessage) {
        lines.push(`原始消息：${error.rawMessage}`)
    }
    if (error.details !== null && error.details !== undefined) {
        const detailsText = typeof error.details === 'string'
            ? error.details
            : JSON.stringify(error.details, null, 2)
        lines.push(`详细信息：\n${detailsText}`)
    }

    return lines.join('\n\n')
}

function FileTree({ tree, onSelect }) {
    const sections = Object.entries(tree || {})
    if (sections.length === 0) return <div className="empty-state">暂无可用文件</div>
    return (
        <div className="tree-root">
            {sections.map(([rootName, children]) => (
                <div key={rootName} className="tree-section">
                    <div className="tree-title">{rootName}</div>
                    <TreeNodes nodes={children} onSelect={onSelect} />
                </div>
            ))}
        </div>
    )
}

function TreeNodes({ nodes, onSelect }) {
    return (
        <div className="tree-nodes">
            {nodes.map((node) => (
                <div key={node.path} className="tree-node">
                    {node.type === 'dir' ? (
                        <>
                            <div className="tree-folder">{node.name}</div>
                            <TreeNodes nodes={node.children || []} onSelect={onSelect} />
                        </>
                    ) : (
                        <button className="tree-file" onClick={() => onSelect(node.path)}>{node.name}</button>
                    )}
                </div>
            ))}
        </div>
    )
}
