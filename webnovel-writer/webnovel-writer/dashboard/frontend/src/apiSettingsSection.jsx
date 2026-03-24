import { useEffect, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'
import { ErrorNotice, Field } from './sectionCommon.jsx'

const LLM_PROVIDER_OPTIONS = [
    { value: 'openai-compatible', label: '兼容 OpenAI 接口' },
    { value: 'openai', label: 'OpenAI 官方接口' },
    { value: 'azure-openai', label: 'Azure OpenAI 接口' },
]

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
        : [{ value: llmForm.provider, label: `自定义：${llmForm.provider}` }, ...LLM_PROVIDER_OPTIONS]

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
                setMessage((current) => ({ ...current, llm: '写作模型 API 设置已保存' }))
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
                setMessage((current) => ({ ...current, rag: 'RAG API 设置已保存' }))
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
                <div className="launcher-title">写作模型 API</div>
                <div className="muted">用于规划、写作、审查等工作流调用的大模型接口。</div>
                <div className="tiny">当前状态：{translateConnection(llmStatus)}</div>
                {loading ? <div className="tiny">正在读取当前配置...</div> : null}
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
                    <Field label="模型名称">
                        <input value={llmForm.model} onChange={(event) => setLlmForm({ ...llmForm, model: event.target.value })} placeholder="例如：gpt-4.1-mini" />
                    </Field>
                    <Field label="API Key">
                        <input type="password" value={llmForm.api_key} onChange={(event) => setLlmForm({ ...llmForm, api_key: event.target.value })} placeholder={meta.llmHasKey ? `留空则保留当前 Key（${meta.llmMasked}）` : '输入新的 API Key'} />
                    </Field>
                </div>
                <div className="tiny">保存位置：项目根目录 `.env`。留空不覆盖已有 Key。</div>
                <ErrorNotice error={error.llm} />
                {message.llm ? <div className="success-text">{message.llm}</div> : null}
                <button className="primary-button" onClick={() => saveSection('llm')} disabled={saving.llm || loading || !llmDirty}>
                    {saving.llm ? '保存中...' : '保存写作模型 API'}
                </button>
            </div>

            <div className="launcher-card settings-card">
                <div className="launcher-title">RAG API</div>
                <div className="muted">用于 Embedding、Rerank 和检索链路的接口配置。</div>
                <div className="tiny">当前状态：{translateConnection(ragStatus)}</div>
                {loading ? <div className="tiny">正在读取当前配置...</div> : null}
                <div className="field-stack">
                    <Field label="Base URL">
                        <input value={ragForm.base_url} onChange={(event) => setRagForm({ ...ragForm, base_url: event.target.value })} placeholder="https://api.siliconflow.cn/v1" />
                    </Field>
                    <Field label="Embedding 模型">
                        <input value={ragForm.embed_model} onChange={(event) => setRagForm({ ...ragForm, embed_model: event.target.value })} placeholder="例如：BAAI/bge-m3" />
                    </Field>
                    <Field label="Rerank 模型">
                        <input value={ragForm.rerank_model} onChange={(event) => setRagForm({ ...ragForm, rerank_model: event.target.value })} placeholder="例如：BAAI/bge-reranker-v2-m3" />
                    </Field>
                    <Field label="API Key">
                        <input type="password" value={ragForm.api_key} onChange={(event) => setRagForm({ ...ragForm, api_key: event.target.value })} placeholder={meta.ragHasKey ? `留空则保留当前 Key（${meta.ragMasked}）` : '输入新的 API Key'} />
                    </Field>
                </div>
                <div className="tiny">保存位置：项目根目录 `.env`。当前实现默认 Embedding 和 Rerank 共用同一组 RAG Key。</div>
                <ErrorNotice error={error.rag} />
                {message.rag ? <div className="success-text">{message.rag}</div> : null}
                <button className="primary-button" onClick={() => saveSection('rag')} disabled={saving.rag || loading || !ragDirty}>
                    {saving.rag ? '保存中...' : '保存 RAG API'}
                </button>
            </div>
        </div>
    )
}

function translateConnection(status) {
    if (!status) return '未检测'
    const effectiveStatus = status.effective_status || status.connection_status
    if (effectiveStatus === 'connected') return '已连接'
    if (effectiveStatus === 'degraded') return '探活异常，最近执行成功'
    if (effectiveStatus === 'failed') return '连接失败'
    if (effectiveStatus === 'not_configured') return '未配置'
    return effectiveStatus || '未检测'
}
