import { useEffect, useState } from 'react'
import { fetchJSON, normalizeError } from './api.js'
import { formatTimestampShort } from './dashboardPageCommon.jsx'
import { ErrorNotice } from './sectionCommon.jsx'

export function FilesPageSection({ refreshToken }) {
    const [tree, setTree] = useState({})
    const [selectedPath, setSelectedPath] = useState('')
    const [fileDetail, setFileDetail] = useState(emptyFileDetail())
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState(null)
    const [missingNotice, setMissingNotice] = useState('')

    useEffect(() => {
        fetchJSON('/api/files/tree').then((result) => {
            setTree(result)
            if (selectedPath && !treeContainsPath(result, selectedPath)) {
                setSelectedPath('')
                setFileDetail(emptyFileDetail())
                setMissingNotice('当前文件已不存在，已清除选中。')
            }
            setError(null)
        }).catch((err) => {
            setTree({})
            setError(normalizeError(err))
        })
    }, [refreshToken])

    useEffect(() => {
        if (!selectedPath) {
            setFileDetail(emptyFileDetail())
            return
        }
        setLoading(true)
        setMissingNotice('')
        fetchJSON('/api/files/read', { path: selectedPath }).then((result) => {
            if (result.exists === false) {
                setSelectedPath('')
                setFileDetail(emptyFileDetail())
                setError(null)
                setMissingNotice('当前文件已不存在，已清除选中。')
                return
            }
            setFileDetail({
                path: result.path || selectedPath,
                content: typeof result.content === 'string' ? result.content : '',
                exists: Boolean(result.exists),
                is_binary: Boolean(result.is_binary),
                encoding: result.encoding || 'utf-8',
                size: Number(result.size || 0),
                modified_at: result.modified_at || '',
                display_name: result.display_name || '',
                is_internal: Boolean(result.is_internal),
                doc_status: result.doc_status || null,
                summary_card: result.summary_card || null,
                internal_hint: result.internal_hint || '',
            })
            setError(null)
        }).catch((err) => {
            const normalized = normalizeError(err)
            if (normalized.statusCode === 404) {
                setSelectedPath('')
                setFileDetail(emptyFileDetail())
                setError(null)
                setMissingNotice('当前文件已不存在，已清除选中。')
            } else {
                setFileDetail({ ...emptyFileDetail(), path: selectedPath })
                setError(normalized)
            }
        }).finally(() => setLoading(false))
    }, [selectedPath, refreshToken])

    const selectedNode = findTreeNode(tree, selectedPath)
    const fileMeta = resolveFileDisplayMeta(selectedPath || fileDetail.path, selectedNode, fileDetail)
    const previewText = !selectedPath
        ? ''
        : loading
            ? '读取中...'
            : fileDetail.is_binary
                ? `该文件为二进制或非 UTF-8 文本，当前编码：${fileDetail.encoding}`
                : fileDetail.exists
                    ? (fileDetail.content === '' ? '无内容' : fileDetail.content)
                    : '读取失败'

    return (
        <div className="split-layout files-layout">
            <section className="panel list-panel file-tree-panel">
                <div className="panel-title">文档树</div>
                <div className="file-tree-scroll">
                    <FileTree tree={tree} onSelect={setSelectedPath} />
                </div>
            </section>
            <section className="panel detail-panel file-preview-panel">
                <div className="panel-title">{fileMeta.displayName || selectedPath || '选择文件'}</div>
                {selectedPath ? (
                    <div className="file-meta-card">
                        <div className="file-meta-grid">
                            <div><strong>显示名称：</strong>{fileMeta.displayName}</div>
                            <div><strong>真实路径：</strong>{fileDetail.path || selectedPath}</div>
                            <div><strong>文件类型：</strong>{fileMeta.fileType}</div>
                            <div><strong>状态标签：</strong>{fileMeta.docStatus || '-'}</div>
                            <div><strong>编码：</strong>{fileDetail.encoding || '-'}</div>
                            <div><strong>大小：</strong>{formatFileSize(fileDetail.size)}</div>
                            <div><strong>更新时间：</strong>{formatTimestampShort(fileDetail.modified_at || '-')}</div>
                        </div>
                    </div>
                ) : null}
                {selectedPath && fileDetail.summary_card ? (
                    <div className="file-meta-card">
                        <div className="subsection-title">{fileDetail.summary_card.title || '摘要'}</div>
                        {fileDetail.summary_card.warning ? <div className="tiny">{fileDetail.summary_card.warning}</div> : null}
                        <div className="file-meta-grid">
                            {(fileDetail.summary_card.items || []).map((item) => (
                                <div key={`${item.label}-${item.value}`}><strong>{item.label}：</strong>{item.value || '-'}</div>
                            ))}
                        </div>
                    </div>
                ) : null}
                {selectedPath && fileDetail.internal_hint ? <div className="tiny">{fileDetail.internal_hint}</div> : null}
                <ErrorNotice error={error} />
                {!selectedPath ? (
                    <div className="file-empty-state">
                        <div className="subsection-title">请选择左侧文件</div>
                        <div className="tiny">{missingNotice || '选中文件后，这里会显示文件摘要、元信息和正文预览。'}</div>
                    </div>
                ) : (
                    <pre className="code-block file-preview">{previewText}</pre>
                )}
            </section>
        </div>
    )
}

function FileTree({ tree, onSelect }) {
    const sections = Object.entries(tree || {})
    if (sections.length === 0) return <div className="empty-state">暂无可用文件</div>
    return (
        <div className="tree-root">
            {sections.map(([rootName, children]) => (
                <div key={rootName} className="tree-section">
                    <div className="tree-title">{rootName}</div>
                    <TreeNodes nodes={children} onSelect={onSelect} />
                </div>
            ))}
        </div>
    )
}

function TreeNodes({ nodes, onSelect }) {
    return (
        <div className="tree-nodes">
            {nodes.map((node) => <TreeNode key={node.path} node={node} onSelect={onSelect} />)}
        </div>
    )
}

function TreeNode({ node, onSelect }) {
    const [expanded, setExpanded] = useState(true)

    if (node.type === 'dir') {
        return (
            <div className="tree-node">
                <button className="tree-folder tree-folder-toggle" onClick={() => setExpanded((value) => !value)}>
                    <span className="tree-folder-icon">{expanded ? '▾' : '▸'}</span>
                    <span>{displayTreeNodeName(node)}</span>
                </button>
                {expanded ? <TreeNodes nodes={node.children || []} onSelect={onSelect} /> : null}
            </div>
        )
    }

    return (
        <div className="tree-node">
            <button className="tree-file" onClick={() => onSelect(node.path)}>{displayTreeNodeName(node)}</button>
        </div>
    )
}

function displayTreeNodeName(node) {
    return resolveFileDisplayMeta(node?.path || node?.name || '', node).displayName
}

function resolveFileDisplayMeta(path, node = null, fileDetail = null) {
    const preferred = resolveLegacyFileDisplayMeta(path)
    const fallbackDisplayName = node?.display_name || fileDetail?.display_name || preferred.displayName
    return {
        displayName: preferred.displayName || fallbackDisplayName || '未命名文件',
        fileType: preferred.fileType || resolveFileType(path),
        docStatus: node?.doc_status || fileDetail?.doc_status || null,
        isInternal: Boolean(node?.is_internal || fileDetail?.is_internal),
    }
}

function resolveLegacyFileDisplayMeta(path) {
    const normalizedPath = String(path || '').replace(/\\/g, '/')
    const segments = normalizedPath.split('/').filter(Boolean)
    const name = segments[segments.length - 1] || normalizedPath || '未命名文件'
    const chapterInVolumeMatch = normalizedPath.match(/^正文\/第(\d+)卷\/第(\d{4})章\.md$/)
    const volumeDirMatch = normalizedPath.match(/^正文\/第(\d+)卷$/)
    if (normalizedPath === '.webnovel/state.json' || name === 'state.json') {
        return { displayName: 'state.json', fileType: '状态文件' }
    }
    if (normalizedPath === '正文') {
        return { displayName: '正文', fileType: '目录' }
    }
    if (volumeDirMatch) {
        return { displayName: `第${String(Number(volumeDirMatch[1]))}卷`, fileType: '卷目录' }
    }
    if (normalizedPath === '.webnovel/summaries' || name === '章节摘要') {
        return { displayName: '章节摘要', fileType: '目录' }
    }
    const volumePlanMatch = name.match(/^volume-(\d+)-plan\.md$/i)
    if (volumePlanMatch) {
        return { displayName: `第${String(Number(volumePlanMatch[1]))}卷规划.md`, fileType: '卷规划' }
    }
    const chapterFileMatch = name.match(/^ch(\d{4})\.md$/i)
    if (chapterFileMatch) {
        return { displayName: `第${String(Number(chapterFileMatch[1]))}章摘要.md`, fileType: '摘要' }
    }
    if (chapterInVolumeMatch) {
        return {
            displayName: `第${String(Number(chapterInVolumeMatch[2]))}章`,
            fileType: '正文',
        }
    }
    const chapterBodyMatch = name.match(/^第(\d{4})章\.md$/i)
    if (chapterBodyMatch) {
        return { displayName: `第${String(Number(chapterBodyMatch[1]))}章正文.md`, fileType: '正文' }
    }
    if (name === '总纲.md') {
        return { displayName: '总纲.md', fileType: '总纲' }
    }
    if (segments.includes('设定集')) {
        return { displayName: name, fileType: '设定' }
    }
    if (segments.includes('大纲')) {
        return { displayName: name, fileType: '大纲' }
    }
    if (segments.includes('正文')) {
        return { displayName: name, fileType: '正文' }
    }
    return { displayName: name, fileType: segments.length > 1 ? '文件' : '目录' }
}

function resolveFileType(path) {
    const normalizedPath = String(path || '').replace(/\\/g, '/')
    if (normalizedPath === '.webnovel/state.json') return '状态文件'
    if (/\/第\d+卷$/.test(normalizedPath)) return '卷目录'
    if (/\/第\d{4}章\.md$/.test(normalizedPath)) return '正文'
    if (/\/ch\d{4}\.md$/i.test(normalizedPath)) return '摘要'
    if (/volume-\d+-plan\.md$/i.test(normalizedPath)) return '卷规划'
    if (normalizedPath.endsWith('/总纲.md')) return '总纲'
    if (normalizedPath.includes('设定集/')) return '设定'
    return normalizedPath.split('/').length > 1 ? '文件' : '目录'
}

function treeContainsPath(tree, targetPath) {
    const target = String(targetPath || '').trim()
    if (!target) return false
    const nodes = Object.values(tree || {}).flat()
    return walkTreeNodes(nodes).some((node) => node?.type === 'file' && node.path === target)
}

function walkTreeNodes(nodes) {
    const output = []
    ;(nodes || []).forEach((node) => {
        output.push(node)
        if (node?.children?.length) {
            output.push(...walkTreeNodes(node.children))
        }
    })
    return output
}

function findTreeNode(tree, targetPath) {
    if (!targetPath) return null
    return walkTreeNodes(Object.values(tree || {}).flat()).find((node) => node?.path === targetPath) || null
}

function emptyFileDetail() {
    return {
        path: '',
        content: '',
        exists: false,
        is_binary: false,
        encoding: 'utf-8',
        size: 0,
        modified_at: '',
        display_name: '',
        is_internal: false,
        doc_status: null,
        summary_card: null,
        internal_hint: '',
    }
}

function formatFileSize(size) {
    const value = Number(size || 0)
    if (!Number.isFinite(value) || value <= 0) return '-'
    if (value < 1024) return `${value} B`
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
    return `${(value / (1024 * 1024)).toFixed(1)} MB`
}
