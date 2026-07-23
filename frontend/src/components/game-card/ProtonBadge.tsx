import { MonitorCheck } from 'lucide-react'
import type { Game, ProtonTier } from '../../types/game'
import {
  PROTON_TIER_DESCRIPTIONS,
  PROTON_TIER_LABELS,
  formatProtonScore,
} from '../../utils/proton'
import { steamAppIdFromGame } from '../../utils/steam'

interface ProtonBadgeProps {
  compact?: boolean
  game: Game
  tier: ProtonTier
}

export function ProtonBadge({
  game,
  tier,
  compact = false,
}: ProtonBadgeProps) {
  const steamAppId = steamAppIdFromGame(game)
  const reportUrl = steamAppId
    ? `https://www.protondb.com/app/${steamAppId}`
    : null
  const scoreText = formatProtonScore(game.proton_score)
  const title = scoreText
    ? `ProtonDB: ${PROTON_TIER_DESCRIPTIONS[tier]} (${scoreText}/100)`
    : `ProtonDB: ${PROTON_TIER_DESCRIPTIONS[tier]}`
  const className = (
    `proton-badge proton-badge-${tier}${compact ? ' proton-badge-compact' : ''}`
  )
  const tierLabel = compact
    ? PROTON_TIER_LABELS[tier]
    : `Linux ${PROTON_TIER_LABELS[tier]}`
  const label = scoreText ? `${tierLabel} ${scoreText}` : tierLabel
  const content = (
    <>
      <MonitorCheck size={compact ? 10 : 13} aria-hidden="true" />
      <span>{label}</span>
    </>
  )

  if (!reportUrl) {
    return (
      <span className={className} title={title}>
        {content}
      </span>
    )
  }

  return (
    <a
      className={className}
      href={reportUrl}
      target="_blank"
      rel="noopener noreferrer"
      title={title}
    >
      {content}
    </a>
  )
}
