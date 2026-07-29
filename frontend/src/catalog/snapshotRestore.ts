import type { RefObject } from 'react'

import type { CatalogGame } from '../types/game'
import { findGameCardElement, writeCatalogSnapshot, type CatalogSnapshot } from './snapshot'

export interface SnapshotAnchor {
  slug: string
  viewportTop: number
}

export function writeCurrentSnapshot(
  snapshot: CatalogSnapshot,
  scrollY: number,
  mastheadVisible: boolean,
  anchorRef: RefObject<SnapshotAnchor | null>,
): void {
  writeCatalogSnapshot({
    ...snapshot,
    scrollY,
    mastheadVisible,
    focusedGameSlug: anchorRef.current?.slug ?? null,
    focusedGameViewportTop: anchorRef.current?.viewportTop ?? null,
  })
}

export function anchorForGame(game: CatalogGame): SnapshotAnchor {
  const card = findGameCardElement(game.slug)
  return {
    slug: game.slug,
    viewportTop: card?.getBoundingClientRect().top ?? 0,
  }
}

/**
 * React Router restores the document scroll position. This applies one
 * layout-stable correction using the focused card as an anchor.
 */
export function restoreScrollPosition(
  snapshot: CatalogSnapshot,
  lastScrollYRef: RefObject<number>,
): void {
  const nextScrollY = anchoredScrollY(snapshot)
  const previousBehavior = document.documentElement.style.scrollBehavior
  document.documentElement.style.scrollBehavior = 'auto'
  window.scrollTo(0, Math.max(0, nextScrollY))
  document.documentElement.style.scrollBehavior = previousBehavior
  lastScrollYRef.current = window.scrollY
}

function anchoredScrollY(snapshot: CatalogSnapshot): number {
  if (!snapshot.focusedGameSlug || typeof snapshot.focusedGameViewportTop !== 'number') {
    return window.scrollY
  }
  const card = findGameCardElement(snapshot.focusedGameSlug)
  if (!card) return window.scrollY
  return window.scrollY + card.getBoundingClientRect().top - snapshot.focusedGameViewportTop
}
