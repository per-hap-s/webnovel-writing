import { SimpleTable, formatCell, translateColumnLabel } from './dashboardPageCommon.jsx'
import { QualityPageSection } from './appSections.jsx'

export function QualityPage({ refreshToken, onMutated }) {
    return <QualityPageSection refreshToken={refreshToken} onMutated={onMutated} SimpleTable={SimpleTable} translateColumnLabel={translateColumnLabel} formatCell={formatCell} />
}
