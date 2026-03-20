const TASK_TYPE_LABELS = {
    init: '旧初始化',
    plan: '规划卷',
    write: '撰写章节',
    'guarded-write': '护栏推进',
    'guarded-batch-write': '护栏批量推进',
    review: '执行审查',
    resume: '恢复任务',
}

const STATUS_LABELS = {
    queued: '已排队',
    running: '运行中',
    awaiting_writeback_approval: '等待回写审批',
    completed: '已完成',
    failed: '失败',
    interrupted: '已中断',
    rejected: '已拒绝',
}

const APPROVAL_STATUS_LABELS = {
    not_required: '无需审批',
    pending: '待批准回写',
    approved: '已批准',
    rejected: '已拒绝',
}

const STEP_LABELS = {
    init: '初始化',
    plan: '规划',
    resume: '恢复',
    'guarded-chapter-runner': '护栏推进一章',
    'guarded-batch-runner': '护栏批量推进',
    'story-director': '多章叙事规划',
    'chapter-director': '单章导演决策',
    context: '上下文准备',
    draft: '草稿生成',
    'consistency-review': '一致性审查',
    'continuity-review': '连续性审查',
    'ooc-review': '角色一致性审查',
    'review-summary': '审查汇总',
    polish: '润色',
    'approval-gate': '审批关卡',
    'data-sync': '数据同步',
    idle: '空闲',
}

const EVENT_LEVEL_LABELS = {
    info: '信息',
    warning: '警告',
    error: '错误',
}

const TABLE_HEADER_LABELS = {
    name: '名称',
    canonical_name: '标准名称',
    type: '类型',
    tier: '层级',
    last_appearance: '最后出现章节',
    from_entity: '起始实体',
    to_entity: '目标实体',
    from_entity_display: '起始实体',
    to_entity_display: '目标实体',
    type_label: '关系类型',
    chapter: '章节',
    title: '标题',
    location: '地点',
    word_count: '字数',
    end_chapter: '结束章节',
    overall_score: '总评分',
    created_at: '创建时间',
    template: '模板',
    score: '分数',
    completion_rate: '完成率',
    query_type: '查询类型',
    query: '查询内容',
    results_count: '结果数',
    latency_ms: '延迟(ms)',
    tool_name: '工具名',
    success: '成功',
    retry_count: '重试次数',
    source_type: '来源类型',
    source_id: '来源 ID',
    from_entity_name: '起始实体',
    to_entity_name: '目标实体',
    target_label: '任务目标',
}

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

const EXACT_EVENT_MESSAGES = {
    'Retry requested': '已请求重试',
    'Writeback approved': '已批准回写',
    'Writeback rejected': '已拒绝回写',
    'Rejected by operator': '已被操作人拒绝',
    'Schema validation failed': '结构校验失败',
    'Task completed': '任务已完成',
    'Story director prepared': '多章叙事规划已生成',
    'Chapter director prepared': '单章导演简报已生成',
    'Context story contract synced': '上下文已同步叙事导演合同',
    'Story plan refresh suggested': '建议重新生成滚动规划',
    'Guarded runner blocked by story refresh': '护栏推进因滚动规划刷新建议而停止',
    'Guarded runner child task created': '护栏推进已创建 write 子任务',
    'Guarded runner stopped at approval gate': '护栏推进在审批关卡停止',
    'Guarded runner blocked by review gate': '护栏推进被审查关卡拦截',
    'Guarded runner child task failed': '护栏推进子任务失败',
    'Guarded runner completed one chapter': '护栏推进已完成一章',
    'Guarded batch child task created': '护栏批量推进已创建子任务',
    'Guarded batch stopped by child outcome': '护栏批量推进因子任务结果而停止',
    'Guarded batch child task failed': '护栏批量推进子任务失败',
    'Guarded batch completed requested chapters': '护栏批量推进已完成请求章数',
    'Review summary persisted': '审查汇总已写入',
    'Review gate blocked execution': '审查闸门阻止继续执行',
    'Waiting for writeback approval': '等待回写审批',
    'Write target normalized': '已按任务章节号纠正写回目标',
    'Data sync completed': '写回同步完成',
    'Data sync payload enriched': '已补齐写回所需的结构化信息',
    'Plan writeback completed': '卷规划写回完成',
    'Core setting docs synced': '核心设定集已更新',
    'Chapter body written': '正文已写入',
    'Step writeback failed': '步骤写回失败',
    'Resume target resolved': '已确定需要恢复的任务',
    'Resume target scheduled': '已重新排入恢复队列',
    'Resume target already running': '目标任务正在运行，无需重复恢复',
    'Resume schedule failed': '恢复排程失败',
    'Task scheduled for resume': '任务已准备恢复',
    'Task auto-completed during resume recovery': '恢复检查时检测到任务已完成',
    'Resume target failed': '恢复目标执行失败',
    'Workflow spec not found': '未找到工作流契约',
    'Workflow parse failed': '工作流契约解析失败',
    'Workflow config error': '工作流配置有误',
    'Task execution failed': '任务执行失败',
    plan_blocked: '规划待补信息',
    writeback_rollback_started: '开始回滚失败写回',
    writeback_rollback_finished: '失败写回已回滚',
    'Review summary prepared': '审查汇总已生成',
    prompt_compiled: '提示词已组装完成',
    request_dispatched: '已向上游发出请求',
    awaiting_model_response: '正在等待模型响应',
    response_received: '已收到模型响应',
    parsing_output: '正在解析输出',
    step_heartbeat: '步骤仍在运行',
    step_retry_scheduled: '已安排步骤重试',
    step_retry_started: '步骤重试开始',
    step_waiting_approval: '等待人工批准回写',
    step_auto_retried: '步骤已自动重试',
    raw_output_parse_failed: '原始输出解析失败',
    json_extraction_recovered: '已从原始输出中恢复 JSON',
}

const UI_COPY = {
    planBlockedStatus: '已完成 / 待补资料',
    planBlockedStep: '待补资料',
    approvalNotApplicable: '不适用',
    approvalNotRequired: '本任务无需你处理',
    approvalNotReached: '尚未进入审批',
    approvalPending: '等你批准回写',
    approvalApproved: '已批准',
    approvalApprovedWritingBack: '你已批准，系统正在写回',
    approvalApprovedCompleted: '已批准，写回已完成',
    approvalRejected: '已拒绝回写',
    unknownSystemEvent: '系统事件',
    unknownSystemEventWithDetail: '系统事件（请查看详情区）',
}

export function MetricCard({ label, value }) {
    return (
        <div className="metric-card">
            <div className="metric-label">{label}</div>
            <div className="metric-value">{value}</div>
        </div>
    )
}

export function formatNumber(value) {
    return Number(value || 0).toLocaleString('zh-CN')
}

export function formatTimestampShort(value) {
    if (!value || value === '-') return '-'
    const text = String(value)
    const normalized = text.endsWith('Z') || text.includes('T') ? text : text.replace(' ', 'T')
    const parsed = new Date(normalized)
    if (Number.isNaN(parsed.getTime())) {
        return text.replace('T', ' ').replace(/\.\d+/, '')
    }
    const year = parsed.getFullYear()
    const month = String(parsed.getMonth() + 1).padStart(2, '0')
    const day = String(parsed.getDate()).padStart(2, '0')
    const hour = String(parsed.getHours()).padStart(2, '0')
    const minute = String(parsed.getMinutes()).padStart(2, '0')
    const second = String(parsed.getSeconds()).padStart(2, '0')
    return `${year}-${month}-${day} ${hour}:${minute}:${second}`
}

export function parseIsoTimestamp(value) {
    const parsed = Date.parse(String(value || ''))
    return Number.isFinite(parsed) ? parsed : 0
}

export function downloadTextFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType || 'text/plain;charset=utf-8' })
    const url = window.URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    document.body.removeChild(anchor)
    window.URL.revokeObjectURL(url)
}

export function translateTaskType(value) {
    return TASK_TYPE_LABELS[value] || value || '-'
}

export function translateTaskStatus(value) {
    return STATUS_LABELS[value] || value || '-'
}

export function translateStepName(value) {
    if (value === 'task') return '任务'
    return STEP_LABELS[value] || value || '-'
}

function isPlanBlockedTask(task) {
    return Boolean(task?.task_type === 'plan' && task?.status === 'completed' && task?.artifacts?.plan_blocked)
}

export function resolveTaskStatusLabel(task) {
    if (isPlanBlockedTask(task)) return UI_COPY.planBlockedStatus
    return translateTaskStatus(task?.status)
}

export function resolveCurrentStepLabel(task) {
    if (isPlanBlockedTask(task)) return UI_COPY.planBlockedStep
    const runtimeStep = task?.runtime_status?.step_key
    if (['completed', 'failed'].includes(task?.status) && task?.runtime_status?.phase_label) {
        return task.runtime_status.phase_label
    }
    if (['completed', 'failed'].includes(task?.status) && runtimeStep) {
        return translateStepName(runtimeStep)
    }
    return translateStepName(task?.current_step || runtimeStep || 'idle')
}

export function translateApprovalStatus(value) {
    if (value === 'n/a') return UI_COPY.approvalNotApplicable
    return APPROVAL_STATUS_LABELS[value] || value || '-'
}

export function resolveApprovalStatusLabel(task) {
    const approvalStatus = task?.approval_status || 'n/a'
    if (task?.task_type !== 'write') return translateApprovalStatus(approvalStatus)
    if (!task?.request?.require_manual_approval) return UI_COPY.approvalNotRequired
    if (approvalStatus === 'approved') {
        if (task?.status === 'completed') return UI_COPY.approvalApprovedCompleted
        if (['queued', 'running'].includes(task?.status) && ['approval-gate', 'data-sync'].includes(task?.current_step)) {
            return UI_COPY.approvalApprovedWritingBack
        }
        return UI_COPY.approvalApproved
    }
    if (approvalStatus === 'pending' || task?.status === 'awaiting_writeback_approval') return UI_COPY.approvalPending
    if (approvalStatus === 'rejected') return UI_COPY.approvalRejected
    return UI_COPY.approvalNotReached
}

export function resolveTaskTargetLabel(task) {
    if (task?.runtime_status?.target_label) return task.runtime_status.target_label
    const request = task?.request || {}
    if (task?.task_type === 'plan') {
        return `第 ${request.volume || 1} 卷`
    }
    if (task?.task_type === 'write' && request.chapter) {
        return `第 ${request.chapter} 章`
    }
    if (task?.task_type === 'guarded-write' && request.chapter) {
        return `护栏推进第 ${request.chapter} 章`
    }
    if (task?.task_type === 'guarded-batch-write') {
        const startChapter = Number(request.start_chapter || request.chapter || 0)
        const maxChapters = Math.max(1, Number(request.max_chapters || 1))
        if (startChapter > 0) {
            const endChapter = startChapter + maxChapters - 1
            return endChapter > startChapter
                ? `护栏批量推进第 ${startChapter}-${endChapter} 章`
                : `护栏批量推进第 ${startChapter} 章`
        }
        return `护栏批量推进 ${maxChapters} 章`
    }
    if (task?.task_type === 'review' && request.chapter_range) {
        return `第 ${request.chapter_range} 章`
    }
    if (task?.task_type === 'resume') {
        return request.chapter ? `恢复第 ${request.chapter} 章` : '恢复最近中断任务'
    }
    return '-'
}

export function translateEventLevel(value) {
    return EVENT_LEVEL_LABELS[value] || value || '-'
}

export function translateColumnLabel(column) {
    return TABLE_HEADER_LABELS[column] || column
}

export function translateKnownValue(value) {
    if (typeof value !== 'string') return value
    if (TASK_TYPE_LABELS[value]) return TASK_TYPE_LABELS[value]
    if (STATUS_LABELS[value]) return STATUS_LABELS[value]
    if (APPROVAL_STATUS_LABELS[value]) return APPROVAL_STATUS_LABELS[value]
    if (STEP_LABELS[value]) return STEP_LABELS[value]
    if (EVENT_LEVEL_LABELS[value]) return EVENT_LEVEL_LABELS[value]
    if (RELATIONSHIP_TYPE_LABELS[value]) return RELATIONSHIP_TYPE_LABELS[value]
    if (value === 'plot') return '剧情模板'
    return value
}

export function translateEventMessage(message) {
    if (!message) return '-'
    if (EXACT_EVENT_MESSAGES[message]) return EXACT_EVENT_MESSAGES[message]

    const queuedMatch = message.match(/^Task queued[:：](.+)$/)
    if (queuedMatch) return `任务已加入队列：${translateTaskType(queuedMatch[1])}`

    const stepStartMatch = message.match(/^Step started[:：](.+)$/)
    if (stepStartMatch) return `步骤开始：${translateStepName(stepStartMatch[1])}`

    const stepDoneMatch = message.match(/^Step completed[:：](.+)$/)
    if (stepDoneMatch) return `步骤完成：${translateStepName(stepDoneMatch[1])}`

    const stepFailedMatch = message.match(/^Step failed[:：](.+)$/)
    if (stepFailedMatch) return `步骤失败：${translateStepName(stepFailedMatch[1])}`

    return /^[\x00-\x7F\s:._/-]+$/.test(message) ? UI_COPY.unknownSystemEventWithDetail : message
}

export function resolveColumnValue(row, column) {
    if (row[column] !== undefined && row[column] !== null && row[column] !== '') return row[column]
    if (column === 'name') return row.name ?? row.canonical_name
    if (column === 'tier') return row.tier ?? row.importance ?? row.level
    if (column === 'location') return row.location ?? row.scene_location ?? row.place
    return row[column]
}

export function formatCell(value, column) {
    if (value === null || value === undefined || value === '') return '-'
    if (typeof value === 'boolean') return value ? '是' : '否'
    if (typeof value === 'object') return JSON.stringify(value)
    if (column === 'chapter') return String(value)
    if (column === 'type') return String(translateKnownValue(value))
    if (isDateTimeColumn(column)) return formatTimestampShort(value)
    return String(translateKnownValue(value))
}

function isDateTimeColumn(column) {
    return ['created_at', 'updated_at', 'last_event_at', 'last_activity_at'].includes(column)
}

export function SimpleTable({ rows, columns }) {
    if (!rows.length) return <div className="empty-state">暂无数据</div>
    return (
        <div className="table-wrap">
            <table>
                <thead>
                    <tr>
                        {columns.map((column) => <th key={column}>{translateColumnLabel(column)}</th>)}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row, index) => (
                        <tr key={row.id || row.chapter || index}>
                            {columns.map((column) => <td key={column}>{formatCell(resolveColumnValue(row, column), column)}</td>)}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    )
}
