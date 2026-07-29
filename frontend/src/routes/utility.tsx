import type { HeadersFunction } from 'react-router'
import { AppContent, type UtilityPage } from '../App'

export const headers: HeadersFunction = () => ({ 'Cache-Control': 'private, no-store' })

export function UtilityRoute({ page }: { page: UtilityPage }) {
  return <AppContent initialPage={page} />
}
