import { ExternalLink } from 'lucide-react'
import type { Game } from '../../types/game'
import { steamAppIdFromGame } from '../../utils/steam'
import { PROTON_TIER_DESCRIPTIONS, PROTON_TIER_LABELS, isProtonTier } from '../../utils/proton'

export function ProtonCompat({ game }: { game: Game }) {
  const tier = game.proton_tier
  if (!tier || !isProtonTier(tier)) return null

  const steamAppId = steamAppIdFromGame(game)
  const reportUrl = steamAppId ? `https://www.protondb.com/app/${steamAppId}` : null

  return (
    <div className="dp-proton" title={PROTON_TIER_DESCRIPTIONS[tier]}>
      <span className={`dp-proton-badge dp-proton-${tier}`}>{PROTON_TIER_LABELS[tier]}</span>
      <span className="dp-proton-detail">
        <strong>{PROTON_TIER_DESCRIPTIONS[tier]}</strong>
      </span>
      {reportUrl && (
        <a className="dp-proton-link" href={reportUrl} target="_blank" rel="noopener noreferrer">
          ProtonDB
          <ExternalLink size={11} aria-hidden="true" />
        </a>
      )}
    </div>
  )
}
