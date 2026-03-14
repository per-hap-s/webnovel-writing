import { useEffect, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'

const LLM_PROVIDER_OPTIONS = [
    { value: 'openai-compatible', label: 'OpenAI Compatible' },
    { value: 'openai', label: 'OpenAI Official' },
    { value: 'azure-openai', label: 'Azure OpenAI' },
]

export function TaskLauncherSection({ template, onCreated, onSuccess, MODE_OPTIONS }) {
    const [form, setForm] = useState({
        project_root: '',
        title: '',
        genre: '玄幻',
        chapter: 1,
        chapter_range: '1-3',
        volume: '1',
        mode: 'standard',
        require_manual_approval: true,
    })
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
    if (status.connection_status === 'connected') return '\u5df2\u8fde\u63a5'
    if (status.connection_status === 'failed') return '\u8fde\u63a5\u5931\u8d25'
    if (status.connection_status === 'not_configured') return '\u672a\u914d\u7f6e'
    return status.connection_status || '\u672a\u68c0\u6d4b'
}


export function TaskCenterPageSection({
    tasks,
    selectedTask,
    onSelectTask,
    onMutated,
    MetricCard,
    translateTaskType,
    translateTaskStatus,
    translateApprovalStatus,
    translateStepName,
    translateEventLevel,
    translateEventMessage,
}) {
    const [events, setEvents] = useState([])
    const [actionError, setActionError] = useState(null)

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
                    {tasks.map((task) => (
                        <button key={task.id} className={`task-item ${selectedTask?.id === task.id ? 'active' : ''}`} onClick={() => onSelectTask(task.id)}>
                            <div>{translateTaskType(task.task_type)}</div>
                            <div className="muted">{translateTaskStatus(task.status)}</div>
                            <div className="tiny">{translateStepName(task.current_step || 'idle')}</div>
                        </button>
                    ))}
                    {tasks.length === 0 && <div className="empty-state">暂无任务</div>}
                </div>
            </section>
            <section className="panel detail-panel">
                <div className="panel-title">任务详情</div>
                {!selectedTask && <div className="empty-state">请选择任务查看详情</div>}
                {selectedTask && (
                    <>
                        <div className="detail-grid">
                            <MetricCard label="状态" value={translateTaskStatus(selectedTask.status)} />
                            <MetricCard label="当前步骤" value={translateStepName(selectedTask.current_step || 'idle')} />
                            <MetricCard label="审批" value={translateApprovalStatus(selectedTask.approval_status || 'n/a')} />
                            <MetricCard label="类型" value={translateTaskType(selectedTask.task_type)} />
                        </div>
                        <div className="button-row">
                            <button className="secondary-button" onClick={() => perform(`/api/tasks/${selectedTask.id}/retry`, {})}>重试</button>
                            {selectedTask.status === 'awaiting_writeback_approval' && (
                                <>
                                    <button className="primary-button" onClick={() => perform('/api/review/approve', { task_id: selectedTask.id, reason: '由仪表盘批准回写' })}>批准回写</button>
                                    <button className="danger-button" onClick={() => perform('/api/review/reject', { task_id: selectedTask.id, reason: '由仪表盘拒绝回写' })}>拒绝回写</button>
                                </>
                            )}
                        </div>
                        <ErrorNotice error={actionError} />
                        <ErrorNotice error={selectedTask.error || null} title="任务失败原因" />
                        <div className="subsection">
                            <div className="subsection-title">步骤输出</div>
                            <pre className="code-block">{JSON.stringify(selectedTask.artifacts?.step_results || {}, null, 2)}</pre>
                        </div>
                        <div className="subsection">
                            <div className="subsection-title">事件流</div>
                            <div className="event-list">
                                {events.map((event) => (
                                    <div key={event.id} className={`event-card ${event.level}`}>
                                        <div className="event-meta">[{translateEventLevel(event.level)}] {translateStepName(event.step_name || 'task')} · {event.timestamp}</div>
                                        <div>{translateEventMessage(event.message)}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </>
                )}
            </section>
        </div>
    )
}

export function DataPageSection({ SimpleTable }) {
    const [entities, setEntities] = useState([])
    const [relationships, setRelationships] = useState([])
    const [chapters, setChapters] = useState([])

    useEffect(() => {
        fetchJSON('/api/entities').then(setEntities).catch(() => setEntities([]))
        fetchJSON('/api/relationships', { limit: 80 }).then(setRelationships).catch(() => setRelationships([]))
        fetchJSON('/api/chapters').then(setChapters).catch(() => setChapters([]))
    }, [])

    return (
        <div className="page-grid">
            <section className="panel">
                <div className="panel-title">实体</div>
                <SimpleTable rows={entities} columns={['name', 'type', 'tier', 'last_appearance']} />
            </section>
            <section className="panel">
                <div className="panel-title">关系</div>
                <SimpleTable rows={relationships} columns={['from_entity', 'to_entity', 'type', 'chapter']} />
            </section>
            <section className="panel full-span">
                <div className="panel-title">章节</div>
                <SimpleTable rows={chapters} columns={['chapter', 'title', 'word_count']} />
            </section>
        </div>
    )
}

export function FilesPageSection() {
    const [tree, setTree] = useState({})
    const [selectedPath, setSelectedPath] = useState('')
    const [content, setContent] = useState('')
    const [error, setError] = useState(null)

    useEffect(() => {
        fetchJSON('/api/files/tree').then((result) => {
            setTree(result)
            setError(null)
        }).catch((err) => {
            setTree({})
            setError(normalizeError(err))
        })
    }, [])

    useEffect(() => {
        if (!selectedPath) return
        fetchJSON('/api/files/read', { path: selectedPath }).then((result) => {
            setContent(result.content || '')
            setError(null)
        }).catch((err) => {
            setContent('读取失败')
            setError(normalizeError(err))
        })
    }, [selectedPath])

    return (
        <div className="split-layout">
            <section className="panel list-panel">
                <div className="panel-title">文档树</div>
                <FileTree tree={tree} onSelect={setSelectedPath} />
            </section>
            <section className="panel detail-panel">
                <div className="panel-title">{selectedPath || '选择文件'}</div>
                <ErrorNotice error={error} />
                <pre className="code-block large">{content || '无内容'}</pre>
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
