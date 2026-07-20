import { scoreColor, scoreTextColor } from '../utils/scoreColors'

interface ScoreRingProps {
  score: number
  size?: 'sm' | 'md' | 'lg'
}

export function ScoreRing({ score, size = 'lg' }: ScoreRingProps) {
  const rounded = Math.round(score)
  const color = scoreColor(rounded)
  return (
    <span
      className={`score-ring score-ring-${size}`}
      style={{ background: color, color: scoreTextColor(rounded) }}
      aria-label={`GameMetrix score ${rounded}`}
    >
      {rounded}
    </span>
  )
}
