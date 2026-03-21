import { useEffect, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'
import { formatTimestampShort } from './dashboardPageCommon.jsx'

import { TaskCenterPageSection as TaskCenterPageSectionImpl } from './taskCenterPageSection.jsx'

const RELATIONSHIP_TYPE_LABELS = {
    family: '家庭',
    ally: '同盟',
    enemy: '敌对',
    mentor: '师友',
    subordinate: '上下级',
    colleague: '同事',
    suspect: '嫌疑',
    investigating: '调查',
    conflict: '冲突',
    owes: '欠债',
    protects: '保护',
    watches: '监视',
    warned_by: '预警来源',
}

const LLM_PROVIDER_OPTIONS = [
    { value: 'openai-compatible', label: '兼容 OpenAI 接口' },
    { value: 'openai', label: 'OpenAI 官方接口' },
    { value: 'azure-openai', label: 'Azure OpenAI 接口' },
]

const DEFAULT_LAUNCHER_FORM = {
    project_root: '',
    title: '',
    genre: '玄幻',
    chapter: 1,
    start_chapter: 1,
    max_chapters: 2,
    chapter_range: '1-3',
    volume: '1',
    mode: 'standard',
    require_manual_approval: true,
}

export function TaskLauncherSection({ template, onCreated, onSuccess, MODE_OPTIONS, suggestedChapter }) {
    const [form, setForm] = useState(DEFAULT_LAUNCHER_FORM)
    const [lastSuggestedChapter, setLastSuggestedChapter] = useState(DEFAULT_LAUNCHER_FORM.chapter)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState(null)

    useEffect(() => {
        if (!template.fields.includes('chapter') && !template.fields.includes('start_chapter')) return
        const nextSuggested = Math.max(1, Number(suggestedChapter || 1))
        setForm((current) => {
            const nextForm = { ...current }
            if (template.fields.includes('chapter')) {
                if (current.chapter !== lastSuggestedChapter && current.chapter > 0) return current
                nextForm.chapter = nextSuggested
            }
            if (template.fields.includes('start_chapter')) {
                if (current.start_chapter !== lastSuggestedChapter && current.start_chapter > 0) return current
                nextForm.start_chapter = nextSuggested
            }
            return nextForm
        })
        setLastSuggestedChapter(nextSuggested)
    }, [template.fields, suggestedChapter, lastSuggestedChapter])

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
        <div className="launcher-card task-launcher-card">
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
                {template.fields.includes('start_chapter') && (
                    <Field label="起始章节">
                        <input type="number" value={form.start_chapter} onChange={(event) => setForm({ ...form, start_chapter: Number(event.target.value) })} />
                    </Field>
                )}
                {template.fields.includes('max_chapters') && (
                    <Field label="最多推进章数">
                        <input type="number" min="1" value={form.max_chapters} onChange={(event) => setForm({ ...form, max_chapters: Number(event.target.value) })} />
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
            <div className="launcher-card-footer">
                <button className="primary-button" onClick={submit} disabled={submitting}>{submitting ? '提交中...' : (template.submitLabel || '创建任务')}</button>
            </div>
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
            setMessage('规划信息已保存，总纲与规划条件已同步更新。')
            if (onSaved) onSaved(response)
        } catch (err) {
            setError(normalizeError(err))
        } finally {
            setSaving(false)
        }
    }

    const missingItems = readiness?.blocking_items || readiness?.missing_items || []

    return (
        <div className="planning-profile planning-profile-form">
            <div className="planning-status-row">
                <div className={`planning-pill ${readiness?.ok ? 'ready' : 'blocked'}`}>
                    {readiness?.ok ? '已满足规划条件' : '待补信息'}
                </div>
                <div className="tiny">
                    {readiness ? `已填写 ${readiness.completed_fields || 0}/${readiness.total_required_fields || 0}` : '正在读取规划条件...'}
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
                    <div className="subsection-title">最近一次规划阻断</div>
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
    selectedTaskId,
    currentProjectRoot,
    onSelectTask,
    onMutated,
    onNavigateOverview,
    MetricCard,
    translateTaskType,
    translateTaskStatus,
    translateStepName,
    translateEventLevel,
    translateEventMessage,
    resolveTaskStatusLabel,
    resolveCurrentStepLabel,
    resolveApprovalStatusLabel,
    resolveTargetLabel,
}) {
    return (
        <TaskCenterPageSectionImpl
            tasks={tasks}
            selectedTask={selectedTask}
            selectedTaskId={selectedTaskId}
            currentProjectRoot={currentProjectRoot}
            onSelectTask={onSelectTask}
            onMutated={onMutated}
            onNavigateOverview={onNavigateOverview}
            ErrorNotice={ErrorNotice}
            MetricCard={MetricCard}
            translateTaskType={translateTaskType}
            translateTaskStatus={translateTaskStatus}
            translateStepName={translateStepName}
            translateEventLevel={translateEventLevel}
            translateEventMessage={translateEventMessage}
            resolveTaskStatusLabel={resolveTaskStatusLabel}
            resolveCurrentStepLabel={resolveCurrentStepLabel}
            resolveApprovalStatusLabel={resolveApprovalStatusLabel}
            resolveTargetLabel={resolveTargetLabel}
        />
    )
}

export function DataPageSection({ SimpleTable, refreshToken }) {
    const [entities, setEntities] = useState([])
    const [relationships, setRelationships] = useState([])
    const [chapters, setChapters] = useState([])
    const [storyPlans, setStoryPlans] = useState([])

    useEffect(() => {
        fetchJSON('/api/entities').then(setEntities).catch(() => setEntities([]))
        fetchJSON('/api/relationships', { limit: 80 }).then(setRelationships).catch(() => setRelationships([]))
        fetchJSON('/api/chapters').then(setChapters).catch(() => setChapters([]))
        fetchJSON('/api/story-plans', { limit: 12 }).then(setStoryPlans).catch(() => setStoryPlans([]))
    }, [refreshToken])

    const chapterSummaryData = buildChapterSummaries(chapters, entities, relationships)
    const chapterSummaries = chapterSummaryData.items

    return (
        <div className="page-grid">
            <section className="panel full-span">
                <div className="panel-title">{chapterSummaryData.title}</div>
                {chapterSummaries.length === 0 ? (
                    <div className="tiny">当前还没有可展示的章节摘要；如果写作已完成但这里为空，请回到对应任务查看 `data-sync` warning。</div>
                ) : (
                    <div className="summary-grid">
                        {chapterSummaries.map((item) => (
                            <div key={item.chapter} className="summary-card">
                                <div className="summary-card-title">第 {item.chapter} 章</div>
                                <div className="tiny">{item.title || '未命名章节'}</div>
                                <div className="summary-card-meta">{chapterSummaryData.entityLabel}：{item.entityCount}</div>
                                <div className="summary-card-meta">{chapterSummaryData.relationshipLabel}：{item.relationshipCount}</div>
                            </div>
                        ))}
                    </div>
                )}
            </section>
            <section className="panel full-span">
                <div className="panel-title">Story Plans</div>
                {storyPlans.length === 0 ? (
                    <div className="tiny">当前还没有可展示的多章滚动规划；请先运行带 `story-director` 的写作任务。</div>
                ) : (
                    <div className="summary-grid">
                        {storyPlans.map((plan) => (
                            <div key={plan.path || plan.anchor_chapter} className="summary-card">
                                <div className="summary-card-title">锚点第 {plan.anchor_chapter} 章</div>
                                <div className="tiny">窗口 {plan.planning_horizon || '-'} 章 · 更新时间 {formatTimestampShort(plan.updated_at_display || plan.updated_at || '-')}</div>
                                <div className="summary-card-meta">当前槽位：{plan.current_role || 'progression'}</div>
                                <div className="summary-card-meta">{plan.current_goal || '-'}</div>
                                <div className="summary-card-meta">Hook：{plan.current_hook || '-'}</div>
                                {Array.isArray(plan.priority_threads) && plan.priority_threads.length ? (
                                    <div className="planning-tags">
                                        {plan.priority_threads.slice(0, 4).map((item) => (
                                            <span key={`${plan.anchor_chapter}-${item}`} className="planning-tag">{item}</span>
                                        ))}
                                    </div>
                                ) : null}
                                {Array.isArray(plan.risk_flags) && plan.risk_flags.length ? (
                                    <div className="alignment-list">
                                        {plan.risk_flags.slice(0, 2).map((item) => (
                                            <div key={`${plan.anchor_chapter}-risk-${item}`} className="alignment-chip missed">{item}</div>
                                        ))}
                                    </div>
                                ) : null}
                            </div>
                        ))}
                    </div>
                )}
            </section>
            <section className="panel">
                <div className="panel-title">实体</div>
                {chapters.length > 0 && entities.length === 0 ? <div className="tiny">当前已有章节，但暂未看到结构化实体；如本章未抽取到结果，会在对应任务事件流里显示 warning。</div> : null}
                <SimpleTable rows={entities} columns={['name', 'type', 'tier', 'last_appearance']} />
            </section>
            <section className="panel">
                <div className="panel-title">关系</div>
                {chapters.length > 0 && relationships.length === 0 ? <div className="tiny">当前已有章节，但暂未看到结构化关系；请同时检查对应写作任务的 `data-sync` 事件。</div> : null}
                <SimpleTable rows={relationships} columns={['from_entity_display', 'to_entity_display', 'type_label', 'chapter']} />
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
    const [fileDetail, setFileDetail] = useState(emptyFileDetail())
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [missingNotice, setMissingNotice] = useState('')

    useEffect(() => {
        fetchJSON('/api/files/tree').then((result) => {
            setTree(result)
            if (selectedPath && !treeContainsPath(result, selectedPath)) {
                setSelectedPath('')
                setFileDetail(emptyFileDetail())
                setMissingNotice('当前文件已不存在，已清除选中。')
            }
            setError(null)
        }).catch((err) => {
            setTree({})
            setError(normalizeError(err))
        })
    }, [refreshToken])

    useEffect(() => {
        if (!selectedPath) {
            setFileDetail(emptyFileDetail())
            return
        }
        setLoading(true)
        setMissingNotice('')
        fetchJSON('/api/files/read', { path: selectedPath }).then((result) => {
            if (result.exists === false) {
                setSelectedPath('')
                setFileDetail(emptyFileDetail())
                setError(null)
                setMissingNotice('当前文件已不存在，已清除选中。')
                return
            }
            setFileDetail({
                path: result.path || selectedPath,
                content: typeof result.content === 'string' ? result.content : '',
                exists: Boolean(result.exists),
                is_binary: Boolean(result.is_binary),
                encoding: result.encoding || 'utf-8',
                size: Number(result.size || 0),
                modified_at: result.modified_at || '',
                display_name: result.display_name || '',
                is_internal: Boolean(result.is_internal),
                doc_status: result.doc_status || null,
                summary_card: result.summary_card || null,
                internal_hint: result.internal_hint || '',
            })
            setError(null)
        }).catch((err) => {
            const normalized = normalizeError(err)
            if (normalized.statusCode === 404) {
                setSelectedPath('')
                setFileDetail(emptyFileDetail())
                setError(null)
                setMissingNotice('当前文件已不存在，已清除选中。')
            } else {
                setFileDetail({ ...emptyFileDetail(), path: selectedPath })
                setError(normalized)
            }
        }).finally(() => setLoading(false))
    }, [selectedPath, refreshToken])

    const selectedNode = findTreeNode(tree, selectedPath)
    const fileMeta = resolveFileDisplayMeta(selectedPath || fileDetail.path, selectedNode, fileDetail)
    const previewText = !selectedPath
        ? (missingNotice || '请选择左侧文件')
        : loading
            ? '读取中...'
            : fileDetail.is_binary
                ? `该文件为二进制或非 UTF-8 文本，当前编码：${fileDetail.encoding}`
                : fileDetail.exists
                    ? (fileDetail.content === '' ? '无内容' : fileDetail.content)
                    : '读取失败'

    return (
        <div className="split-layout files-layout">
            <section className="panel list-panel file-tree-panel">
                <div className="panel-title">文档树</div>
                <div className="file-tree-scroll">
                    <FileTree tree={tree} onSelect={setSelectedPath} />
                </div>
            </section>
            <section className="panel detail-panel file-preview-panel">
                <div className="panel-title">{fileMeta.displayName || selectedPath || '选择文件'}</div>
                {selectedPath ? (
                    <div className="file-meta-card">
                        <div className="file-meta-grid">
                            <div><strong>显示名称：</strong>{fileMeta.displayName}</div>
                            <div><strong>真实路径：</strong>{fileDetail.path || selectedPath}</div>
                            <div><strong>文件类型：</strong>{fileMeta.fileType}</div>
                            <div><strong>状态标签：</strong>{fileMeta.docStatus || '-'}</div>
                            <div><strong>编码：</strong>{fileDetail.encoding || '-'}</div>
                            <div><strong>大小：</strong>{formatFileSize(fileDetail.size)}</div>
                            <div><strong>更新时间：</strong>{formatTimestampShort(fileDetail.modified_at || '-')}</div>
                        </div>
                    </div>
                ) : null}
                {selectedPath && fileDetail.summary_card ? (
                    <div className="file-meta-card">
                        <div className="subsection-title">{fileDetail.summary_card.title || '摘要'}</div>
                        {fileDetail.summary_card.warning ? <div className="tiny">{fileDetail.summary_card.warning}</div> : null}
                        <div className="file-meta-grid">
                            {(fileDetail.summary_card.items || []).map((item) => (
                                <div key={`${item.label}-${item.value}`}><strong>{item.label}：</strong>{item.value || '-'}</div>
                            ))}
                        </div>
                    </div>
                ) : null}
                {selectedPath && fileDetail.internal_hint ? <div className="tiny">{fileDetail.internal_hint}</div> : null}
                <ErrorNotice error={error} />
                <pre className="code-block file-preview">{previewText}</pre>
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

export function ErrorNotice({ error, title = '操作失败' }) {
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
            {nodes.map((node) => <TreeNode key={node.path} node={node} onSelect={onSelect} />)}
        </div>
    )
}

function TreeNode({ node, onSelect }) {
    const [expanded, setExpanded] = useState(true)

    if (node.type === 'dir') {
        return (
            <div className="tree-node">
                <button className="tree-folder tree-folder-toggle" onClick={() => setExpanded((value) => !value)}>
                    <span className="tree-folder-icon">{expanded ? '▾' : '▸'}</span>
                    <span>{displayTreeNodeName(node)}</span>
                </button>
                {expanded ? <TreeNodes nodes={node.children || []} onSelect={onSelect} /> : null}
            </div>
        )
    }

    return (
        <div className="tree-node">
            <button className="tree-file" onClick={() => onSelect(node.path)}>{displayTreeNodeName(node)}</button>
        </div>
    )
}

function displayTreeNodeName(node) {
    return resolveFileDisplayMeta(node?.path || node?.name || '', node).displayName
}

function resolveFileDisplayMeta(path, node = null, fileDetail = null) {
    const preferred = resolveLegacyFileDisplayMeta(path)
    const fallbackDisplayName = node?.display_name || fileDetail?.display_name || preferred.displayName
    return {
        displayName: preferred.displayName || fallbackDisplayName || '未命名文件',
        fileType: preferred.fileType || resolveFileType(path),
        docStatus: node?.doc_status || fileDetail?.doc_status || null,
        isInternal: Boolean(node?.is_internal || fileDetail?.is_internal),
    }
}

function resolveLegacyFileDisplayMeta(path) {
    const normalizedPath = String(path || '').replace(/\\/g, '/')
    const segments = normalizedPath.split('/').filter(Boolean)
    const name = segments[segments.length - 1] || normalizedPath || '未命名文件'
    const chapterInVolumeMatch = normalizedPath.match(/^正文\/第(\d+)卷\/第(\d{4})章\.md$/)
    const volumeDirMatch = normalizedPath.match(/^正文\/第(\d+)卷$/)
    if (normalizedPath === '.webnovel/state.json' || name === 'state.json') {
        return { displayName: 'state.json', fileType: '状态文件' }
    }
    if (normalizedPath === '正文') {
        return { displayName: '正文', fileType: '目录' }
    }
    if (volumeDirMatch) {
        return { displayName: `第${String(Number(volumeDirMatch[1]))}卷`, fileType: '卷目录' }
    }
    if (normalizedPath === '.webnovel/summaries' || name === '章节摘要') {
        return { displayName: '章节摘要', fileType: '目录' }
    }
    const volumePlanMatch = name.match(/^volume-(\d+)-plan\.md$/i)
    if (volumePlanMatch) {
        return { displayName: `第${String(Number(volumePlanMatch[1]))}卷规划.md`, fileType: '卷规划' }
    }
    const chapterFileMatch = name.match(/^ch(\d{4})\.md$/i)
    if (chapterFileMatch) {
        return { displayName: `第${String(Number(chapterFileMatch[1]))}章摘要.md`, fileType: '摘要' }
    }
    if (chapterInVolumeMatch) {
        return {
            displayName: `第${String(Number(chapterInVolumeMatch[2]))}章`,
            fileType: '正文',
        }
    }
    const chapterBodyMatch = name.match(/^第(\d{4})章\.md$/i)
    if (chapterBodyMatch) {
        return { displayName: `第${String(Number(chapterBodyMatch[1]))}章正文.md`, fileType: '正文' }
    }
    if (name === '总纲.md') {
        return { displayName: '总纲.md', fileType: '总纲' }
    }
    if (segments.includes('设定集')) {
        return { displayName: name, fileType: '设定' }
    }
    if (segments.includes('大纲')) {
        return { displayName: name, fileType: '大纲' }
    }
    if (segments.includes('正文')) {
        return { displayName: name, fileType: '正文' }
    }
    return { displayName: name, fileType: segments.length > 1 ? '文件' : '目录' }
}

function resolveFileType(path) {
    const normalizedPath = String(path || '').replace(/\\/g, '/')
    if (normalizedPath === '.webnovel/state.json') return '状态文件'
    if (/\/第\d+卷$/.test(normalizedPath)) return '卷目录'
    if (/\/第\d{4}章\.md$/.test(normalizedPath)) return '正文'
    if (/\/ch\d{4}\.md$/i.test(normalizedPath)) return '摘要'
    if (/volume-\d+-plan\.md$/i.test(normalizedPath)) return '卷规划'
    if (normalizedPath.endsWith('/总纲.md')) return '总纲'
    if (normalizedPath.includes('设定集/')) return '设定'
    return normalizedPath.split('/').length > 1 ? '文件' : '目录'
}

function translateRelationshipType(value) {
    return RELATIONSHIP_TYPE_LABELS[String(value || '').trim()] || String(value || '-')
}

function buildChapterSummaries(chapters, entities, relationships) {
    const hasFirstAppearance = (entities || []).some((item) => item?.first_appearance !== undefined && item?.first_appearance !== null)
    const items = (chapters || []).map((chapter) => {
        const number = Number(chapter.chapter || 0)
        return {
            chapter: number,
            title: chapter.title || '',
            entityCount: (entities || []).filter((item) => Number(hasFirstAppearance ? item.first_appearance : item.last_appearance || 0) === number).length,
            relationshipCount: (relationships || []).filter((item) => Number(item.chapter || 0) === number).length,
        }
    }).filter((item) => item.chapter > 0)
    return {
        items,
        title: hasFirstAppearance ? '本章新增摘要' : '本章实体/关系摘要',
        entityLabel: hasFirstAppearance ? '新增实体' : '实体',
        relationshipLabel: hasFirstAppearance ? '新增关系' : '关系',
    }
}

function treeContainsPath(tree, targetPath) {
    const target = String(targetPath || '').trim()
    if (!target) return false
    const nodes = Object.values(tree || {}).flat()
    return walkTreeNodes(nodes).some((node) => node?.type === 'file' && node.path === target)
}

function walkTreeNodes(nodes) {
    const output = []
    ;(nodes || []).forEach((node) => {
        output.push(node)
        if (node?.children?.length) {
            output.push(...walkTreeNodes(node.children))
        }
    })
    return output
}

function findTreeNode(tree, targetPath) {
    if (!targetPath) return null
    return walkTreeNodes(Object.values(tree || {}).flat()).find((node) => node?.path === targetPath) || null
}

function emptyFileDetail() {
    return {
        path: '',
        content: '',
        exists: false,
        is_binary: false,
        encoding: 'utf-8',
        size: 0,
        modified_at: '',
        display_name: '',
        is_internal: false,
        doc_status: null,
        summary_card: null,
        internal_hint: '',
    }
}

function displayPathAlias(path) {
    return resolveFileDisplayMeta(path).displayName
}

function formatFileSize(size) {
    const value = Number(size || 0)
    if (!Number.isFinite(value) || value <= 0) return '-'
    if (value < 1024) return `${value} B`
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
    return `${(value / (1024 * 1024)).toFixed(1)} MB`
}
