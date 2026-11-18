import { useEffect, useRef, useState } from 'react'
import {
  Bookmark,
  Check,
  ChevronDown,
  CirclePause,
  CircleX,
  FolderPlus,
  Gamepad2,
  Heart,
  History,
  Share2,
  Star,
  Trophy,
  type LucideIcon,
} from 'lucide-react'
import type { CollectionKey } from '../../state/collections'
import type { GameCardCollectionState } from './types'

interface ListAction {
  collection: CollectionKey
  icon: LucideIcon
  label: string
  stateKey: keyof GameCardCollectionState
}

// The wishlist is the headline action and keeps its own labelled button; every
// other list lives behind one "Lists" menu so no card carries a row of
// unlabelled icons.
const MENU_ACTIONS: ListAction[] = [
  { collection: 'playing', icon: Gamepad2, label: 'Currently playing', stateKey: 'isPlaying' },
  { collection: 'seen', icon: History, label: 'Played', stateKey: 'isSeen' },
  { collection: 'completed', icon: Trophy, label: 'Completed', stateKey: 'isCompleted' },
  { collection: 'on_hold', icon: CirclePause, label: 'On hold', stateKey: 'isOnHold' },
  { collection: 'dropped', icon: CircleX, label: 'Dropped', stateKey: 'isDropped' },
  { collection: 'liked', icon: Heart, label: 'Liked', stateKey: 'isLiked' },
  { collection: 'favorites', icon: Star, label: 'Favorite', stateKey: 'isFavorite' },
]

interface GameCardActionsProps extends GameCardCollectionState {
  compact?: boolean
  slug: string
  onShare: () => void
  onToggleCollection: (collection: CollectionKey, slug: string) => void
}

function useDismissableMenu() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    window.addEventListener('mousedown', onPointerDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onPointerDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])
  return { open, ref, setOpen }
}

export function GameCardActions({
  compact = false,
  slug,
  onShare,
  onToggleCollection,
  ...collectionState
}: GameCardActionsProps) {
  const iconSize = compact ? 16 : 20
  const { open: menuOpen, ref: menuRef, setOpen: setMenuOpen } = useDismissableMenu()
  const savedCount = MENU_ACTIONS.filter((action) => collectionState[action.stateKey]).length
  const wishlisted = collectionState.isWatchlisted

  return (
    <>
      <button
        type="button"
        data-action="watchlist"
        className={wishlisted ? 'is-active' : undefined}
        title={wishlisted ? 'Remove from wishlist' : 'Add to wishlist'}
        aria-pressed={wishlisted}
        onClick={() => onToggleCollection('watchlist', slug)}
      >
        <Bookmark size={iconSize} aria-hidden="true" />
        <span className="action-label">{wishlisted ? 'Wishlisted' : 'Wishlist'}</span>
      </button>
      <div className={`card-lists${compact ? ' card-lists-compact' : ''}`} ref={menuRef}>
        <button
          type="button"
          data-action="lists"
          className={savedCount > 0 ? 'is-active' : undefined}
          title="Add to a list"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          <FolderPlus size={iconSize} aria-hidden="true" />
          <span className="action-label">
            {savedCount > 0 ? `Lists (${savedCount})` : 'Lists'}
            <ChevronDown size={10} aria-hidden="true" />
          </span>
        </button>
        {menuOpen ? (
          <div className="card-lists-menu" role="menu" aria-label="Add to a list">
            {MENU_ACTIONS.map(({ collection, icon: Icon, label, stateKey }) => {
              const active = collectionState[stateKey]
              return (
                <button
                  key={collection}
                  type="button"
                  role="menuitemcheckbox"
                  aria-checked={active}
                  data-action={collection}
                  className={active ? 'is-active' : undefined}
                  onClick={() => onToggleCollection(collection, slug)}
                >
                  <Icon size={15} aria-hidden="true" />
                  <span>{label}</span>
                  {active ? <Check size={13} aria-hidden="true" /> : null}
                </button>
              )
            })}
          </div>
        ) : null}
      </div>
      <button
        type="button"
        data-action="share"
        title="Copy link"
        onClick={onShare}
      >
        <Share2 size={iconSize} aria-hidden="true" />
        <span className="action-label">Share</span>
      </button>
    </>
  )
}
