import { Link } from 'react-router'
import { useAccount } from '../state/useAccount'

/**
 * Lists and alert thresholds live in this browser's storage until the visitor
 * signs in, so a signed-out visitor is told that plainly.
 */
export function GuestListNotice({ subject }: { subject: 'list' | 'alerts' }) {
  const { account, accountsEnabled, isLoading } = useAccount()
  if (isLoading || account) return null
  return (
    <aside className="guest-notice" role="note">
      <p>
        {subject === 'alerts'
          ? 'These alerts are checked only in this browser. '
          : 'This list is saved only in this browser. '}
        {accountsEnabled ? (
          <><Link to="/login">Log in</Link> to get email alerts and keep your lists in sync across devices.</>
        ) : null}
      </p>
    </aside>
  )
}
