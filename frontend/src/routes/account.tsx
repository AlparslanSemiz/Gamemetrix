import type { MetaFunction } from 'react-router'
import { AccountPage } from '../pages/AccountPage'
export const meta: MetaFunction = () => [{ title: 'Account | GameMetrix' }, { name: 'robots', content: 'noindex,nofollow,noarchive' }]
export const headers = () => ({ 'Cache-Control': 'private, no-store' })
export default function AccountRoute() { return <AccountPage /> }
