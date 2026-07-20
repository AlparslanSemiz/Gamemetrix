import type { MetaFunction } from 'react-router'
import { AdminPage } from '../pages/AdminPage'

export const meta: MetaFunction = () => [
  { title: 'Admin | GameMetrix' },
  { name: 'robots', content: 'noindex,nofollow,noarchive' },
]

export function headers() {
  return { 'Cache-Control': 'private, no-store' }
}

export default function AdminRoute() {
  return <AdminPage />
}
