import type { MetaFunction } from 'react-router'
import { ImpressumPage } from '../pages/legal/ImpressumPage'

export const meta: MetaFunction = () => [
  { title: 'Impressum | GameMetrix' },
  { name: 'robots', content: 'noindex,follow' },
]
export const headers = () => ({ 'Cache-Control': 'public, max-age=300, s-maxage=3600' })
export default function ImpressumRoute() { return <ImpressumPage /> }
