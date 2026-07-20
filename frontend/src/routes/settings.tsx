import type { MetaFunction } from 'react-router'
import { fetchBackend } from '../server-api.server'
import type { GameListResponse } from '../types/game'
import { headers, UtilityRoute } from './utility'

export { headers }
export async function loader(): Promise<GameListResponse> {
  return fetchBackend<GameListResponse>('/api/seo/curated/home?limit=24')
}
export const meta: MetaFunction = () => [
  { title: 'Settings | GameMetrix' },
  { name: 'robots', content: 'noindex,follow' },
]

export default function SettingsRoute({ loaderData }: { loaderData: GameListResponse }) {
  return <UtilityRoute loaderData={loaderData} page="settings" />
}
