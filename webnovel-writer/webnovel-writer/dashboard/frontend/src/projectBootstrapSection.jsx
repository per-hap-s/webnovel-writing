import { useEffect, useState } from 'react'
import { normalizeError, postJSON } from './api.js'
import { ErrorNotice, Field } from './sectionCommon.jsx'

const DEFAULT_LAUNCHER_FORM = {
    project_root: '',
    title: '',
    genre: '玄幻',
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
    const [showCreateForm, setShowCreateForm] = useState(() => !projectInitialized)
    const [submitting, setSubmitting] = useState(false)
    const [error, setError] = useState(null)

    const nextPrefillKey = `${currentProjectRoot || ''}|${currentTitle || ''}|${currentGenre || ''}|${projectInitialized ? '1' : '0'}`

    useEffect(() => {
        if (nextPrefillKey === prefillKey) return
        setForm(buildBootstrapForm(currentProjectRoot, currentTitle, currentGenre))
        setPrefillKey(nextPrefillKey)
        setShowCreateForm(!projectInitialized)
        setError(null)
    }, [currentProjectRoot, currentTitle, currentGenre, projectInitialized, nextPrefillKey, prefillKey])

    const normalizedCurrentRoot = normalizePath(currentProjectRoot)
    const normalizedTargetRoot = normalizePath(form.project_root)
    const targetingCurrentProject = Boolean(
        projectInitialized
        && normalizedCurrentRoot
        && (!normalizedTargetRoot || normalizedTargetRoot === normalizedCurrentRoot)
    )
    const shouldShowCreateForm = !projectInitialized || showCreateForm || !targetingCurrentProject

    function switchToNewDirectoryMode() {
        setShowCreateForm(true)
        setError(null)
        setForm((current) => ({
            ...current,
            project_root: '',
        }))
    }

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
            {shouldShowCreateForm ? (
                <>
                    {projectInitialized ? (
                        <div className="tiny">
                            当前已经打开一个已初始化项目。请使用新的空目录创建项目。
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
                </>
            ) : (
                <div className="planning-warning subtle project-bootstrap-info">
                    <div className="subsection-title">当前目录已是可用项目</div>
                    <div className="tiny">这里先展示当前项目说明，避免把同一目录误当成新项目重复创建。</div>
                    <div className="project-bootstrap-meta">
                        <div><strong>当前项目：</strong>{currentTitle || '未命名项目'}</div>
                        <div><strong>题材：</strong>{currentGenre || '未填写'}</div>
                        <div><strong>项目根目录：</strong>{currentProjectRoot || '未提供'}</div>
                    </div>
                    <div className="button-row">
                        <button type="button" className="secondary-button" onClick={switchToNewDirectoryMode}>改用新目录新建项目</button>
                    </div>
                </div>
            )}
            <ErrorNotice error={error} />
            {shouldShowCreateForm ? (
                <button className="primary-button" onClick={submit} disabled={submitting || targetingCurrentProject}>
                    {submitting ? '创建中...' : '创建项目'}
                </button>
            ) : null}
            {shouldShowCreateForm && projectInitialized && !targetingCurrentProject ? (
                <button type="button" className="ghost-button" onClick={() => setShowCreateForm(false)} disabled={submitting}>
                    收起并返回当前项目说明
                </button>
            ) : null}
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
