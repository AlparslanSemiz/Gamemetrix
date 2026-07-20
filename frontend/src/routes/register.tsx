import type { MetaFunction } from 'react-router'
import { AccountAuth } from '../components/AccountAuth'
export const meta: MetaFunction = () => [{ title: 'Create Account | GameMetrix' }, { name: 'robots', content: 'noindex,nofollow' }]
export const headers = () => ({ 'Cache-Control': 'private, no-store' })
export default function RegisterRoute() { return <AccountAuth mode="register" /> }
