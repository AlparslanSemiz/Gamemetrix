// Every date shown to a visitor goes through here. The server renders in the
// container's time zone and the browser in the visitor's, so any formatter that
// reads the local zone (toLocale*, getFullYear, bare Intl.DateTimeFormat) renders
// a different day on each side and fails hydration. ISO dates are calendar days:
// format them in UTC, with a pinned locale.

export type IsoDateStyle = 'short' | 'long'

const DATE_FORMATTERS: Record<IsoDateStyle, Intl.DateTimeFormat> = {
  short: new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric' }),
  long: new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'long', day: 'numeric', year: 'numeric' }),
}

/** Parses an ISO date or timestamp; null when invalid or the "unknown" epoch placeholder. */
function parseIsoDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime()) || date.getUTCFullYear() <= 1970) return null
  return date
}

export function formatIsoDate(value: string | null | undefined, style: IsoDateStyle = 'short'): string | null {
  const date = parseIsoDate(value)
  return date ? DATE_FORMATTERS[style].format(date) : null
}

export function currentUtcYear(): number {
  return new Date().getUTCFullYear()
}

const NUMBER_FORMATTER = new Intl.NumberFormat('en-US')

/** Thousands-separated, locale-pinned: 52,092 on the server and in every browser. */
export function formatNumber(value: number): string {
  return NUMBER_FORMATTER.format(value)
}
