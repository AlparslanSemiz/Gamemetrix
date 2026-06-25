interface ScoreRingProps {
  score: number
  size?: 'sm' | 'md' | 'lg'
}

function scoreColor(score: number): string {
  if (score >= 95) return '#7c3aed' // purple
  if (score >= 90) return '#1d4ed8' // dark blue
  if (score >= 85) return '#166534' // dark green
  if (score >= 80) return '#16a34a' // green
  if (score >= 75) return '#22c55e' // light green
  if (score >= 70) return '#84cc16' // lime / green-yellow
  if (score >= 65) return '#eab308' // yellow
  if (score >= 58) return '#ea580c' // orange
  if (score >= 46) return '#ca8a04' // amber
  if (score >= 30) return '#dc2626' // red
  return '#374151'                  // near-black
}

export function ScoreRing({ score, size = 'lg' }: ScoreRingProps) {
  const rounded = Math.round(score)
  const color = scoreColor(rounded)
  return (
    <span
      className={`score-ring score-ring-${size}`}
      style={{ background: color }}
      aria-label={`Metrix score ${rounded}`}
    >
      {rounded}
    </span>
  )
}
