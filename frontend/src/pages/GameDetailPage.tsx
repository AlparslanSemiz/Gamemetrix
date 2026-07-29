import { useEffect, useRef, useState, type RefObject } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { SeriesRow } from '../components/SeriesRow'
import { TrailerModal } from '../components/TrailerModal'
import type { Game, SeriesGameItem } from '../types/game'
import { CollectionActions } from './detail/CollectionActions'
import { DlcSection } from './detail/DlcSection'
import { Gallery } from './detail/Gallery'
import { GameDetailHeader } from './detail/GameDetailHeader'
import { GameInfoTable } from './detail/GameInfoTable'
import { GameRatingsPanel } from './detail/GameRatingsPanel'
import { GameScoreSummary } from './detail/GameScoreSummary'
import { buildGameDetailModel } from './detail/model'
import { PricePanel } from './detail/PricePanel'
import { SimilarGamesSection } from './detail/SimilarGamesSection'
import { SysReqPanel } from './detail/SysReqPanel'
import {
  useGameDetailGame,
  useGameTrailer,
  useSimilarGames,
} from './detail/useGameDetailData'
import './GameDetailPage.css'

export function GameDetailPage({ initialGame }: { initialGame?: Game }) {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const { error, game } = useGameDetailGame(slug, initialGame)
  const related = useNearViewport(slug)
  const similar = useSimilarGames(slug, initialGame, related.enabled)
  const trailer = useGameTrailer(game)

  const goBackToCatalog = () => {
    if (window.history.length > 1) navigate(-1)
    else navigate('/')
  }

  if (error) {
    return (
      <div className="dp-shell">
        <div className="dp-inner">
          <button
            type="button"
            className="dp-back"
            onClick={goBackToCatalog}
          >
            ← Back
          </button>
          <p className="dp-msg">{error}</p>
        </div>
      </div>
    )
  }

  if (!game) {
    return (
      <div className="dp-shell">
        <p className="dp-msg">Loading…</p>
      </div>
    )
  }

  const model = buildGameDetailModel(game)

  return (
    <main className="dp-shell" style={model.detailStyle}>
      {model.backgroundImage ? (
        <div
          className="dp-bg"
          style={{ backgroundImage: `url("${model.backgroundImage}")` }}
        />
      ) : null}
      <div className="dp-bg-overlay" />

      <GameDetailContent
        game={game}
        model={model}
        onOpenTrailer={trailer.openTrailer}
        relatedEnabled={related.enabled}
        relatedRef={related.ref}
        similarGames={similar.games}
        similarLoading={similar.loading}
      />

      {trailer.open ? (
        <TrailerModal
          title={game.title}
          videoId={trailer.videoId}
          loading={trailer.loading}
          onClose={trailer.closeTrailer}
        />
      ) : null}
    </main>
  )
}

function GameDetailContent({
  game,
  model,
  onOpenTrailer,
  relatedEnabled,
  relatedRef,
  similarGames,
  similarLoading,
}: {
  game: Game
  model: ReturnType<typeof buildGameDetailModel>
  onOpenTrailer: () => void
  relatedEnabled: boolean
  relatedRef: RefObject<HTMLDivElement | null>
  similarGames: SeriesGameItem[]
  similarLoading: boolean
}) {
  const hasSimilarGames = (
    game.similar_games.length > 0
    || similarGames.length > 0
    || similarLoading
  )
  return (
    <div className="dp-inner">
      <nav className="dp-breadcrumb" aria-label="Breadcrumb">
        <Link to="/" className="dp-bc-item dp-bc-link">Home</Link>
        <span className="dp-bc-sep">/</span>
        <span className="dp-bc-item dp-bc-current" aria-current="page">{game.title}</span>
      </nav>
      <div className="dp-grid">
        <div className="dp-left">
          <GameDetailHeader game={game} model={model} />
          <CollectionActions slug={game.slug} onOpenTrailer={onOpenTrailer} />
          <GameScoreSummary game={game} />
          <GameRatingsPanel game={game} />
          <AboutSection paragraphs={model.aboutParagraphs} />
          <GameInfoTable game={game} model={model} />
          <SystemRequirements game={game} />
        </div>
        <div className="dp-right">
          <div className="dp-gallery-panel"><Gallery game={game} /></div>
          {model.priceSnapshots.length > 0 ? (
            <div className="dp-side-panel">
              <h2 className="dp-section-title">Where to buy</h2>
              <PricePanel prices={model.priceSnapshots} game={game} />
            </div>
          ) : null}
          <DlcSection game={game} />
        </div>
      </div>
      <div className="dp-related-lazy" ref={relatedRef}>
        <SeriesRow enabled={relatedEnabled} slug={game.slug} />
        {hasSimilarGames ? (
          <div className="dp-bottom-related">
            <SimilarGamesSection game={game} catalogGames={similarGames} loading={similarLoading} />
          </div>
        ) : null}
      </div>
    </div>
  )
}

function useNearViewport(key: string | undefined) {
  const ref = useRef<HTMLDivElement>(null)
  const [visibility, setVisibility] = useState({ key, enabled: false })
  const enabled = visibility.key === key && visibility.enabled

  useEffect(() => {
    if (enabled) return
    const element = ref.current
    if (!element) return
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry?.isIntersecting) return
        setVisibility({ key, enabled: true })
        observer.disconnect()
      },
      { rootMargin: '600px 0px' },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [enabled, key])

  return { enabled, ref }
}

function AboutSection({ paragraphs }: { paragraphs: string[] }) {
  if (paragraphs.length === 0) return null
  return (
    <div className="dp-section">
      <h2 className="dp-section-title">About</h2>
      <div className="dp-description">
        {paragraphs.map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </div>
    </div>
  )
}

function SystemRequirements({ game }: { game: Game }) {
  if (game.system_requirements.length === 0) return null
  return (
    <div className="dp-section">
      <h2 className="dp-section-title">System requirements</h2>
      <SysReqPanel requirements={game.system_requirements} />
    </div>
  )
}
