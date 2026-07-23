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

export function adminHealthClass(
  status: AdminApiHealth[string],
): string {
  if (!status.configured) return 'is-muted'
  return status.working ? 'is-ok' : 'is-bad'
}
