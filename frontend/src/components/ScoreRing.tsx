interface ScoreRingProps {
  score: number
  size?: 'sm' | 'md' | 'lg'
}

export function scoreColor(score: number): string {
  if (score >= 95) return '#8b5cf6' // vivid purple — masterpiece
  if (score >= 90) return '#1d4ed8' // blue — exceptional
  if (score >= 85) return '#16a34a' // dark green — excellent
  if (score >= 80) return '#22c55e' // green — very good
  if (score >= 75) return '#eab308' // yellow — good
  if (score >= 70) return '#ca8a04' // amber — decent
  if (score >= 60) return '#ea580c' // orange — below average
  if (score >= 50) return '#dc2626' // red — poor
  return '#374151'                  // near-black
}

export function ScoreRing({ score, size = 'lg' }: ScoreRingProps) {
  const rounded = Math.round(score)
  const color = scoreColor(rounded)
  return (
    <span
      className={`score-ring score-ring-${size}`}
      style={{ background: color }}
      aria-label={`GameMetrix score ${rounded}`}
    >
      {rounded}
    </span>
  )
}
