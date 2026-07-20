import type { MetaFunction } from 'react-router'
import { AccountAuth } from '../components/AccountAuth'
export const meta: MetaFunction = () => [{ title: 'Verify Email | GameMetrix' }, { name: 'robots', content: 'noindex,nofollow' }, { name: 'referrer', content: 'no-referrer' }]
export const headers = () => ({ 'Cache-Control': 'private, no-store' })
export default function VerifyEmailRoute() { return <AccountAuth mode="verify" /> }
