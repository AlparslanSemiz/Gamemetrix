import type { MetaFunction } from 'react-router'
import { fetchBackend } from '../server-api.server'
import type { GameListResponse } from '../types/game'
import { headers, UtilityRoute } from './utility'

export { headers }
export async function loader(): Promise<GameListResponse> {
  return fetchBackend<GameListResponse>('/api/seo/curated/home?limit=24')
}
export const meta: MetaFunction = () => [
  { title: 'Alerts | GameMetrix' },
  { name: 'robots', content: 'noindex,follow' },
]

export default function AlertsRoute({ loaderData }: { loaderData: GameListResponse }) {
  return <UtilityRoute loaderData={loaderData} page="alerts" />
}
