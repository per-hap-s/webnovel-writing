import { useEffect, useState } from 'react'
import { normalizeError, postJSON } from './api.js'
import { ErrorNotice, Field } from './sectionCommon.jsx'

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
    require_manual_approval: false,
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
                        正文回写前需要人工确认
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
