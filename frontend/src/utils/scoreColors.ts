export function scoreColor(score: number): string {
  if (score >= 90) return '#22c55e'
  if (score >= 80) return '#84cc16'
  if (score >= 70) return '#eab308'
  if (score >= 60) return '#f97316'
  if (score >= 50) return '#ef4444'
  return '#6b7280'
}

export function scoreColorRgb(score: number): string {
  const color = scoreColor(score).replace('#', '')
  const red = Number.parseInt(color.slice(0, 2), 16)
  const green = Number.parseInt(color.slice(2, 4), 16)
  const blue = Number.parseInt(color.slice(4, 6), 16)
  return `${red}, ${green}, ${blue}`
}

export function sourceScoreColor(score: number): string {
  if (score >= 90) return '#86efac'
  if (score >= 80) return '#bef264'
  if (score >= 70) return '#fde047'
  if (score >= 60) return '#fdba74'
  if (score >= 50) return '#fca5a5'
  return '#9ca3af'
}
