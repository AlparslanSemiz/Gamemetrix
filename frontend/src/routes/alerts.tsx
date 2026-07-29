import type { MetaFunction } from 'react-router'
import { headers, UtilityRoute } from './utility'

export { headers }
export const meta: MetaFunction = () => [
  { title: 'Alerts | GameMetrix' },
  { name: 'robots', content: 'noindex,follow' },
]

export default function AlertsRoute() {
  return <UtilityRoute page="alerts" />
}
