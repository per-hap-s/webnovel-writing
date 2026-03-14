const BASE = ''

const CODE_MESSAGE_MAP = {
    CONFLICT: '当前操作与现有数据冲突，请调整后重试。',
    NOT_FOUND: '未找到对应资源。',
    BAD_REQUEST: '请求无效，请检查输入后重试。',
    VALIDATION_ERROR: '请求参数校验失败，请检查输入内容。',
    INTERNAL_VALIDATION_ERROR: '内部数据校验失败，请稍后重试。',
    REQUEST_TIMEOUT: '请求处理超时，请稍后重试。',
    DATABASE_ERROR: '数据库操作失败，请稍后重试。',
    DATABASE_LOCKED: '数据库正忙，请稍后重试。',
    TABLE_NOT_FOUND: '所需数据表不存在。',
    INTEGRITY_ERROR: '数据约束校验失败，请检查输入内容。',
    JSON_PARSE_ERROR: '服务端返回的数据解析失败。',
    INTERNAL_ERROR: '服务器内部错误，请稍后重试。',
    PROJECT_BOOTSTRAP_FAILED: '项目初始化失败。',
    PROJECT_BOOTSTRAP_INCOMPLETE: '项目初始化未完成，未生成必要文件。',
    LLM_NOT_CONFIGURED: '写作模型尚未配置完整。',
    LLM_HTTP_ERROR: '写作模型接口请求失败。',
    LLM_REQUEST_FAILED: '写作模型接口连接失败。',
    LLM_RESPONSE_INVALID: '写作模型返回的数据格式无效。',
    CODEX_CLI_NOT_FOUND: '未找到 Codex CLI 可执行文件。',
    CODEX_AUTH_REQUIRED: 'Codex CLI 尚未登录。',
    CODEX_TIMEOUT: 'Codex 步骤执行超时。',
    CODEX_EXEC_ERROR: 'Codex CLI 调用失败。',
    CODEX_STEP_FAILED: 'Codex 步骤执行失败。',
    INVALID_STEP_OUTPUT: '步骤输出格式无效。',
    REVIEW_GATE_BLOCKED: '审查关卡阻止了继续执行。',
    NETWORK_ERROR: '网络请求失败，请检查连接后重试。',
    HTML_RESPONSE: '后端返回了页面内容而不是接口数据。',
    INVALID_JSON_RESPONSE: '接口返回了无效的 JSON 数据。',
    REQUEST_FAILED: '请求失败，请稍后重试。',
}

const STATUS_MESSAGE_MAP = {
    400: '请求无效，请检查输入后重试。',
    401: '当前请求未通过身份校验。',
    403: '当前操作被拒绝。',
    404: '未找到对应资源。',
    405: '当前请求方法不被允许。',
    409: '当前操作与现有数据冲突，请调整后重试。',
    422: '请求参数校验失败，请检查输入内容。',
    429: '请求过于频繁，请稍后再试。',
    500: '服务器内部错误，请稍后重试。',
    502: '上游服务暂时不可用，请稍后重试。',
    503: '服务暂时不可用，请稍后重试。',
    504: '请求处理超时，请稍后重试。',
}

const STATUS_CODE_MAP = {
    400: 'BAD_REQUEST',
    401: 'UNAUTHORIZED',
    403: 'FORBIDDEN',
    404: 'NOT_FOUND',
    405: 'METHOD_NOT_ALLOWED',
    409: 'CONFLICT',
    422: 'VALIDATION_ERROR',
    429: 'RATE_LIMITED',
    500: 'INTERNAL_ERROR',
    502: 'BAD_GATEWAY',
    503: 'SERVICE_UNAVAILABLE',
    504: 'REQUEST_TIMEOUT',
}

class AppError extends Error {
    constructor({
        displayMessage,
        code,
        rawMessage = '',
        details = null,
        statusCode = undefined,
    }) {
        super(displayMessage)
        this.name = 'AppError'
        this.displayMessage = displayMessage
        this.code = code || 'REQUEST_FAILED'
        this.rawMessage = rawMessage || ''
        this.details = details
        this.statusCode = statusCode
    }
}

function buildUrl(path, params = {}) {
    const url = new URL(`${BASE}${path}`, window.location.origin)
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
            url.searchParams.set(key, value)
        }
    })
    return url.toString()
}

function inferCodeFromStatus(statusCode) {
    return STATUS_CODE_MAP[statusCode] || 'REQUEST_FAILED'
}

function getDisplayMessage(code, statusCode) {
    return CODE_MESSAGE_MAP[code] || STATUS_MESSAGE_MAP[statusCode] || CODE_MESSAGE_MAP.REQUEST_FAILED
}

function looksLikeEnglishMessage(text) {
    return Boolean(text) && /^[\x00-\x7F\s.,:;!?'"`()\[\]{}\-_/\\]+$/.test(text)
}

function parseJSON(text) {
    return JSON.parse(text)
}

function parseErrorPayload(text) {
    if (!text) return null
    try {
        const parsed = parseJSON(text)
        return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : null
    } catch {
        return null
    }
}

function buildHTMLResponseError(path, statusCode) {
    const rawMessage = path.startsWith('/api/settings/')
        ? '当前 Dashboard 后端尚未重启，API 设置接口还未生效。请关闭启动窗口后重新启动 Dashboard。'
        : '后端返回了页面内容而不是接口数据。请关闭并重新启动 Dashboard。'
    return new AppError({
        displayMessage: CODE_MESSAGE_MAP.HTML_RESPONSE,
        code: 'HTML_RESPONSE',
        rawMessage,
        details: { path },
        statusCode,
    })
}

function buildApiError(path, statusCode, payload, text) {
    const code = typeof payload?.code === 'string' && payload.code ? payload.code : inferCodeFromStatus(statusCode)
    const rawMessage = typeof payload?.message === 'string' && payload.message
        ? payload.message
        : (text || '').trim()
    const details = payload && typeof payload === 'object'
        ? (payload.details ?? (payload.code || payload.message ? null : payload))
        : null

    return new AppError({
        displayMessage: rawMessage && !looksLikeEnglishMessage(rawMessage)
            ? rawMessage
            : getDisplayMessage(code, statusCode),
        code,
        rawMessage,
        details,
        statusCode,
    })
}

export function normalizeError(error) {
    if (error instanceof AppError) return error
    if (error?.name === 'AbortError') {
        return new AppError({
            displayMessage: CODE_MESSAGE_MAP.REQUEST_TIMEOUT,
            code: 'REQUEST_TIMEOUT',
            rawMessage: '请求已中断。',
        })
    }
    if (error && typeof error === 'object') {
        const code = typeof error.code === 'string' && error.code ? error.code : 'REQUEST_FAILED'
        const statusCode = typeof error.statusCode === 'number'
            ? error.statusCode
            : (typeof error.status_code === 'number' ? error.status_code : undefined)
        const rawMessage = typeof error.rawMessage === 'string'
            ? error.rawMessage
            : (typeof error.message === 'string' ? error.message : '')
        const details = Object.prototype.hasOwnProperty.call(error, 'details') ? error.details : null

        return new AppError({
            displayMessage: typeof error.displayMessage === 'string' && error.displayMessage
                ? error.displayMessage
                : (rawMessage && !looksLikeEnglishMessage(rawMessage)
                    ? rawMessage
                    : getDisplayMessage(code, statusCode)),
            code,
            rawMessage,
            details,
            statusCode,
        })
    }
    if (error instanceof Error) {
        return new AppError({
            displayMessage: CODE_MESSAGE_MAP.REQUEST_FAILED,
            code: 'REQUEST_FAILED',
            rawMessage: error.message,
        })
    }
    return new AppError({
        displayMessage: CODE_MESSAGE_MAP.REQUEST_FAILED,
        code: 'REQUEST_FAILED',
        rawMessage: String(error || ''),
    })
}

export async function requestJSON(path, options = {}) {
    const { params, body, method = 'GET' } = options

    let response
    try {
        response = await fetch(buildUrl(path, params), {
            method,
            headers: {
                Accept: 'application/json',
                ...(body ? { 'Content-Type': 'application/json' } : {}),
            },
            body: body ? JSON.stringify(body) : undefined,
        })
    } catch (error) {
        throw new AppError({
            displayMessage: CODE_MESSAGE_MAP.NETWORK_ERROR,
            code: 'NETWORK_ERROR',
            rawMessage: error instanceof Error ? error.message : String(error || ''),
            details: { path },
        })
    }

    const contentType = response.headers.get('content-type') || ''
    const text = await response.text()
    const isHTML = contentType.includes('text/html') || /^\s*<!DOCTYPE html/i.test(text) || /^\s*<html/i.test(text)

    if (!response.ok) {
        if (isHTML) {
            throw buildHTMLResponseError(path, response.status)
        }
        throw buildApiError(path, response.status, parseErrorPayload(text), text)
    }

    if (isHTML) {
        throw buildHTMLResponseError(path, response.status)
    }

    try {
        return parseJSON(text)
    } catch {
        throw new AppError({
            displayMessage: CODE_MESSAGE_MAP.INVALID_JSON_RESPONSE,
            code: 'INVALID_JSON_RESPONSE',
            rawMessage: `接口 ${path} 返回的数据不是有效 JSON。`,
            details: { path, responseText: text },
            statusCode: response.status,
        })
    }
}

export function fetchJSON(path, params = {}) {
    return requestJSON(path, { params, method: 'GET' })
}

export function postJSON(path, body = {}) {
    return requestJSON(path, { method: 'POST', body })
}

export function subscribeSSE(onMessage, handlers = {}) {
    const { onOpen, onError } = handlers
    const es = new EventSource(`${BASE}/api/events`)
    es.onopen = () => {
        if (onOpen) onOpen()
    }
    es.onmessage = (event) => {
        try {
            onMessage(JSON.parse(event.data))
        } catch {
            // ignore malformed events
        }
    }
    es.onerror = (error) => {
        if (onError) onError(error)
    }
    return () => es.close()
}
