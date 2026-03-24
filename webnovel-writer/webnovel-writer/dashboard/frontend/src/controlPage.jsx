import { useMemo, useState } from 'react'
import { normalizeError, postJSON } from './api.js'
import { executeOperatorAction as executeRuntimeOperatorAction } from './operatorActionRuntime.js'
import { MetricCard, resolveTaskStatusLabel, resolveTaskTargetLabel, translateTaskType } from './dashboardPageCommon.jsx'
import {
    ApiSettingsSection,
    PlanningProfileSection,
    ProjectBootstrapSection,
    TaskLauncherSection,
} from './appSections.jsx'
import { ErrorNotice } from './sectionCommon.jsx'
import { buildWritingTaskListSummary, supportsWritingTaskContinuation } from './writingTaskListSummary.js'

const MODE_OPTIONS = [
    { value: 'standard', label: '标准' },
    { value: 'fast', label: '快速' },
    { value: 'minimal', label: '精简' },
]

const TASK_TEMPLATES = [
    { key: 'init', title: '补齐旧项目骨架', fields: ['project_root'] },
    { key: 'plan', title: '创建多章规划', fields: ['volume', 'mode'] },
    { key: 'write', title: '撰写章节', fields: ['chapter', 'mode', 'require_manual_approval'] },
    { key: 'guarded-write', title: '护栏推进单章', fields: ['chapter', 'mode', 'require_manual_approval'] },
    { key: 'guarded-batch-write', title: '护栏批量推进', fields: ['start_chapter', 'max_chapters', 'mode', 'require_manual_approval'] },
    { key: 'review', title: '执行审查', fields: ['chapter_range', 'mode'] },
    { key: 'resume', title: '恢复任务', fields: ['mode'] },
]

const UI_COPY = {
    overviewPlanningTitle: '规划必填信息',
    projectCreateHint: '启动后会先进入项目工作台。你可以在这里打开已有项目，或创建新的创作项目。',
    taskEntryHint: '主线任务建议按“多章规划 -> 撰写章节 -> 执行审查 / 恢复任务”的顺序使用；“补齐旧项目骨架”只用于兼容旧项目。',
    planningHint: '先补齐这里的规划信息，再运行“多章规划”。如果信息不足，系统会提示你回到这里继续补资料。',
    writingEngine: '写作引擎',
    retrievalEngine: '检索引擎',
    overviewMainlineTitle: '主线任务',
    overviewMainlineEmpty: '暂时没有可展示的主线任务。创建写作、护栏推进或恢复任务后，这里会显示推荐动作。',
    viewTask: '查看任务',
    suggestedNextStep: '建议下一步',
}

export function ControlPage({ projectInfo, directorHub, directorHubError, llmStatus, ragStatus, tasks, bootstrapHint, onTaskCreated, onProjectBootstrapped, onApiSettingsSaved, onOpenTask, onTasksMutated, onPlanningProfileSaved }) {
    const projectMeta = projectInfo?.project_info || projectInfo || {}
    const dashboardContext = projectInfo?.dashboard_context || {}
    const [submittingActionKey, setSubmittingActionKey] = useState('')
    const [actionError, setActionError] = useState(null)

    const writingTaskCards = useMemo(() => (
        (tasks || [])
            .filter((task) => supportsWritingTaskContinuation(task))
            .sort(compareTaskFreshness)
            .slice(0, 3)
            .map((task) => ({
                task,
                summary: buildWritingTaskListSummary({ task }),
            }))
            .filter((item) => item.summary)
    ), [tasks])

    async function executeOverviewAction(action) {
        if (!action || action.disabled || action.kind === 'complete-noop') return
        const actionKey = action.id || `${action.kind}:${action.taskId || action.taskType || action.label}`
        setActionError(null)
        setSubmittingActionKey(actionKey)
        try {
            await executeRuntimeOperatorAction({
                action,
                postJSON,
                onOpenTask,
                onTasksMutated: () => onTasksMutated?.(),
                onTaskCreated: (response) => {
                    if (response?.id) {
                        onTaskCreated?.(response)
                        return
                    }
                    onTasksMutated?.()
                },
            })
        } catch (err) {
            setActionError(normalizeError(err))
        } finally {
            setSubmittingActionKey('')
        }
    }

    return (
        <div className="page-grid">
            <section className="panel hero-panel">
                <div className="panel-title">项目总览</div>
                <div className="metric-grid">
                    <MetricCard label="总字数" value={formatNumber(projectInfo?.progress?.total_words || 0)} />
                    <MetricCard label="当前章节" value={`第 ${projectInfo?.progress?.current_chapter || 0} 章`} />
                    <MetricCard label="题材" value={projectMeta?.genre || '未知'} />
                    <MetricCard label={UI_COPY.writingEngine} value={formatWritingModelDetail(llmStatus)} />
                    <MetricCard label={UI_COPY.retrievalEngine} value={formatRagDetail(ragStatus)} />
                </div>
                {(ragStatus?.connection_status === 'failed' || ragStatus?.last_error) && (
                    <div className="empty-state">{`${UI_COPY.retrievalEngine}最近错误：${formatRagErrorSummary(ragStatus.connection_error || ragStatus.last_error)}`}</div>
                )}
            </section>

            <DirectorHubPanel directorHub={directorHub} error={directorHubError} />

            <section className="panel">
                <div className="panel-title">项目创建</div>
                <div className="empty-state">{UI_COPY.projectCreateHint}</div>
                <div className="launcher-grid">
                    <ProjectBootstrapSection
                        currentProjectRoot={dashboardContext.project_root || ''}
                        currentTitle={projectMeta?.title || projectMeta?.project_name || dashboardContext?.title || ''}
                        currentGenre={projectMeta?.genre || dashboardContext?.genre || ''}
                        projectInitialized={Boolean(dashboardContext.project_initialized)}
                        onSuccess={onProjectBootstrapped}
                    />
                </div>
            </section>

            <section className="panel">
                <div className="panel-title">任务入口</div>
                <div className="empty-state">{UI_COPY.taskEntryHint}</div>
                <div className="launcher-grid">
                    {TASK_TEMPLATES.map((template) => (
                        <TaskLauncherSection
                            key={template.key}
                            template={template}
                            onCreated={onTaskCreated}
                            MODE_OPTIONS={MODE_OPTIONS}
                            suggestedChapter={Math.max(1, Number(projectInfo?.progress?.current_chapter || 0) + 1)}
                        />
                    ))}
                </div>
            </section>

            <section className="panel full-span">
                <div className="panel-title">{UI_COPY.overviewMainlineTitle}</div>
                <ErrorNotice error={actionError} />
                {writingTaskCards.length === 0 ? (
                    <div className="empty-state">{UI_COPY.overviewMainlineEmpty}</div>
                ) : (
                    <div className="summary-grid">
                        {writingTaskCards.map(({ task, summary }) => (
                            <WritingTaskOverviewCard
                                key={task.id}
                                task={task}
                                summary={summary}
                                submitting={Boolean(summary.primaryAction && submittingActionKey === (summary.primaryAction.id || `${summary.primaryAction.kind}:${summary.primaryAction.taskId || summary.primaryAction.taskType || summary.primaryAction.label}`))}
                                onOpenTask={onOpenTask}
                                onAction={executeOverviewAction}
                            />
                        ))}
                    </div>
                )}
            </section>

            <section className="panel full-span">
                <div className="panel-title">{UI_COPY.overviewPlanningTitle}</div>
                {bootstrapHint === 'planning' ? (
                    <div className="planning-warning subtle">
                        <div className="subsection-title">下一步建议</div>
                        <div className="tiny">项目已初始化。下一步先确认并保存规划信息，再运行“多章规划”。不需要先手工修改总纲。</div>
                    </div>
                ) : null}
                <div className="empty-state">{UI_COPY.planningHint}</div>
                <PlanningProfileSection onSaved={() => onPlanningProfileSaved?.()} />
            </section>

            <section className="panel full-span">
                <div className="panel-title">API 接入设置</div>
                <div className="empty-state">在这里填写写作模型和检索接口配置。保存后会写入项目根目录的 `.env`，并立即刷新当前面板状态。</div>
                <ApiSettingsSection llmStatus={llmStatus} ragStatus={ragStatus} onSaved={() => onApiSettingsSaved?.()} />
            </section>
        </div>
    )
}

function WritingTaskOverviewCard({ task, summary, submitting, onOpenTask, onAction }) {
    const recommendedLabel = summary.primaryActionLabel || summary.nextStep || UI_COPY.viewTask

    return (
        <div className="summary-card">
            <div className="task-item-header">
                <div className="summary-card-title">{translateTaskType(task.task_type)}</div>
                <span className={`runtime-badge ${mapContinuationToneToBadgeTone(summary.tone)}`}>{summary.continuationLabel}</span>
            </div>
            <div className="tiny task-target">{resolveTaskTargetLabel(task)}</div>
            <div className="summary-card-meta">{resolveTaskStatusLabel(task)}</div>
            <div className="summary-card-meta">{summary.reasonLabel}</div>
            <div className="summary-card-meta">{`${UI_COPY.suggestedNextStep}：${recommendedLabel}`}</div>
            <div className="button-row">
                <button className="secondary-button" onClick={() => onOpenTask(task.id)}>
                    {UI_COPY.viewTask}
                </button>
                <button
                    className={summary.primaryAction ? 'primary-button' : 'secondary-button'}
                    onClick={() => summary.primaryAction && onAction(summary.primaryAction)}
                    disabled={!summary.primaryAction || submitting || summary.primaryAction.disabled}
                    title={summary.primaryAction ? (summary.primaryAction.reason || summary.primaryAction.label) : '当前任务暂时没有可执行的下一步'}
                >
                    {submitting ? '处理中...' : (summary.primaryActionLabel || '执行下一步')}
                </button>
            </div>
        </div>
    )
}

function DirectorHubPanel({ directorHub, error }) {
    const currentBrief = directorHub?.current_brief || {}
    const storyPlan = directorHub?.story_plan || {}
    const continuity = directorHub?.continuity || {}
    const voiceBible = directorHub?.voice_bible || {}
    const chapterBeats = Array.isArray(storyPlan?.chapters) ? storyPlan.chapters.slice(0, 3) : []
    const activeThreads = mapDirectorItems(continuity?.plot_threads, (item) => item?.title || item?.name)
    const mysteryItems = mapDirectorItems(continuity?.mystery_ledger, (item) => item?.name || item?.title)
    const ruleItems = mapDirectorItems(continuity?.rule_assertions, (item) => item?.name || item?.title)
    const trustItems = mapTrustItems(continuity?.trust_map)
    const decisionItems = mapDirectorItems(continuity?.director_decisions, (item) => {
        const chapter = Number(item?.chapter || 0)
        const goal = trimText(item?.chapter_goal)
        if (chapter > 0 && goal) return `第 ${chapter} 章 / ${goal}`
        if (chapter > 0) return `第 ${chapter} 章指挥决策`
        return goal
    })
    const voiceItems = mapVoiceBibleItems(voiceBible)
    const currentChapter = Number(directorHub?.current_chapter || currentBrief?.chapter || 0)

    return (
        <section className="panel full-span">
            <div className="panel-title">创作指挥台</div>
            {error ? (
                <div className="planning-warning subtle">
                    <div className="subsection-title">创作指挥台暂时无法刷新，请稍后重试。</div>
                    <div className="tiny">接口未返回有效数据。项目总览其他区域仍可继续使用。</div>
                </div>
            ) : null}
            {!error && !directorHub ? <div className="empty-state">当前还没有可展示的创作指挥台数据。</div> : null}
            {!directorHub || error ? null : (
                <>
                    <div className="director-hub-topline">
                        <span className="runtime-badge info">{`当前准备章节：${currentChapter > 0 ? `第 ${currentChapter} 章` : '未确定'}`}</span>
                        <span className="runtime-badge muted">{`活跃线索 ${activeThreads.length}`}</span>
                        <span className="runtime-badge muted">{`谜团 ${mysteryItems.length}`}</span>
                        <span className="runtime-badge muted">{`规则 ${ruleItems.length}`}</span>
                    </div>
                    <div className="director-hub-grid">
                        <section className="director-hub-card">
                            <div className="subsection-title">章节简报</div>
                            {currentBrief && Object.keys(currentBrief).length ? (
                                <>
                                    <div className="director-hub-kv">
                                        <div><strong>本章目标：</strong>{trimText(currentBrief.chapter_goal) || '未生成'}</div>
                                        <div><strong>核心冲突：</strong>{trimText(currentBrief.primary_conflict) || '未生成'}</div>
                                        <div><strong>揭示上限：</strong>{trimText(currentBrief.allowed_reveal_ceiling) || '未设定'}</div>
                                        <div><strong>章末钩子：</strong>{trimText(currentBrief.ending_hook_target) || '未设定'}</div>
                                    </div>
                                    <DirectorChipGroup title="必须推进" items={currentBrief.must_advance_threads} emptyText="暂未指定必须推进的线索" />
                                    <DirectorChipGroup title="必须压住的信息" items={currentBrief.must_hold_back_facts} emptyText="暂时没有需要压住的事实" />
                                    <DirectorChipGroup title="人物声线约束" items={currentBrief.voice_constraints} emptyText="暂时没有声线约束" />
                                    <DirectorChipGroup title="禁用术语" items={currentBrief.forbidden_terms} emptyText="暂时没有禁用术语" />
                                </>
                            ) : (
                                <div className="empty-state">当前还没有可展示的章节简报。</div>
                            )}
                        </section>
                        <section className="director-hub-card">
                            <div className="subsection-title">多章规划摘要</div>
                            {storyPlan && Object.keys(storyPlan).length ? (
                                <>
                                    <div className="director-hub-kv">
                                        <div><strong>锚点章节：</strong>{Number(storyPlan.anchor_chapter || 0) || '-'}</div>
                                        <div><strong>规划跨度：</strong>{Number(storyPlan.planning_horizon || 0) || '-'}</div>
                                        <div><strong>规划理由：</strong>{trimText(storyPlan.rationale) || '未提供'}</div>
                                    </div>
                                    <DirectorChipGroup title="优先线索" items={storyPlan.priority_threads} emptyText="暂时没有优先线索" />
                                    <div className="director-mini-list">
                                        {chapterBeats.length ? chapterBeats.map((beat) => (
                                            <div key={`beat-${beat.chapter || beat.chapter_goal}`} className="director-mini-card">
                                                <div className="director-mini-title">{`第 ${Number(beat.chapter || 0) || '-'} 章`}</div>
                                                <div className="tiny">{trimText(beat.chapter_goal) || '未填写章节目标'}</div>
                                                <div className="tiny">{`章末钩子：${trimText(beat.ending_hook_target) || '未填写'}`}</div>
                                            </div>
                                        )) : <div className="empty-state">当前还没有可展示的章节节拍。</div>}
                                    </div>
                                </>
                            ) : (
                                <div className="empty-state">当前还没有可展示的多章规划摘要。</div>
                            )}
                        </section>
                        <section className="director-hub-card">
                            <div className="subsection-title">连续性账本</div>
                            <DirectorChipGroup title="活跃线索" items={activeThreads} emptyText="暂时没有活跃线索" />
                            <DirectorChipGroup title="未回收谜团" items={mysteryItems} emptyText="暂时没有待压住的谜团" />
                            <DirectorChipGroup title="已坐实规则" items={ruleItems} emptyText="暂时没有已坐实规则" />
                            <DirectorChipGroup title="关系变化" items={trustItems} emptyText="暂时没有关系变化" />
                            <DirectorChipGroup title="最近指挥决策" items={decisionItems} emptyText="暂时没有指挥决策记录" />
                        </section>
                        <section className="director-hub-card">
                            <div className="subsection-title">人物声线卡</div>
                            <DirectorChipGroup title="声线摘要" items={voiceItems} emptyText="当前还没有结构化声线约束。" />
                        </section>
                    </div>
                </>
            )}
        </section>
    )
}

function DirectorChipGroup({ title, items, emptyText }) {
    const values = coerceUniqueTextList(items)
    return (
        <div className="director-chip-group">
            <div className="tiny director-chip-group-title">{title}</div>
            {values.length ? (
                <div className="planning-tags">
                    {values.map((item) => (
                        <span key={`${title}-${item}`} className="planning-tag director-tag">{item}</span>
                    ))}
                </div>
            ) : (
                <div className="tiny">{emptyText}</div>
            )}
        </div>
    )
}

function compareTaskFreshness(left, right) {
    return String(right?.updated_at || right?.created_at || '').localeCompare(String(left?.updated_at || left?.created_at || ''))
}

function formatNumber(value) {
    return new Intl.NumberFormat('zh-CN').format(Number(value || 0))
}

function mapContinuationToneToBadgeTone(tone) {
    if (tone === 'critical') return 'danger'
    if (tone === 'warning') return 'warning'
    if (tone === 'success') return 'success'
    return 'info'
}

function trimText(value) {
    return localizeUserFacingText(String(value || '').trim())
}

function localizeUserFacingText(value) {
    let text = String(value || '').trim()
    if (!text) return ''

    const exactRewrites = [
        [
            /^This story plan uses active foreshadowing, knowledge conflicts and hooks to keep the rain archive line under pressure\.?$/i,
            '当前多章规划会根据活跃伏笔、知识冲突与最近指挥结果生成，用于持续给雨档案线施压。',
        ],
        [
            /^当前 story plan 根据 active foreshadowing、knowledge conflicts、最近导演执行结果生成，用于稳定未来几章的推进顺序。本轮仍以当前大纲切片为硬约束。?$/i,
            '当前多章规划会根据活跃伏笔、知识冲突与最近指挥结果生成，用于稳定未来几章的推进顺序。本轮仍以当前大纲切片为硬约束。',
        ],
    ]

    for (const [pattern, replacement] of exactRewrites) {
        if (pattern.test(text)) return replacement
    }

    return text
}

function mapDirectorItems(items, resolver) {
    const source = Array.isArray(items) ? items : []
    return source.map((item) => trimText(resolver(item))).filter(Boolean)
}

function mapTrustItems(trustMap) {
    return Object.entries(trustMap || {}).slice(0, 6).map(([key, entry]) => {
        const label = trimText(entry?.status)
        const chapter = Number(entry?.chapter || 0)
        if (label && chapter > 0) return `${key} / ${label} / 第 ${chapter} 章`
        if (label) return `${key} / ${label}`
        return key
    })
}

function mapVoiceBibleItems(voiceBible) {
    const characters = voiceBible?.characters || {}
    return Object.entries(characters)
        .slice(0, 6)
        .map(([name, entry]) => {
            const constraints = coerceUniqueTextList(entry?.constraints)
            const notes = coerceUniqueTextList(entry?.notes)
            const detail = constraints[0] || notes[0] || trimText(entry?.arc_stage)
            return detail ? `${name} / ${detail}` : name
        })
}

function coerceUniqueTextList(items) {
    const source = Array.isArray(items) ? items : (items ? [items] : [])
    const seen = new Set()
    const values = []
    source.forEach((item) => {
        const text = trimText(item)
        if (!text) return
        const key = text.toLowerCase()
        if (seen.has(key)) return
        seen.add(key)
        values.push(text)
    })
    return values
}

function getWritingModelTone(llmStatus) {
    if (!llmStatus) return 'warning'
    const status = llmStatus.effective_status || llmStatus.connection_status
    if (status === 'connected') return 'good'
    if (status === 'degraded') return 'warning'
    return 'danger'
}

function formatWritingModelDetail(llmStatus) {
    const tone = getWritingModelTone(llmStatus)
    if (tone === 'good') return llmStatus.model || '已连接'
    if (tone === 'warning') return '探活异常'
    return '未连接'
}

function formatRagDetail(ragStatus) {
    const status = ragStatus?.effective_status || ragStatus?.connection_status
    if (status === 'connected') return ragStatus?.embed_model || '已连接'
    if (status === 'degraded') return '探活异常'
    if (status === 'failed') return '连接失败'
    return '未连接'
}

function formatRagErrorSummary(error) {
    if (!error) return '未知错误'
    if (typeof error === 'string') return error
    return error.message || error.code || '未知错误'
}
