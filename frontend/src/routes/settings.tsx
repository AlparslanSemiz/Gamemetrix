import type { MetaFunction } from 'react-router'
import { headers, UtilityRoute } from './utility'

export { headers }
export const meta: MetaFunction = () => [
  { title: 'Settings | GameMetrix' },
  { name: 'robots', content: 'noindex,follow' },
]

export default function SettingsRoute() {
  return <UtilityRoute page="settings" />
}
