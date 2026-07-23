import { memo, type SyntheticEvent } from 'react'
import { trackProductEvent } from '../services/analytics'
import { fallbackCoverUrl } from '../utils/coverImage'
import { CompactGameCard } from './game-card/CompactGameCard'
import { ListGameCard } from './game-card/ListGameCard'
import { buildGameCardModel } from './game-card/model'
import type { GameCardProps } from './game-card/types'

export const GameCard = memo(function GameCard({
  compact = false,
  ...props
}: GameCardProps) {
  const model = buildGameCardModel(props.game)

  const handleCoverError = (event: SyntheticEvent<HTMLImageElement>) => {
    const fallback = fallbackCoverUrl(props.game.title)
    if (event.currentTarget.src !== fallback) {
      event.currentTarget.src = fallback
    }
  }

  const handleShare = () => {
    void navigator.clipboard
      .writeText(`${window.location.origin}/game/${props.game.slug}`)
      .catch(() => undefined)
    trackProductEvent('share', {
      game_slug: props.game.slug,
      surface: 'game_card',
    })
  }

  const viewProps = {
    ...props,
    model,
    onCoverError: handleCoverError,
    onShare: handleShare,
  }
  return compact
    ? <CompactGameCard {...viewProps} compact />
    : <ListGameCard {...viewProps} />
})
