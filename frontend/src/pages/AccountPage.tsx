import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, Download, LogOut, ShieldCheck, Trash2 } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { AccountApiError, deleteAccountData, exportAccountData } from '../services/account'
import { trackProductEvent } from '../services/analytics'
import { useAccount } from '../state/useAccount'
import './AccountPage.css'

export function AccountPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const oauthEventTracked = useRef(false)
  const { account, accountState, clearAccount, isLoading, logout, updatePreferences } = useAccount()
  const [error, setError] = useState<string | null>(null)
  const [deleteText, setDeleteText] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!isLoading && !account) navigate('/login', { replace: true })
  }, [account, isLoading, navigate])

  useEffect(() => {
    const event = searchParams.get('account_event')
    if (!account || oauthEventTracked.current || (event !== 'signup_completed' && event !== 'login_completed')) return
    oauthEventTracked.current = true
    trackProductEvent(event, { method: 'google' })
    const next = new URLSearchParams(searchParams)
    next.delete('account_event')
    navigate(next.size ? `/account?${next.toString()}` : '/account', { replace: true })
  }, [account, navigate, searchParams])

  if (isLoading || !account) return <main className="account-page"><p>Loading account...</p></main>

  const run = async (operation: () => Promise<void>) => {
    setError(null)
    setBusy(true)
    try { await operation() }
    catch (caught) { setError(caught instanceof AccountApiError || caught instanceof Error ? caught.message : 'The request failed.') }
    finally { setBusy(false) }
  }

  const downloadExport = () => run(async () => {
    const data = await exportAccountData()
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `gamemetrix-account-${new Date().toISOString().slice(0, 10)}.json`
    anchor.click()
    URL.revokeObjectURL(url)
  })

  const setEmailPreference = (key: 'email_digest_enabled' | 'marketing_enabled', enabled: boolean) => run(async () => {
    await updatePreferences({ [key]: enabled })
    if (key === 'email_digest_enabled' && enabled) {
      trackProductEvent('alert_enabled', { kind: 'daily_digest' })
    }
  })

  return (
    <main className="account-page">
      <header className="account-page-head">
        <Link to="/" aria-label="Back to catalog"><ArrowLeft size={18} /></Link>
        <a href="/" className="account-page-brand">Game<span>Metrix</span></a>
      </header>
      <div className="account-page-inner">
        <div className="account-page-title">
          <div><ShieldCheck size={24} aria-hidden="true" /></div>
          <div><h1>{account.display_name}</h1><p>{account.email}</p></div>
          <span className={account.email_verified ? 'is-verified' : 'is-pending'}>{account.email_verified ? 'Verified' : 'Verification pending'}</span>
        </div>

        {error ? <p className="account-page-error" role="alert">{error}</p> : null}

        <section className="account-section">
          <h2>Synchronization</h2>
          <p>{Object.values(accountState?.collections ?? {}).reduce((sum, values) => sum + values.length, 0)} saved collection entries are synchronized.</p>
        </section>

        <section className="account-section">
          <h2>Email alerts</h2>
          <label className="account-toggle">
            <input type="checkbox" checked={accountState?.preferences.email_digest_enabled ?? false} onChange={(event) => void setEmailPreference('email_digest_enabled', event.target.checked)} />
            <span>Daily wishlist deal, free game, release and score digest</span>
          </label>
          <label className="account-toggle">
            <input type="checkbox" checked={accountState?.preferences.marketing_enabled ?? false} onChange={(event) => void setEmailPreference('marketing_enabled', event.target.checked)} />
            <span>Product news and marketing email</span>
          </label>
        </section>

        <section className="account-section account-actions">
          <h2>Account data</h2>
          <button type="button" onClick={() => void downloadExport()} disabled={busy}><Download size={17} /> Export JSON</button>
          <button type="button" onClick={() => void run(async () => { await logout(); navigate('/') })} disabled={busy}><LogOut size={17} /> Log out</button>
        </section>

        <section className="account-section account-danger">
          <h2>Delete account</h2>
          <input aria-label="Type DELETE to confirm" placeholder="Type DELETE" value={deleteText} onChange={(event) => setDeleteText(event.target.value)} />
          <input aria-label="Current password" type="password" autoComplete="current-password" placeholder="Current password, if set" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
          <button type="button" disabled={busy || deleteText !== 'DELETE'} onClick={() => void run(async () => {
            await deleteAccountData(currentPassword)
            clearAccount()
            navigate('/')
          })}><Trash2 size={17} /> Delete account</button>
        </section>
      </div>
    </main>
  )
}
