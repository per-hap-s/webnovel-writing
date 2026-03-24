import { useEffect, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'
import { ErrorNotice, Field } from './sectionCommon.jsx'

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
