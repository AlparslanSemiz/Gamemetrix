import { useEffect, useRef, useState } from 'react'
import {
  Check,
  CheckCircle2,
  ChevronDown,
  Eye,
  Flag,
  FolderPlus,
  Gamepad2,
  Heart,
  Play,
  Share2,
  Star,
} from 'lucide-react'
import { trackProductEvent } from '../../services/analytics'
import type { CollectionKey } from '../../state/collections'
import { useCollectionActions } from '../../state/useCollectionActions'

// The four states that live behind "Save to collection" — the two headline
// actions (library, wishlist) get their own buttons.
const MENU_ITEMS: { key: CollectionKey; label: string; icon: typeof Star }[] = [
  { key: 'playing', label: 'Currently playing', icon: Gamepad2 },
  { key: 'completed', label: 'Completed', icon: Flag },
  { key: 'liked', label: 'Liked', icon: Heart },
  { key: 'favorites', label: 'Favorite', icon: Star },
]

export function CollectionActions({ slug, onOpenTrailer }: { slug: string; onOpenTrailer: () => void }) {
  const { collectionSets, toggle } = useCollectionActions()
  const [menuOpen, setMenuOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) return
    function onPointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false)
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setMenuOpen(false)
    }
    window.addEventListener('mousedown', onPointerDown)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onPointerDown)
      window.removeEventListener('keydown', onKey)
    }
  }, [menuOpen])

  const handleShare = () => {
    void navigator.clipboard.writeText(`${window.location.origin}/game/${slug}`)
      .then(() => setCopied(true))
      .catch(() => undefined)
    trackProductEvent('share', { game_slug: slug, surface: 'game_detail' })
  }

  const inLibrary = collectionSets.seen.has(slug)
  const inWishlist = collectionSets.watchlist.has(slug)
  const savedCount = MENU_ITEMS.filter((item) => collectionSets[item.key].has(slug)).length

  return (
    <div className="dp-actions">
      <button
        type="button"
        className={`dp-btn dp-btn-wide${inLibrary ? ' is-active' : ''}`}
        aria-pressed={inLibrary}
        onClick={() => toggle('seen', slug)}
      >
        {inLibrary ? <Check size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
        {inLibrary ? 'In my games' : 'Add to my games'}
      </button>

      <button
        type="button"
        className={`dp-btn dp-btn-wide${inWishlist ? ' is-active' : ''}`}
        aria-pressed={inWishlist}
        onClick={() => toggle('watchlist', slug)}
      >
        <CheckCircle2 size={15} aria-hidden="true" />
        {inWishlist ? 'On wishlist' : 'Add to wishlist'}
      </button>

      <div className="dp-menu-wrap" ref={menuRef}>
        <button
          type="button"
          className={`dp-btn${savedCount > 0 ? ' is-active' : ''}`}
          aria-expanded={menuOpen}
          aria-haspopup="true"
          onClick={() => setMenuOpen((open) => !open)}
        >
          <FolderPlus size={15} aria-hidden="true" />
          Save to collection
          {savedCount > 0 ? <span className="dp-menu-count">{savedCount}</span> : null}
          <ChevronDown size={13} aria-hidden="true" />
        </button>
        {menuOpen && (
          <div className="dp-menu" role="menu">
            {MENU_ITEMS.map(({ key, label, icon: Icon }) => {
              const active = collectionSets[key].has(slug)
              return (
                <button
                  key={key}
                  type="button"
                  role="menuitemcheckbox"
                  aria-checked={active}
                  className={`dp-menu-item${active ? ' is-active' : ''}`}
                  onClick={() => toggle(key, slug)}
                >
                  <Icon size={15} aria-hidden="true" />
                  <span>{label}</span>
                  {active ? <Check size={14} aria-hidden="true" /> : null}
                </button>
              )
            })}
          </div>
        )}
      </div>

      <button type="button" className="dp-btn dp-btn-primary" onClick={onOpenTrailer}>
        <Play size={14} aria-hidden="true" />
        Trailer
      </button>

      <button
        type="button"
        className="dp-btn dp-btn-icon"
        title={copied ? 'Link copied' : 'Copy link'}
        aria-label="Copy link"
        onClick={handleShare}
      >
        {copied ? <Check size={15} aria-hidden="true" /> : <Share2 size={15} aria-hidden="true" />}
      </button>
    </div>
  )
}
