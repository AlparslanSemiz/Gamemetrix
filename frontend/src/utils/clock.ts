// The one place client-only code may read the wall clock. Render paths must take
// their "now" from the route loader (`renderedAt`) so server and browser agree.
export function clientNow(): number {
  return Date.now()
}

export function clientTimeZone(): string | undefined {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined
}
