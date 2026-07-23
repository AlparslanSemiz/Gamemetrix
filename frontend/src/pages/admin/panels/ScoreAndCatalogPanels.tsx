import { Server } from 'lucide-react'

import { RefreshAllPanel } from '../../../components/RefreshAllPanel'
import { ScoreWeightSettings } from '../../../components/ScoreWeightSettings'
import type { AdminDashboard } from '../../../services/admin'
import { AdminRow, Panel, RowList } from './Panel'

export function ScoreAndCatalogPanels({
  dashboard,
  token,
  onScoreWeightsSaved,
}: {
  dashboard: AdminDashboard | null
  token: string
  onScoreWeightsSaved: () => void
}) {
  return (
    <>
      <Panel title="Score Weights" width="wide">
        <ScoreWeightSettings token={token} onSaved={onScoreWeightsSaved} />
      </Panel>
      <Panel title="Score Data">
        <RefreshAllPanel token={token} />
      </Panel>
      <Panel title="Catalog" action={<Server size={16} aria-hidden="true" />}>
        <RowList>
          <AdminRow label="Non-game rows" value={dashboard?.catalog.non_game_rows ?? 0} />
          <AdminRow
            label="Rating snapshots"
            value={dashboard?.catalog.rating_snapshots ?? 0}
          />
          <AdminRow
            label="Source snapshots"
            value={dashboard?.catalog.source_snapshots ?? 0}
          />
        </RowList>
      </Panel>
    </>
  )
}
