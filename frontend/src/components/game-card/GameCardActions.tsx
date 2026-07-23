import {
  CheckCircle2,
  Eye,
  Flag,
  Gamepad2,
  Heart,
  Share2,
  Star,
  type LucideIcon,
} from 'lucide-react'
import type { CollectionKey } from '../../state/collections'
import type { GameCardCollectionState } from './types'

interface CollectionAction {
  collection: CollectionKey
  compactSecondary: boolean
  icon: LucideIcon
  stateKey: keyof GameCardCollectionState
  title: string
}

const COLLECTION_ACTIONS: CollectionAction[] = [
  {
    collection: 'watchlist',
    compactSecondary: false,
    icon: CheckCircle2,
    stateKey: 'isWatchlisted',
    title: 'Add to wishlist',
  },
  {
    collection: 'playing',
    compactSecondary: false,
    icon: Gamepad2,
    stateKey: 'isPlaying',
    title: 'Currently playing',
  },
  {
    collection: 'seen',
    compactSecondary: false,
    icon: Eye,
    stateKey: 'isSeen',
    title: 'Mark as played',
  },
  {
    collection: 'completed',
    compactSecondary: true,
    icon: Flag,
    stateKey: 'isCompleted',
    title: 'Mark as completed',
  },
  {
    collection: 'liked',
    compactSecondary: true,
    icon: Heart,
    stateKey: 'isLiked',
    title: 'Like',
  },
  {
    collection: 'favorites',
    compactSecondary: true,
    icon: Star,
    stateKey: 'isFavorite',
    title: 'Add to favorites',
  },
]

interface GameCardActionsProps extends GameCardCollectionState {
  compact?: boolean
  slug: string
  onShare: () => void
  onToggleCollection: (collection: CollectionKey, slug: string) => void
}

export function GameCardActions({
  compact = false,
  slug,
  onShare,
  onToggleCollection,
  ...collectionState
}: GameCardActionsProps) {
  const iconSize = compact ? 17 : 20

  return (
    <>
      {COLLECTION_ACTIONS.map((action) => {
        const Icon = action.icon
        const isActive = collectionState[action.stateKey]
        const className = [
          compact && action.compactSecondary ? 'compact-secondary' : '',
          isActive ? 'is-active' : '',
        ].filter(Boolean).join(' ')
        return (
          <button
            key={action.collection}
            type="button"
            data-action={action.collection}
            className={className || undefined}
            title={action.title}
            onClick={() => onToggleCollection(action.collection, slug)}
          >
            <Icon size={iconSize} aria-hidden="true" />
          </button>
        )
      })}
      <button
        type="button"
        data-action="share"
        className={compact ? 'compact-secondary' : undefined}
        title="Copy link"
        onClick={onShare}
      >
        <Share2 size={iconSize} aria-hidden="true" />
      </button>
    </>
  )
}
