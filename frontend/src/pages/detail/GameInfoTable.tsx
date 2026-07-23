import { ExternalLink, Info } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { PlatformIcons } from '../../components/PlatformIcons'
import type { Game } from '../../types/game'
import { formatPlaytimeHours } from '../../utils/playtime'
import { catalogFilterHref } from './links'
import type { GameDetailModel } from './model'

interface GameInfoTableProps {
  game: Game
  model: GameDetailModel
}

export function GameInfoTable({ game, model }: GameInfoTableProps) {
  return (
    <div className="dp-section">
      <div className="dp-info-table">
        <CatalogMetadataRows game={game} />
        <GameplayMetadataRows game={game} model={model} />
      </div>
      <p className="dp-attribution">
        Metadata and imagery may include attributed data from{' '}
        <a href="https://rawg.io/" target="_blank" rel="noopener noreferrer">
          RAWG
        </a>.
      </p>
    </div>
  )
}

function CatalogMetadataRows({ game }: { game: Game }) {
  return (
    <>
      {game.platforms.length > 0 ? (
        <InfoRow label="Platforms">
          <PlatformIcons platforms={game.platforms} mode="detail" game={game} />
        </InfoRow>
      ) : null}
      {game.developer ? (
        <InfoRow label="Developer">
          <Link className="dp-info-link" to={catalogFilterHref('developer', game.developer)}>
            {game.developer}
          </Link>
        </InfoRow>
      ) : null}
      {game.publisher && game.publisher !== game.developer ? (
        <InfoRow label="Publisher">
          <Link className="dp-info-link" to={catalogFilterHref('publisher', game.publisher)}>
            {game.publisher}
          </Link>
        </InfoRow>
      ) : null}
      {game.genres.length > 0 ? (
        <InfoRow label="Genre">
          {game.genres.map((genre, index) => (
            <span key={genre}>
              {index > 0 ? ', ' : ''}
              <Link className="dp-info-link" to={catalogFilterHref('genre', genre)}>
                {genre}
              </Link>
            </span>
          ))}
        </InfoRow>
      ) : null}
      {game.franchise ? <InfoRow label="Series">{game.franchise}</InfoRow> : null}
    </>
  )
}

function GameplayMetadataRows({
  game,
  model,
}: GameInfoTableProps) {
  return (
    <>
      <InfoRow label="Release date">
        <ReleaseValue label={model.primaryReleaseLabel} year={game.release_year} />
        {model.earlyAccessSuffix}
      </InfoRow>
      {model.gameModes.length > 0 ? (
        <InfoRow label="Game modes">{model.gameModes.map(formatGameMode).join(', ')}</InfoRow>
      ) : null}
      {model.playtime.endless || model.playtime.hasData ? (
        <InfoRow label="How long to beat"><PlaytimeValue model={model} /></InfoRow>
      ) : null}
      {game.goty_year ? (
        <InfoRow label="GOTY">
          <Link className="dp-info-link" to={catalogFilterHref('year', game.goty_year)}>
            {game.goty_year}
          </Link>
        </InfoRow>
      ) : null}
      {model.protonText ? (
        <InfoRow label="ProtonDB">
          <a className={`dp-info-link dp-proton-tier dp-proton-${game.proton_tier ?? 'unknown'}`} href={model.protonUrl} target="_blank" rel="noopener noreferrer">
            {model.protonText}
            <ExternalLink size={11} aria-hidden="true" />
          </a>
        </InfoRow>
      ) : null}
    </>
  )
}

function InfoRow({
  children,
  label,
}: {
  children: ReactNode
  label: string
}) {
  return (
    <div className="dp-info-row">
      <span className="dp-info-key">{label}</span>
      <span className="dp-info-val">{children}</span>
    </div>
  )
}

function ReleaseValue({ label, year }: { label: string; year: number }) {
  const yearText = String(year)
  const yearIndex = year > 1970 ? label.indexOf(yearText) : -1
  if (yearIndex === -1) return <>{label}</>
  return (
    <>
      {label.slice(0, yearIndex)}
      <Link
        className="dp-info-link"
        to={catalogFilterHref('year', year)}
      >
        {yearText}
      </Link>
      {label.slice(yearIndex + yearText.length)}
    </>
  )
}

function PlaytimeValue({ model }: { model: GameDetailModel }) {
  const playtime = model.playtime
  if (playtime.endless) {
    return (
      <span
        className="dp-hltb-endless"
        title="Endlessly replayable — no fixed completion time"
      >
        ∞
      </span>
    )
  }

  return (
    <span className="dp-hltb">
      {playtime.url ? (
        <a
          className="dp-info-link"
          href={playtime.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {formatPlaytimeHours(playtime.primaryMinutes)}
          <ExternalLink size={11} aria-hidden="true" />
        </a>
      ) : (
        formatPlaytimeHours(playtime.primaryMinutes)
      )}
      {playtime.detailRows.length > 0 ? (
        <button
          type="button"
          className="dp-hltb-info"
          aria-label="Other playtimes"
          aria-describedby="game-hltb-tooltip"
        >
          <Info size={12} aria-hidden="true" />
          <span
            id="game-hltb-tooltip"
            className="dp-hltb-tip"
            role="tooltip"
          >
            {playtime.detailRows.map(([label, minutes]) => (
              <span className="dp-hltb-tip-row" key={label}>
                <span>{label}</span>
                <span>{formatPlaytimeHours(Number(minutes))}</span>
              </span>
            ))}
          </span>
        </button>
      ) : null}
    </span>
  )
}

function formatGameMode(mode: string): string {
  return mode.charAt(0).toUpperCase() + mode.slice(1)
}
