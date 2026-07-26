import { Clock3, ExternalLink } from 'lucide-react'
import { Link } from 'react-router'
import { PlatformIcons } from '../../components/PlatformIcons'
import type { Game } from '../../types/game'
import { formatPlaytimeHours } from '../../utils/playtime'
import { catalogFilterHref, websiteLabel } from './links'
import type { GameDetailModel } from './model'

interface GameDetailHeaderProps {
  game: Game
  model: GameDetailModel
}

export function GameDetailHeader({
  game,
  model,
}: GameDetailHeaderProps) {
  return (
    <>
      <div className="dp-header-meta">
        <span className="dp-release-chip">{model.releaseLabel}</span>
        {game.platforms.length > 0 ? (
          <PlatformIcons
            platforms={game.platforms}
            mode="detail"
            maxVisible={6}
            game={game}
          />
        ) : null}
        {model.playtime.endless || model.playtime.primaryMinutes > 0 ? (
          <span className="dp-header-playtime">
            <Clock3 size={12} aria-hidden="true" />
            {model.playtime.endless
              ? '∞'
              : formatPlaytimeHours(model.playtime.primaryMinutes)}
          </span>
        ) : null}
      </div>

      <h1 className="dp-title">{game.title}</h1>

      {game.developer || model.websiteUrl ? (
        <p className="dp-subtitle">
          {game.developer ? (
            <Link
              className="dp-subtitle-link"
              to={catalogFilterHref('developer', game.developer)}
            >
              {game.developer}
            </Link>
          ) : null}
          {game.publisher && game.publisher !== game.developer
            ? ` · ${game.publisher}`
            : ''}
          {model.websiteUrl ? (
            <>
              {game.developer || game.publisher ? ' · ' : ''}
              <a
                className="dp-subtitle-link"
                href={model.websiteUrl}
                target="_blank"
                rel="noopener noreferrer"
              >
                {websiteLabel(model.websiteUrl)}
                <ExternalLink size={11} aria-hidden="true" />
              </a>
            </>
          ) : null}
        </p>
      ) : null}
    </>
  )
}
