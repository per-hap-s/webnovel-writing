import { useEffect, useMemo, useState } from 'react'
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
    return `${failedStep.name || failedStep.id || '未命名步骤'} / ${renderValue(failedStep.failure_kind, '-')} / ${renderValue(failedStep.blocking_severity, '-')}`
}

export function WorkbenchVerificationPage({ visible }) {
    const [overview, setOverview] = useState(null)
    const [history, setHistory] = useState(null)
    const [detail, setDetail] = useState(null)
    const [selectedRunId, setSelectedRunId] = useState('')
    const [busyKey, setBusyKey] = useState('')
    const [error, setError] = useState(null)
    const [detailError, setDetailError] = useState(null)
    const [logError, setLogError] = useState(null)
    const [logTitle, setLogTitle] = useState('')
    const [logContent, setLogContent] = useState('')
    const [logMeta, setLogMeta] = useState(null)
    const [autoLogKey, setAutoLogKey] = useState('')

    const activeExecution = overview?.active_execution || null
    const runs = Array.isArray(overview?.runs) ? overview.runs : []
    const groups = Array.isArray(history?.groups) ? history.groups : []
    const lanes = Array.isArray(detail?.lanes) ? detail.lanes : []
    const failedSteps = useMemo(() => {
        const items = []
        lanes.forEach((lane) => {
            ;(lane?.steps || []).forEach((step) => {
                if (step?.passed === false) items.push({ laneName: lane?.name || '-', step })
            })
        })
        return items
    }, [lanes])

    async function loadOverview(options = {}) {
        const preserveSelection = options.preserveSelection === true
        const [overviewPayload, historyPayload] = await Promise.all([
            fetchJSON('/api/workbench/verification/overview', { limit: 10 }),
            fetchJSON('/api/workbench/verification/history', { limit: 20 }),
        ])
        setOverview(overviewPayload)
        setHistory(historyPayload)
        setError(null)
        const nextRunId = pickPreferredRunId(overviewPayload, preserveSelection ? selectedRunId : '')
        if (nextRunId) {
            setSelectedRunId(nextRunId)
        } else if (!preserveSelection) {
            setSelectedRunId('')
            setDetail(null)
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

    async function loadProgress(runId) {
        if (!runId) return
        try {
            const payload = await fetchJSON(`/api/workbench/verification/runs/${runId}/progress`)
            setOverview((current) => {
                if (!current?.active_execution || current.active_execution.run_id !== runId) return current
                return {
                    ...current,
                    active_execution: {
                        ...current.active_execution,
                        progress: payload,
                    },
                }
            })
            setDetail((current) => (current?.run_id === runId ? { ...current, progress: payload } : current))
        } catch (requestError) {
            setError(normalizeError(requestError))
        }
    }

    async function refreshAll(options = {}) {
        try {
            await loadOverview(options)
        } catch (requestError) {
            setError(normalizeError(requestError))
        }
    }

    async function startVerification() {
        setBusyKey('run')
        try {
            const payload = await postJSON('/api/workbench/verification/run', {})
            setOverview((current) => ({
                ...(current || {}),
                active_execution: payload.execution,
                runs: current?.runs || [],
            }))
            setSelectedRunId(payload?.execution?.run_id || '')
            await refreshAll({ preserveSelection: true })
        } catch (requestError) {
            setError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    async function stopVerification() {
        setBusyKey('stop')
        try {
            const payload = await postJSON('/api/workbench/verification/run/stop', {})
            setOverview((current) => ({
                ...(current || {}),
                active_execution: payload.execution,
                runs: current?.runs || [],
            }))
            await refreshAll({ preserveSelection: true })
            await loadDetail(selectedRunId || payload?.execution?.run_id || '')
        } catch (requestError) {
            setError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    async function rerunSelected() {
        if (!selectedRunId) return
        setBusyKey('rerun')
        try {
            const payload = await postJSON(`/api/workbench/verification/runs/${selectedRunId}/rerun`, {})
            setSelectedRunId(payload?.execution?.run_id || selectedRunId)
            await refreshAll({ preserveSelection: true })
        } catch (requestError) {
            setError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    async function copyMinimalRepro() {
        const value = String(detail?.minimal_repro || '').trim()
        if (!value || !window.navigator?.clipboard?.writeText) return
        await window.navigator.clipboard.writeText(value)
    }

    async function loadLog(url, title) {
        if (!url) return
        setBusyKey(title)
        setLogError(null)
        try {
            const payload = await fetchJSON(url, { tail_lines: 200 })
            setLogTitle(title)
            setLogContent(payload?.content || '')
            setLogMeta(payload)
        } catch (requestError) {
            setLogError(normalizeError(requestError))
        } finally {
            setBusyKey('')
        }
    }

    async function loadReport(url, title) {
        if (!url) return
        setBusyKey(title)
        setLogError(null)
        try {
            const text = await fetchText(url)
            setLogTitle(title)
            setLogContent(text)
            setLogMeta(null)
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
        setLogTitle('')
        setLogContent('')
        setLogMeta(null)
        setLogError(null)
        setAutoLogKey('')
    }, [detail?.run_id])

    useEffect(() => {
        if (!visible || !detail?.run_id) return
        const firstFailedStep = failedSteps[0]?.step || null
        const combinedLogUrl = String(firstFailedStep?.combined_log_url || '').trim()
        const stepId = String(firstFailedStep?.id || '').trim()
        if (!combinedLogUrl || !stepId) return
        const nextKey = `${detail.run_id}:${stepId}:combined`
        if (autoLogKey === nextKey) return
        setAutoLogKey(nextKey)
        void loadLog(combinedLogUrl, `${stepId} combined`)
    }, [visible, detail?.run_id, failedSteps, autoLogKey])

    useEffect(() => {
        if (!visible || !isActiveExecution(activeExecution)) return () => {}
        const progressTimer = window.setInterval(() => {
            void loadProgress(activeExecution.run_id)
        }, 3000)
        const overviewTimer = window.setInterval(() => {
            void refreshAll({ preserveSelection: true })
        }, 15000)
        return () => {
            window.clearInterval(progressTimer)
            window.clearInterval(overviewTimer)
        }
    }, [visible, activeExecution?.run_id, activeExecution?.status])

    return (
        <>
            <section className="panel full-span workbench-panel">
                <div className="task-item-header workbench-hero-header">
                    <div>
                        <div className="workbench-eyebrow">验证控制台</div>
                        <div className="panel-title">多子代理测试</div>
                        <div className="workbench-section-copy">这里统一查看仓库级多子代理验证的启动状态、历史结果、失败分诊和日志入口。</div>
                    </div>
                </div>
                <div className="task-row-actions workbench-inline-actions">
                    <button className="primary-button workbench-button" onClick={startVerification} disabled={busyKey === 'run' || isActiveExecution(activeExecution)}>开始验证</button>
                    <button className="secondary-button workbench-button" onClick={stopVerification} disabled={busyKey === 'stop' || !isActiveExecution(activeExecution)}>停止验证</button>
                    <button className="secondary-button workbench-button" onClick={() => void refreshAll({ preserveSelection: true })}>手动刷新</button>
                </div>
                <ErrorNotice error={error} />
            </section>

            <section className="panel workbench-panel">
                <div className="panel-title">活动运行</div>
                {activeExecution ? (
                    <div className="summary-card workbench-card">
                        <div className="summary-card-title">{renderValue(activeExecution.run_id, '未分配运行编号')}</div>
                        <div className="summary-card-meta">{`状态：${renderValue(activeExecution.status)}`}</div>
                        <div className="summary-card-meta">{`阶段：${renderValue(activeExecution?.progress?.phase)}`}</div>
                        <div className="summary-card-meta">{`当前 lane：${renderValue(activeExecution?.progress?.current_lane)}`}</div>
                        <div className="summary-card-meta">{`当前步骤：${renderValue(activeExecution?.progress?.current_step_id)}`}</div>
                        <div className="summary-card-meta">{`进度：${renderValue(activeExecution?.progress?.completed_steps, 0)} / ${renderValue(activeExecution?.progress?.total_steps, 0)}`}</div>
                        <div className="summary-card-meta">{`更新时间：${renderValue(activeExecution?.progress?.updated_at)}`}</div>
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
                            <button key={run.run_id} type="button" className={`summary-card workbench-card verification-run-card ${selectedRunId === run.run_id ? 'active' : ''}`} onClick={() => setSelectedRunId(run.run_id)}>
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
                <div className="panel-title">历史分组</div>
                {groups.length ? (
                    <div className="summary-grid verification-history-groups">
                        {groups.map((group) => (
                            <div key={group.failure_fingerprint} className="summary-card">
                                <div className="summary-card-title">{group.failure_fingerprint}</div>
                                <div className="summary-card-meta">{`出现次数：${renderValue(group.run_count, 0)}`}</div>
                                <div className="summary-card-meta">{`最近运行：${renderValue(group.latest_run_id)}`}</div>
                                <div className="summary-card-meta">{`最近分类：${renderValue(group.latest_classification)}`}</div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="empty-state">当前没有可分组的失败指纹。</div>
                )}
            </section>

            <section className="panel full-span workbench-panel">
                <div className="panel-title">Verdict</div>
                <ErrorNotice error={detailError} />
                {detail ? (
                    <div className="summary-grid">
                        <div className="summary-card"><div className="summary-card-title">最终分类</div><div className="summary-card-meta">{renderValue(detail.classification, '运行中或未完成')}</div></div>
                        <div className="summary-card"><div className="summary-card-title">动作码</div><div className="summary-card-meta">{renderValue(detail.next_action, '待生成')}</div></div>
                        <div className="summary-card"><div className="summary-card-title">失败摘要</div><div className="summary-card-meta">{renderValue(detail.failure_summary)}</div></div>
                        <div className="summary-card"><div className="summary-card-title">最小复现</div><div className="summary-card-meta">{renderValue(detail.minimal_repro)}</div></div>
                        <div className="summary-card"><div className="summary-card-title">失败指纹</div><div className="summary-card-meta">{renderValue(detail.failure_fingerprint)}</div></div>
                    </div>
                ) : (
                    <div className="empty-state">请选择一个运行记录以查看详情。</div>
                )}
                <div className="task-row-actions workbench-inline-actions">
                    <button className="secondary-button workbench-button" onClick={rerunSelected} disabled={busyKey === 'rerun' || !selectedRunId || isActiveExecution(activeExecution)}>重跑本次</button>
                    <button className="secondary-button workbench-button" onClick={() => void copyMinimalRepro()} disabled={!detail?.minimal_repro}>复制最小复现</button>
                </div>
            </section>

            <section className="panel workbench-panel">
                <div className="panel-title">当前阶段</div>
                {detail?.progress ? (
                    <div className="summary-card">
                        <div className="summary-card-title">{renderValue(detail.progress.phase)}</div>
                        <div className="summary-card-meta">{`当前 lane：${renderValue(detail.progress.current_lane)}`}</div>
                        <div className="summary-card-meta">{`当前步骤：${renderValue(detail.progress.current_step_id)}`}</div>
                        <div className="summary-card-meta">{`进度：${renderValue(detail.progress.completed_steps, 0)} / ${renderValue(detail.progress.total_steps, 0)}`}</div>
                    </div>
                ) : (
                    <div className="empty-state">当前没有可显示的运行进度。</div>
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
                        <div className="summary-card"><div className="summary-card-title">预检分类</div><div className="summary-card-meta">{renderValue(detail.preflight.classification)}</div></div>
                        <div className="summary-card"><div className="summary-card-title">缺失路径</div><div className="summary-card-meta">{detail.preflight.missing_paths?.length || 0}</div></div>
                        <div className="summary-card"><div className="summary-card-title">失败命令</div><div className="summary-card-meta">{detail.preflight.failed_commands?.length || 0}</div></div>
                    </div>
                ) : (
                    <div className="empty-state">当前没有可显示的预检结果。</div>
                )}
            </section>

            <section className="panel full-span workbench-panel">
                <div className="panel-title">Logs</div>
                <div className="task-row-actions workbench-inline-actions">
                    <button className="secondary-button workbench-button" disabled={!detail?.artifacts?.report_url} onClick={() => void loadReport(detail?.artifacts?.report_url, '报告 report.md')}>查看报告</button>
                    <button className="secondary-button workbench-button" disabled={!detail?.artifacts?.console_stdout_url} onClick={() => void loadLog(detail?.artifacts?.console_stdout_url, '控制台 stdout')}>控制台 stdout</button>
                    <button className="secondary-button workbench-button" disabled={!detail?.artifacts?.console_stderr_url} onClick={() => void loadLog(detail?.artifacts?.console_stderr_url, '控制台 stderr')}>控制台 stderr</button>
                </div>
                {failedSteps.length ? (
                    <div className="summary-grid verification-log-grid">
                        {failedSteps.map(({ laneName, step }) => (
                            <div key={`${laneName}:${step.id}`} className="summary-card">
                                <div className="summary-card-title">{`${laneName} / ${step.name || step.id}`}</div>
                                <div className="task-row-actions workbench-inline-actions">
                                    <button className="secondary-button workbench-button" disabled={!step.combined_log_url} onClick={() => void loadLog(step.combined_log_url, `${step.id} combined`)}>查看 combined</button>
                                    <button className="secondary-button workbench-button" disabled={!step.stdout_log_url} onClick={() => void loadLog(step.stdout_log_url, `${step.id} stdout`)}>查看 stdout</button>
                                    <button className="secondary-button workbench-button" disabled={!step.stderr_log_url} onClick={() => void loadLog(step.stderr_log_url, `${step.id} stderr`)}>查看 stderr</button>
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
                        {logMeta ? <div className="summary-card-meta">{`truncated=${String(logMeta.truncated)} / bytes=${renderValue(logMeta.total_bytes, 0)}`}</div> : null}
                        <pre>{logContent || '当前文件为空。'}</pre>
                    </div>
                ) : null}
            </section>
        </>
    )
}
