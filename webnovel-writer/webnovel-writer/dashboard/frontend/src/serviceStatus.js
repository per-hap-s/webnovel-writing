export const SERVICE_STATUS_COPY = {
    writingEngine: '写作引擎',
    retrievalEngine: '检索引擎',
}

export function mergeServiceStatusWithError(status, error) {
    if (!error) return status
    return {
        ...(status || {}),
        effective_status: 'degraded',
        connection_status: 'degraded',
        last_error: error,
    }
}

export function getWritingModelTone(llmStatus, loadError) {
    if (loadError) return 'warning'
    if (!llmStatus?.installed) return 'warning'
    const effectiveStatus = llmStatus?.effective_status || llmStatus?.connection_status
    if (effectiveStatus === 'failed') return 'danger'
    if (effectiveStatus === 'degraded') return 'warning'
    if (effectiveStatus === 'connected') return 'good'
    return 'warning'
}

export function formatWritingModelPill(llmStatus, loadError, copy = SERVICE_STATUS_COPY) {
    if (loadError) {
        const suffix = llmStatus ? ` ${formatWritingModelValue(llmStatus)}` : ''
        return `${copy.writingEngine}探活异常，请稍后重试${suffix}`
    }
    if (!llmStatus?.installed) return '未配置可用的写作引擎'
    const effectiveStatus = llmStatus?.effective_status || llmStatus?.connection_status
    if (effectiveStatus === 'failed') return `${copy.writingEngine}连接失败 ${formatWritingModelValue(llmStatus)}`
    if (effectiveStatus === 'degraded') return `${copy.writingEngine}探活异常，但最近运行成功 ${formatWritingModelValue(llmStatus)}`
    if (effectiveStatus === 'connected') return `${copy.writingEngine}已连接 ${formatWritingModelValue(llmStatus)}`
    return `${copy.writingEngine}已配置 ${formatWritingModelValue(llmStatus)}`
}

export function formatWritingModelDetail(llmStatus) {
    const tone = getWritingModelTone(llmStatus)
    if (tone === 'good') return llmStatus.model || '已连接'
    if (tone === 'warning') return '探活异常'
    return '未连接'
}

function formatWritingModelValue(llmStatus) {
    if (!llmStatus) return '未配置'
    if (llmStatus.mode === 'cli') {
        return llmStatus.version ? `本地命令行（${llmStatus.version}）` : '本地命令行'
    }
    if (llmStatus.mode === 'api') {
        return `模型：${llmStatus.model || '未指定模型'}`
    }
    if (llmStatus.mode === 'mock') {
        return '模拟运行器'
    }
    return llmStatus.provider || '未配置'
}

export function getRagTone(ragStatus, loadError) {
    const effectiveStatus = ragStatus?.effective_status || ragStatus?.connection_status
    if (loadError) return 'warning'
    if (!ragStatus?.configured) return 'warning'
    if (effectiveStatus === 'failed') return 'danger'
    if (effectiveStatus === 'connected') return 'good'
    return 'warning'
}

export function formatRagStatusLabel(ragStatus, loadError, copy = SERVICE_STATUS_COPY) {
    const effectiveStatus = ragStatus?.effective_status || ragStatus?.connection_status
    const suffix = ragStatus?.embed_model ? ` ${ragStatus.embed_model}` : ''
    if (loadError) {
        return `${copy.retrievalEngine}探活异常，请稍后重试${suffix}`.trim()
    }
    if (!ragStatus?.configured) return `${copy.retrievalEngine}未配置`
    if (effectiveStatus === 'failed') {
        return `${copy.retrievalEngine}连接失败：${formatRagErrorSummary(ragStatus.connection_error || ragStatus.last_error)}`
    }
    if (effectiveStatus === 'connected') {
        return `${copy.retrievalEngine}已连接${suffix}`.trim()
    }
    if (effectiveStatus === 'not_configured') return `${copy.retrievalEngine}未配置`
    return `${copy.retrievalEngine}未连接${suffix}`.trim()
}

export function formatRagDetail(ragStatus) {
    const status = ragStatus?.effective_status || ragStatus?.connection_status
    if (status === 'connected') return ragStatus?.embed_model || '已连接'
    if (status === 'degraded') return '探活异常'
    if (status === 'failed') return '连接失败'
    return '未连接'
}

export function formatRagErrorSummary(error) {
    if (!error) return '未知错误'
    if (typeof error === 'string') return error
    if (error?.details?.stage || error?.code) {
        const stage = error?.details?.stage ? String(error.details.stage) : 'embedding'
        const code = error?.code || 'UNKNOWN'
        return `${stage} / ${code}`
    }
    return error.message || error.code || '未知错误'
}
