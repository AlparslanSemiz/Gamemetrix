import type { MetaFunction } from 'react-router'
import { DatenschutzPage } from '../pages/legal/DatenschutzPage'

export const meta: MetaFunction = () => [
  { title: 'Datenschutzerklärung | GameMetrix' },
  { name: 'robots', content: 'noindex,follow' },
]
export const headers = () => ({ 'Cache-Control': 'public, max-age=300, s-maxage=3600' })
export default function DatenschutzRoute() { return <DatenschutzPage /> }
