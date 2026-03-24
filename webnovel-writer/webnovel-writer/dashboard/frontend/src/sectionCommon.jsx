import { useState } from 'react'
import { normalizeError } from './api.js'

export function Field({ label, children }) {
    return (
        <label className="field">
            <span>{label}</span>
            {children}
        </label>
    )
}

export function ErrorNotice({ error, title = '操作失败' }) {
    const [showDetails, setShowDetails] = useState(false)
    if (!error) return null

    const normalized = normalizeError(error)
    const detailText = buildErrorDetailText(normalized)

    return (
        <div className="error-panel" role="alert">
            <div className="error-title">{title}</div>
            <div className="error-text">{normalized.displayMessage}</div>
            {detailText ? (
                <details className="error-details" onToggle={(event) => setShowDetails(event.currentTarget.open)}>
                    <summary>查看诊断详情</summary>
                    {showDetails ? <pre className="error-details-block">{detailText}</pre> : null}
                </details>
            ) : null}
        </div>
    )
}

export function CompactEmptyCard({ title, description }) {
    return (
        <div className="compact-empty-card">
            <div className="subsection-title">{title}</div>
            <div className="tiny">{description}</div>
        </div>
    )
}

function buildErrorDetailText(error) {
    const lines = []

    if (error.code) {
        lines.push(`错误码：${error.code}`)
    }
    if (error.statusCode) {
        lines.push(`HTTP 状态：${error.statusCode}`)
    }
    if (error.rawMessage && error.rawMessage !== error.displayMessage) {
        lines.push(`原始消息：${error.rawMessage}`)
    }
    if (error.details !== null && error.details !== undefined) {
        const detailsText = typeof error.details === 'string'
            ? error.details
            : JSON.stringify(error.details, null, 2)
        lines.push(`详情：${detailsText}`)
    }

    return lines.join('\n')
}
