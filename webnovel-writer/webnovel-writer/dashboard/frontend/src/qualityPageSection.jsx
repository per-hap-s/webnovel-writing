import { useEffect, useState } from 'react'
import { fetchJSON, normalizeError, postJSON } from './api.js'
import { CompactEmptyCard, ErrorNotice } from './sectionCommon.jsx'

const QUALITY_PAGE_COPY = {
    invalidFactsEmptyTitle: '暂无待处理失效事实',
    invalidFactsEmptyDescription: '当审查发现需要冻结或确认的失效事实时，这里会出现审批项。',
    reviewMetricsEmptyTitle: '暂无审查指标',
    reviewMetricsEmptyDescription: '运行审查任务后，这里会汇总各章节的评分。',
    checklistScoresEmptyTitle: '暂无清单评分',
    checklistScoresEmptyDescription: '当写作清单被执行后，这里会显示完成率与得分。',
    ragQueriesEmptyTitle: '暂无检索记录',
    ragQueriesEmptyDescription: '发生检索调用后，这里会显示查询类型、结果数和延迟。',
    toolStatsEmptyTitle: '暂无工具统计',
    toolStatsEmptyDescription: '工具链开始写入运行记录后，这里会显示调用次数和重试情况。',
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
                    {invalidFacts.length === 0 && <CompactEmptyCard title={QUALITY_PAGE_COPY.invalidFactsEmptyTitle} description={QUALITY_PAGE_COPY.invalidFactsEmptyDescription} />}
                </div>
            </section>
            <section className="panel">
                <div className="panel-title">审查指标</div>
                {reviewMetrics.length ? <SimpleTable rows={reviewMetrics} columns={['end_chapter', 'overall_score', 'created_at']} /> : <CompactEmptyCard title={QUALITY_PAGE_COPY.reviewMetricsEmptyTitle} description={QUALITY_PAGE_COPY.reviewMetricsEmptyDescription} />}
            </section>
            <section className="panel">
                <div className="panel-title">清单评分</div>
                {checklistScores.length ? <SimpleTable rows={checklistScores} columns={['chapter', 'template', 'score', 'completion_rate']} /> : <CompactEmptyCard title={QUALITY_PAGE_COPY.checklistScoresEmptyTitle} description={QUALITY_PAGE_COPY.checklistScoresEmptyDescription} />}
            </section>
            <section className="panel">
                <div className="panel-title">RAG 查询</div>
                {ragQueries.length ? <SimpleTable rows={ragQueries} columns={['query_type', 'query', 'results_count', 'latency_ms']} /> : <CompactEmptyCard title={QUALITY_PAGE_COPY.ragQueriesEmptyTitle} description={QUALITY_PAGE_COPY.ragQueriesEmptyDescription} />}
            </section>
            <section className="panel">
                <div className="panel-title">工具统计</div>
                {toolStats.length ? <SimpleTable rows={toolStats} columns={['tool_name', 'success', 'retry_count', 'created_at']} /> : <CompactEmptyCard title={QUALITY_PAGE_COPY.toolStatsEmptyTitle} description={QUALITY_PAGE_COPY.toolStatsEmptyDescription} />}
            </section>
        </div>
    )
}
