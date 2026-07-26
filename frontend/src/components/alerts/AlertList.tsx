import { Bell, CalendarDays, ExternalLink, Percent, Sparkles, X } from 'lucide-react'
import { Link } from 'react-router'

import type { AlertKind, GameAlert } from './types'

const ALERT_ICON_SIZE = 17
const ACTION_ICON_SIZE = 15

function AlertIcon({ kind }: { kind: AlertKind }) {
  if (kind === 'deal') return <Percent size={ALERT_ICON_SIZE} aria-hidden="true" />
  if (kind === 'release') return <CalendarDays size={ALERT_ICON_SIZE} aria-hidden="true" />
  if (kind === 'score') return <Sparkles size={ALERT_ICON_SIZE} aria-hidden="true" />
  return <Bell size={ALERT_ICON_SIZE} aria-hidden="true" />
}

export function AlertList({
  alerts,
  readIds,
  onDismiss,
  onOpen,
}: {
  alerts: GameAlert[]
  readIds: Set<string>
  onDismiss: (id: string) => void
  onOpen: (id: string) => void
}) {
  return (
    <div className="alerts-list">
      {alerts.map((alert) => (
        <article
          className={`alert-item${readIds.has(alert.id) ? ' is-read' : ''}`}
          key={alert.id}
        >
          <span className={`alert-kind alert-kind-${alert.kind}`}>
            <AlertIcon kind={alert.kind} />
          </span>
          <div>
            <strong>{alert.title}</strong>
            <p>{alert.detail}</p>
          </div>
          <div className="alert-item-actions">
            <Link
              to={`/game/${alert.game.slug}`}
              title={`Open ${alert.game.title}`}
              onClick={() => onOpen(alert.id)}
            >
              <ExternalLink size={ACTION_ICON_SIZE} aria-hidden="true" />
            </Link>
            <button type="button" title="Dismiss alert" onClick={() => onDismiss(alert.id)}>
              <X size={ACTION_ICON_SIZE} aria-hidden="true" />
            </button>
          </div>
        </article>
      ))}
    </div>
  )
}
