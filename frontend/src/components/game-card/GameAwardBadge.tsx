import { Medal, Trophy } from 'lucide-react'
import type { Game } from '../../types/game'

interface GameAwardBadgeProps {
  compact?: boolean
  game: Game
}

export function GameAwardBadge({
  compact = false,
  game,
}: GameAwardBadgeProps) {
  if (!game.goty_year && !(game.award_count > 0)) return null

  const iconSize = compact ? 10 : 11
  return (
    <div className={compact ? 'compact-award' : 'award-badge'}>
      <Trophy size={compact ? 9 : 11} aria-hidden="true" />
      {compact ? (
        game.goty_year
          ? ` GOTY ${game.goty_year}`
          : ` ${game.award_count} awards`
      ) : (
        <span>
          {game.goty_year
            ? `GOTY ${game.goty_year}`
            : `${game.award_count} awards`}
        </span>
      )}
      <div className="award-tooltip">
        <AwardDetails game={game} iconSize={iconSize} />
      </div>
    </div>
  )
}

function AwardDetails({
  game,
  iconSize,
}: {
  game: Game
  iconSize: number
}) {
  if (game.awards?.length > 0) {
    return game.awards.map((award) => (
      <div key={award} className="award-tooltip-item">
        <Trophy size={iconSize} aria-hidden="true" />
        {award}
      </div>
    ))
  }

  return (
    <>
      {game.goty_year ? (
        <div className="award-tooltip-item">
          <Trophy size={iconSize} aria-hidden="true" />
          Game of the Year {game.goty_year}
        </div>
      ) : null}
      {game.award_count > 0 ? (
        <div className="award-tooltip-item">
          <Medal size={iconSize} aria-hidden="true" />
          {game.award_count} major awards
        </div>
      ) : null}
      {game.award_nominations > 0 ? (
        <div className="award-tooltip-item">
          <Medal size={iconSize} aria-hidden="true" />
          {game.award_nominations} nominations
        </div>
      ) : null}
    </>
  )
}
