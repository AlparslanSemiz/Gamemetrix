import type { HeadersFunction } from 'react-router'
import { AppContent, type UtilityPage } from '../App'
import type { GameListResponse } from '../types/game'

export const headers: HeadersFunction = () => ({ 'Cache-Control': 'private, no-store' })

export function UtilityRoute({ loaderData, page }: { loaderData: GameListResponse; page: UtilityPage }) {
  return (
    <AppContent
      initialGames={loaderData.games}
      initialTotal={loaderData.total}
      initialPage={page}
    />
  )
}
