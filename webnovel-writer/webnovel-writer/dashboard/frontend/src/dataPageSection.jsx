import { useEffect, useState } from 'react'
import { fetchJSON } from './api.js'
import { formatTimestampShort } from './dashboardPageCommon.jsx'

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
                <div className="panel-title">多章规划摘要</div>
                {storyPlans.length === 0 ? (
                    <div className="tiny">当前还没有可展示的多章滚动规划；请先运行带“多章规划”的写作任务。</div>
                ) : (
                    <div className="summary-grid">
                        {storyPlans.map((plan) => (
                            <div key={plan.path || plan.anchor_chapter} className="summary-card">
                                <div className="summary-card-title">锚点第 {plan.anchor_chapter} 章</div>
                                <div className="tiny">窗口 {plan.planning_horizon || '-'} 章 · 更新时间 {formatTimestampShort(plan.updated_at_display || plan.updated_at || '-')}</div>
                                <div className="summary-card-meta">当前定位：{translatePlanRole(plan.current_role)}</div>
                                <div className="summary-card-meta">本轮目标：{plan.current_goal || '-'}</div>
                                <div className="summary-card-meta">章末钩子：{plan.current_hook || '-'}</div>
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

function translatePlanRole(value) {
    const text = String(value || '').trim()
    if (!text) return '未设置'
    if (text === 'current-execution') return '当前执行'
    if (text === 'progression') return '主线推进'
    if (text === 'setup') return '铺垫'
    if (text === 'payoff') return '兑现'
    if (text === 'transition') return '过渡'
    return text
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
