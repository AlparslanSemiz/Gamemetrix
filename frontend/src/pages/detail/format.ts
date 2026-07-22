export function normalizeSignal(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
}

// Pinned locale: the server formats in the container's locale and the browser in
// the visitor's, so a bare toLocaleString() renders 26,352 on one side and
// 26.352 on the other and fails hydration.
const COUNT_FORMATTER = new Intl.NumberFormat('en-US')

export function formatCount(value: number): string {
  return COUNT_FORMATTER.format(value)
}

export function formatCompactCount(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value >= 10_000_000 ? 0 : 1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(value >= 100_000 ? 0 : 1)}K`
  return formatCount(value)
}

export function formatDate(value?: string | null): string {
  if (!value) return 'Not tracked'
  const date = new Date(value)
  if (Number.isNaN(date.getTime()) || date.getFullYear() <= 1970) return 'Not tracked'
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

export function formatMoney(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined) return 'N/A'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency || 'USD',
    maximumFractionDigits: value % 1 === 0 ? 0 : 2,
  }).format(value)
}
