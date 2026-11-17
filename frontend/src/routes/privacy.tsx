import type { MetaFunction } from 'react-router'
import { PrivacyPage } from '../pages/legal/PrivacyPage'

export const meta: MetaFunction = () => [
  { title: 'Privacy Policy | GameMetrix' },
  { name: 'robots', content: 'noindex,follow' },
]
export const headers = () => ({ 'Cache-Control': 'public, max-age=300, s-maxage=3600' })
export default function PrivacyRoute() { return <PrivacyPage /> }
