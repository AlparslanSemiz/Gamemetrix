import { ExternalLink } from 'lucide-react'
import type { Game, ProtonTier } from '../../types/game'
import { steamAppIdFromGame } from '../../utils/steam'

const TIER_LABELS: Record<ProtonTier, string> = {
  platinum: 'Platinum',
  gold: 'Gold',
  silver: 'Silver',
  bronze: 'Bronze',
  borked: 'Borked',
}

const TIER_DESCRIPTIONS: Record<ProtonTier, string> = {
  platinum: 'Runs perfectly out of the box',
  gold: 'Runs perfectly after tweaks',
  silver: 'Runs with minor issues',
  bronze: 'Runs, but crashes often or has major issues',
  borked: 'Does not run',
}

function isProtonTier(value: string): value is ProtonTier {
  return value in TIER_LABELS
}

export function ProtonCompat({ game }: { game: Game }) {
  const tier = game.proton_tier
  if (!tier || !isProtonTier(tier)) return null

  const steamAppId = steamAppIdFromGame(game)
  const reportUrl = steamAppId ? `https://www.protondb.com/app/${steamAppId}` : null

  return (
    <div className="dp-proton" title={TIER_DESCRIPTIONS[tier]}>
      <span className={`dp-proton-badge dp-proton-${tier}`}>{TIER_LABELS[tier]}</span>
      <span className="dp-proton-detail">
        <strong>{TIER_DESCRIPTIONS[tier]}</strong>
        {typeof game.proton_score === 'number' && (
          <small>{Math.round(game.proton_score)}/100 community report score</small>
        )}
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
