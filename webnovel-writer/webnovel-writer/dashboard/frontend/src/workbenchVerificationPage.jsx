import { useEffect, useState } from 'react'
import { ErrorNotice } from './appSections.jsx'
import { fetchJSON, fetchText, normalizeError, postJSON } from './api.js'

function isActiveExecution(execution) {
    const status = String(execution?.status || '').trim()
    return status === 'starting' || status === 'running'
}

function pickPreferredRunId(overview, currentRunId) {
    const activeRunId = String(overview?.active_execution?.run_id || '').trim()
    if (activeRunId && isActiveExecution(overview?.active_execution)) {
        return activeRunId
    }
    const runs = Array.isArray(overview?.runs) ? overview.runs : []
    if (currentRunId && runs.some((item) => item?.run_id === currentRunId)) {
        return currentRunId
    }
    return String(runs[0]?.run_id || '').trim()
}

function renderValue(value, fallback = '暂无') {
    const normalized = String(value || '').trim()
    return normalized || fallback
}

function summarizeLaneFailure(lane) {
    const failedStep = (lane?.steps || []).find((step) => step?.passed === false) || null
    if (!failedStep) return '当前 lane 未发现失败步骤。'
    return `${failedStep.name || failedStep.id || '未命名步骤'} / ${renderValue(failedStep.failure_kind, '-') } / ${renderValue(failedStep.blocking_severity, '-')}`
}

export function WorkbenchVerificationPage({ visible }) {
    const [overview, setOverview] = useState(null)
    const [detail, setDetail] = useState(null)
    const [selectedRunId, setSelectedRunId] = useState('')
    const [busyKey, setBusyKey] = useState('')
    const [error, setError] = useState(null)
    const [detailError, setDetailError] = useState(null)
    const [logError, setLogError] = useState(null)
    const [logTitle, setLogTitle] = useState('')
    const [logContent, setLogContent] = useState('')

    async function loadOverview(options = {}) {
        const preserveSelection = options.preserveSelection === true
        try {
            const payload = await fetchJSON('/api/workbench/verification/overview', { limit: 10 })
            setOverview(payload)
            setError(null)
            const nextRunId = pickPreferredRunId(payload, preserveSelection ? selectedRunId : '')
            if (nextRunId) {
                setSelectedRunId(nextRunId)
            } else if (!preserveSelection) {
                setSelectedRunId('')
                setDetail(null)
            }
        } catch (requestError) {
            setError(normalizeError(requestError))
        }
    }

    async function loadDetail(runId) {
        if (!runId) {
            setDetail(null)
            return
        }
        try {
            const payload = await fetchJSON(`/api/workbench/verification/runs/${runId}`)
            setDetail(payload)
            setDetailError(null)
        } catch (requestError) {
            setDetail(null)
            setDetailError(normalizeError(requestError))
        }
    }

    async function refreshAll(options = {}) {
        await loadOverview(options)
    }

    async function startVerification() {
        setBusyKey('run')
        setError(null)
        try {
            const payload = await postJSON('/api/workbench/verification/run', {})
            setOverview((currentOverview) => ({
                ...(currentOverview || {}),
                active_execution: payload.execution,
                runs: currentOverview?.runs || [],
            }))
            if (payload?.execution?.run_id) {
                setSelectedRunId(payload.execution.run_id)
            }
            await refreshAll({ preserveSelection: true })
        } catch (requestError) {
            setError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    async function loadText(url, title) {
        if (!url) return
        setBusyKey(title)
        setLogError(null)
        try {
            const text = await fetchText(url)
            setLogTitle(title)
            setLogContent(text)
        } catch (requestError) {
            setLogError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    useEffect(() => {
        if (!visible) return
        void refreshAll()
    }, [visible])

    useEffect(() => {
        if (!visible || !selectedRunId) return
        void loadDetail(selectedRunId)
    }, [visible, selectedRunId])

    useEffect(() => {
        if (!visible || !isActiveExecution(overview?.active_execution)) return () => {}
        const timer = window.setInterval(() => {
            void refreshAll({ preserveSelection: true })
        }, 3000)
        return () => window.clearInterval(timer)
    }, [visible, overview?.active_execution?.run_id, overview?.active_execution?.status])

    const activeExecution = overview?.active_execution || null
    const runs = Array.isArray(overview?.runs) ? overview.runs : []
    const lanes = Array.isArray(detail?.lanes) ? detail.lanes : []
    const failedSteps = []
    lanes.forEach((lane) => {
        ;(lane?.steps || []).forEach((step) => {
            if (step?.passed === false) {
                failedSteps.push({ laneName: lane?.name || '-', step })
            }
        })
    })

    return (
        <>
            <section className="panel full-span workbench-panel">
                <div className="task-item-header workbench-hero-header">
                    <div>
                        <div className="workbench-eyebrow">验证控制台</div>
                        <div className="panel-title">多子代理测试</div>
                        <div className="workbench-section-copy">
                            这里统一查看仓库级多子代理验证的启动状态、历史结果、失败分诊和日志入口。
                        </div>
                    </div>
                </div>
                <div className="task-row-actions workbench-inline-actions">
                    <button className="primary-button workbench-button" onClick={startVerification} disabled={busyKey === 'run' || isActiveExecution(activeExecution)}>
                        {busyKey === 'run' ? '启动中...' : '开始验证'}
                    </button>
                    <button className="secondary-button workbench-button" onClick={() => void refreshAll({ preserveSelection: true })}>
                        手动刷新
                    </button>
                </div>
                <ErrorNotice error={error} />
            </section>

            <section className="panel workbench-panel">
                <div className="panel-title">活动运行</div>
                {activeExecution ? (
                    <div className="summary-card workbench-card">
                        <div className="summary-card-title">{renderValue(activeExecution.run_id, '未分配运行编号')}</div>
                        <div className="summary-card-meta">{`状态：${renderValue(activeExecution.status)}`}</div>
                        <div className="summary-card-meta">{`开始时间：${renderValue(activeExecution.started_at)}`}</div>
                        <div className="summary-card-meta">{`产物目录：${renderValue(activeExecution.artifact_dir)}`}</div>
                    </div>
                ) : (
                    <div className="empty-state">当前没有正在运行的多子代理验证。</div>
                )}
            </section>

            <section className="panel workbench-panel">
                <div className="panel-title">历史运行</div>
                {runs.length ? (
                    <div className="summary-grid verification-run-list">
                        {runs.map((run) => (
                            <button
                                key={run.run_id}
                                type="button"
                                className={`summary-card workbench-card verification-run-card ${selectedRunId === run.run_id ? 'active' : ''}`}
                                onClick={() => setSelectedRunId(run.run_id)}
                            >
                                <div className="summary-card-title">{run.run_id}</div>
                                <div className="summary-card-meta">{`状态：${renderValue(run.status)}`}</div>
                                <div className="summary-card-meta">{`分类：${renderValue(run.classification, '未生成')}`}</div>
                                <div className="summary-card-meta">{`动作码：${renderValue(run.next_action, '待生成')}`}</div>
                            </button>
                        ))}
                    </div>
                ) : (
                    <div className="empty-state">还没有多子代理验证历史。</div>
                )}
            </section>

            <section className="panel full-span workbench-panel">
                <div className="panel-title">Verdict</div>
                <ErrorNotice error={detailError} />
                {detail ? (
                    <div className="summary-grid">
                        <div className="summary-card">
                            <div className="summary-card-title">最终分类</div>
                            <div className="summary-card-meta">{renderValue(detail.classification, '运行中或未完成')}</div>
                        </div>
                        <div className="summary-card">
                            <div className="summary-card-title">动作码</div>
                            <div className="summary-card-meta">{renderValue(detail.next_action, '待生成')}</div>
                        </div>
                        <div className="summary-card">
                            <div className="summary-card-title">失败摘要</div>
                            <div className="summary-card-meta">{renderValue(detail.failure_summary)}</div>
                        </div>
                        <div className="summary-card">
                            <div className="summary-card-title">最小复现</div>
                            <div className="summary-card-meta">{renderValue(detail.minimal_repro)}</div>
                        </div>
                    </div>
                ) : (
                    <div className="empty-state">请选择一个运行记录以查看详情。</div>
                )}
            </section>

            <section className="panel workbench-panel">
                <div className="panel-title">Local Lanes</div>
                {lanes.length ? (
                    <div className="summary-grid">
                        {lanes.map((lane) => (
                            <div key={lane.name} className="summary-card">
                                <div className="summary-card-title">{lane.name || '未命名 lane'}</div>
                                <div className="summary-card-meta">{`状态：${renderValue(lane.status)}`}</div>
                                <div className="summary-card-meta">{summarizeLaneFailure(lane)}</div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="empty-state">当前还没有本地 lane 结果。</div>
                )}
            </section>

            <section className="panel workbench-panel">
                <div className="panel-title">RealE2E</div>
                <div className="summary-card">
                    <div className="summary-card-title">{renderValue(detail?.real_e2e?.status, '待执行')}</div>
                    <div className="summary-card-meta">{`分类：${renderValue(detail?.real_e2e?.classification, '未生成')}`}</div>
                    <div className="summary-card-meta">{`产物目录：${renderValue(detail?.real_e2e?.artifact_dir)}`}</div>
                </div>
            </section>

            <section className="panel full-span workbench-panel">
                <div className="panel-title">Preflight</div>
                {detail?.preflight ? (
                    <div className="summary-grid">
                        <div className="summary-card">
                            <div className="summary-card-title">预检分类</div>
                            <div className="summary-card-meta">{renderValue(detail.preflight.classification)}</div>
                        </div>
                        <div className="summary-card">
                            <div className="summary-card-title">缺失路径</div>
                            <div className="summary-card-meta">{detail.preflight.missing_paths?.length || 0}</div>
                        </div>
                        <div className="summary-card">
                            <div className="summary-card-title">失败命令</div>
                            <div className="summary-card-meta">{detail.preflight.failed_commands?.length || 0}</div>
                        </div>
                    </div>
                ) : (
                    <div className="empty-state">当前没有可显示的预检结果。</div>
                )}
            </section>

            <section className="panel full-span workbench-panel">
                <div className="panel-title">Logs</div>
                <div className="task-row-actions workbench-inline-actions">
                    <button
                        className="secondary-button workbench-button"
                        disabled={!detail?.artifacts?.report_url}
                        onClick={() => void loadText(detail?.artifacts?.report_url, '报告 report.md')}
                    >
                        查看报告
                    </button>
                    <button
                        className="secondary-button workbench-button"
                        disabled={!detail?.artifacts?.console_stdout_url}
                        onClick={() => void loadText(detail?.artifacts?.console_stdout_url, '控制台 stdout')}
                    >
                        控制台 stdout
                    </button>
                    <button
                        className="secondary-button workbench-button"
                        disabled={!detail?.artifacts?.console_stderr_url}
                        onClick={() => void loadText(detail?.artifacts?.console_stderr_url, '控制台 stderr')}
                    >
                        控制台 stderr
                    </button>
                </div>
                {failedSteps.length ? (
                    <div className="summary-grid verification-log-grid">
                        {failedSteps.map(({ laneName, step }) => (
                            <div key={`${laneName}:${step.id}`} className="summary-card">
                                <div className="summary-card-title">{`${laneName} / ${step.name || step.id}`}</div>
                                <div className="task-row-actions workbench-inline-actions">
                                    <button
                                        className="secondary-button workbench-button"
                                        disabled={!step.combined_log_url}
                                        onClick={() => void loadText(step.combined_log_url, `${step.id} combined`)}
                                    >
                                        查看 combined
                                    </button>
                                    <button
                                        className="secondary-button workbench-button"
                                        disabled={!step.stdout_log_url}
                                        onClick={() => void loadText(step.stdout_log_url, `${step.id} stdout`)}
                                    >
                                        查看 stdout
                                    </button>
                                    <button
                                        className="secondary-button workbench-button"
                                        disabled={!step.stderr_log_url}
                                        onClick={() => void loadText(step.stderr_log_url, `${step.id} stderr`)}
                                    >
                                        查看 stderr
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="empty-state">当前没有失败步骤日志可查看。</div>
                )}
                <ErrorNotice error={logError} />
                {logTitle ? (
                    <div className="summary-card verification-log-viewer">
                        <div className="summary-card-title">{logTitle}</div>
                        <pre>{logContent || '当前文件为空。'}</pre>
                    </div>
                ) : null}
            </section>
        </>
    )
}
