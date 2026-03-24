import { SimpleTable } from './dashboardPageCommon.jsx'
import { DataPageSection } from './appSections.jsx'

export function DataPage({ refreshToken }) {
    return <DataPageSection SimpleTable={SimpleTable} refreshToken={refreshToken} />
}
