interface ScoreRingProps {
  score: number
  size?: 'sm' | 'md' | 'lg'
}

function scoreColor(score: number): string {
  if (score >= 90) return '#4cc458'
  if (score >= 75) return '#d4a017'
  if (score >= 60) return '#e86f2c'
  return '#e84c4c'
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
