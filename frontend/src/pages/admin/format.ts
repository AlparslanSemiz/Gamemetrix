import type { AdminApiHealth } from '../../services/admin'

const NUMBER_FORMATTER = new Intl.NumberFormat('en-US')
const DATE_TIME_FORMATTER = new Intl.DateTimeFormat('tr-TR', {
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})

export function formatAdminNumber(value: number): string {
  return NUMBER_FORMATTER.format(value)
}

export function formatAdminDateTime(value: string): string {
  return DATE_TIME_FORMATTER.format(new Date(value))
}

export function formatDuration(seconds: number): string {
  if (seconds <= 0) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.round((seconds % 3600) / 60)
  if (hours >= 1) return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`
  if (minutes >= 1) return `${minutes}m`
  return `${seconds}s`
}

export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return '—'
  const deltaMs = new Date(value).getTime() - Date.now()
  const seconds = Math.round(Math.abs(deltaMs) / 1000)
  const suffix = deltaMs < 0 ? ' ago' : ''
  const prefix = deltaMs < 0 ? '' : 'in '
  if (seconds < 45) return deltaMs < 0 ? 'just now' : 'now'
  const label = formatDuration(seconds)
  return `${prefix}${label}${suffix}`
}

export function adminHealthClass(
  status: AdminApiHealth[string],
): string {
  if (!status.configured) return 'is-muted'
  return status.working ? 'is-ok' : 'is-bad'
}
