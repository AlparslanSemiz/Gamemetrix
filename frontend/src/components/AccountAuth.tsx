import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowLeft, KeyRound, LogIn, Mail, UserPlus, X } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import {
  AccountApiError,
  registerAccount,
  requestPasswordReset,
  resetAccountPassword,
  verifyAccountEmail,
} from '../services/account'
import { trackProductEvent } from '../services/analytics'
import { useAccount } from '../state/useAccount'
import './AccountAuth.css'

export type AuthMode = 'login' | 'register' | 'forgot' | 'reset' | 'verify'

const TITLES: Record<AuthMode, string> = {
  login: 'Log in',
  register: 'Create account',
  forgot: 'Reset password',
  reset: 'Choose a new password',
  verify: 'Verify email',
}

export function AccountAuth({ mode }: { mode: AuthMode }) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [actionToken] = useState(() => {
    const queryToken = searchParams.get('token') ?? ''
    if (queryToken || typeof window === 'undefined') return queryToken
    return new URLSearchParams(window.location.hash.slice(1)).get('token') ?? ''
  })
  const { account, login } = useAccount()
  const firstInput = useRef<HTMLInputElement>(null)
  const [displayName, setDisplayName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    firstInput.current?.focus()
  }, [mode])

  useEffect(() => {
    if (actionToken && mode === 'reset') window.history.replaceState(window.history.state, '', '/reset-password')
    if (actionToken && mode === 'verify') window.history.replaceState(window.history.state, '', '/verify-email')
  }, [actionToken, mode])

  useEffect(() => {
    if (account && mode === 'login') navigate('/account', { replace: true })
  }, [account, mode, navigate])

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') navigate('/')
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [navigate])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setError(null)
    setMessage(null)
    setIsSubmitting(true)
    try {
      if (mode === 'login') {
        await login(email, password)
        trackProductEvent('login_completed', { method: 'password' })
        navigate('/account', { replace: true })
      } else if (mode === 'register') {
        const result = await registerAccount({ display_name: displayName, email, password })
        setMessage(result.message)
        setPassword('')
      } else if (mode === 'forgot') {
        const result = await requestPasswordReset(email)
        setMessage(result.message)
      } else if (mode === 'reset') {
        if (!actionToken) throw new Error('The password reset token is missing.')
        const result = await resetAccountPassword(actionToken, password)
        setMessage(result.message)
        setPassword('')
      } else {
        if (!actionToken) throw new Error('The verification token is missing.')
        const result = await verifyAccountEmail(actionToken, password)
        trackProductEvent('signup_completed', { method: 'password' })
        setMessage(result.message)
        setPassword('')
      }
    } catch (caught) {
      setError(caught instanceof AccountApiError || caught instanceof Error ? caught.message : 'The request could not be completed.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const googleUrl = `/api/account/oauth/google/start?return_to=${encodeURIComponent('/account')}`
  const oauthError = searchParams.get('oauth') === 'cancelled' ? 'Google sign-in was cancelled.' : null

  return (
    <main className="account-auth-shell">
      <section className="account-auth-dialog" role="dialog" aria-modal="true" aria-labelledby="account-auth-title">
        <div className="account-auth-head">
          <Link to="/" className="account-auth-back" aria-label="Back to catalog"><ArrowLeft size={18} /></Link>
          <a className="account-auth-brand" href="/">Game<span>Metrix</span></a>
          <button type="button" className="account-auth-close" onClick={() => navigate('/')} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="account-auth-icon" aria-hidden="true">
          {mode === 'register' ? <UserPlus size={22} /> : mode === 'forgot' || mode === 'reset' ? <KeyRound size={22} /> : mode === 'verify' ? <Mail size={22} /> : <LogIn size={22} />}
        </div>
        <h1 id="account-auth-title">{TITLES[mode]}</h1>

        <form onSubmit={submit} className="account-auth-form">
          {mode === 'register' ? (
            <label>
              <span>Name</span>
              <input ref={firstInput} name="name" autoComplete="name" minLength={2} maxLength={80} required value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
            </label>
          ) : null}
          {mode === 'login' || mode === 'register' || mode === 'forgot' ? (
            <label>
              <span>Email</span>
              <input ref={mode !== 'register' ? firstInput : undefined} type="email" name="email" autoComplete="email" maxLength={320} required value={email} onChange={(event) => setEmail(event.target.value)} />
            </label>
          ) : null}
          {mode === 'login' || mode === 'register' || mode === 'reset' || mode === 'verify' ? (
            <label>
              <span>Password</span>
              <input ref={mode === 'reset' || mode === 'verify' ? firstInput : undefined} type="password" name="password" autoComplete={mode === 'login' || mode === 'verify' ? 'current-password' : 'new-password'} minLength={mode === 'login' ? 1 : 12} maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
            </label>
          ) : null}
          {error || oauthError ? <p className="account-auth-status is-error" role="alert">{error ?? oauthError}</p> : null}
          {message ? <p className="account-auth-status is-success" role="status">{message}</p> : null}
          <button type="submit" className="account-auth-submit" disabled={isSubmitting}>
            {isSubmitting ? 'Working...' : TITLES[mode]}
          </button>
        </form>

        {mode === 'login' || mode === 'register' ? (
          <>
            <div className="account-auth-divider"><span>or</span></div>
            <a className="account-auth-google" href={googleUrl}>Continue with Google</a>
          </>
        ) : null}

        <div className="account-auth-links">
          {mode === 'login' ? <><Link to="/register">Create an account</Link><Link to="/forgot-password">Forgot password?</Link></> : null}
          {mode === 'register' ? <Link to="/login">Already have an account?</Link> : null}
          {mode === 'forgot' || mode === 'reset' || mode === 'verify' ? <Link to="/login">Back to login</Link> : null}
        </div>
      </section>
    </main>
  )
}
