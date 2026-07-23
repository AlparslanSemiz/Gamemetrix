import { KeyRound, ShieldCheck } from 'lucide-react'
import type { FormEvent } from 'react'

const ADMIN_USERNAME_MAX_LENGTH = 64
const ADMIN_PASSWORD_MAX_LENGTH = 128

interface AdminLoginProps {
  error: string | null
  isSigningIn: boolean
  password: string
  username: string
  onChangePassword: (value: string) => void
  onChangeUsername: (value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function AdminLogin({
  error,
  isSigningIn,
  password,
  username,
  onChangePassword,
  onChangeUsername,
  onSubmit,
}: AdminLoginProps) {
  return (
    <main className="admin-shell">
      <section className="admin-login-panel">
        <div className="admin-login-mark">
          <ShieldCheck size={24} aria-hidden="true" />
        </div>
        <h1>GameMetrix Admin</h1>
        <form className="admin-login-form" onSubmit={onSubmit}>
          <label>
            <span>Username</span>
            <input
              autoComplete="username"
              required
              maxLength={ADMIN_USERNAME_MAX_LENGTH}
              value={username}
              onChange={(event) => onChangeUsername(event.target.value)}
            />
          </label>
          <label>
            <span>Password</span>
            <input
              autoComplete="current-password"
              type="password"
              required
              maxLength={ADMIN_PASSWORD_MAX_LENGTH}
              value={password}
              onChange={(event) => onChangePassword(event.target.value)}
            />
          </label>
          <button type="submit" disabled={isSigningIn}>
            <KeyRound size={16} aria-hidden="true" />
            <span>{isSigningIn ? 'Signing in' : 'Sign in'}</span>
          </button>
        </form>
        {error ? <p className="admin-error">{error}</p> : null}
      </section>
    </main>
  )
}
