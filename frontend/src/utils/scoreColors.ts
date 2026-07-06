export function scoreColor(score: number): string {
  if (score >= 95) return '#8b5cf6'
  if (score >= 90) return '#1d4ed8'
  if (score >= 85) return '#16a34a'
  if (score >= 80) return '#22c55e'
  if (score >= 75) return '#eab308'
  if (score >= 70) return '#ca8a04'
  if (score >= 60) return '#ea580c'
  if (score >= 50) return '#dc2626'
  return '#374151'
}

export function scoreColorRgb(score: number): string {
  const color = scoreColor(score).replace('#', '')
  const red = Number.parseInt(color.slice(0, 2), 16)
  const green = Number.parseInt(color.slice(2, 4), 16)
  const blue = Number.parseInt(color.slice(4, 6), 16)
  return `${red}, ${green}, ${blue}`
}

export function sourceScoreColor(score: number): string {
  if (score >= 95) return '#a79bd6'
  if (score >= 90) return '#89a4d6'
  if (score >= 85) return '#7db394'
  if (score >= 80) return '#91b783'
  if (score >= 75) return '#c1b574'
  if (score >= 70) return '#bf986d'
  if (score >= 60) return '#c08a72'
  if (score >= 50) return '#bc7777'
  return '#6f7787'
}
