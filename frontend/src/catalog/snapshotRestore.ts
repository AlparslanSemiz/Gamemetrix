/**
 * Non-hook helpers for catalog back-nav restore.
 *
 * Restore spans two renders: the mount render still holds pre-restore state,
 * then a second render commits the snapshot. `prepareRestoreRefs` primes the
 * signature refs so the fetch/filter-reset effects recognise the restored state
 * as already-applied instead of refetching page 0 and wiping the list.
 */

import type { Dispatch, RefObject, SetStateAction } from 'react'

import type { Game, GameFilters } from '../types/game'
import { findGameCardElement, writeCatalogSnapshot, type CatalogSnapshot } from './snapshot'
import { catalogFilterSignature } from './catalogFetch'
import type { CatalogSnapshotSetters } from './useCatalogSnapshot'

const RESTORE_SETTLE_DELAY_MS = 80

export interface SnapshotAnchor {
  slug: string
  viewportTop: number
}

export interface RestoreRefs {
  filtersRef: RefObject<GameFilters>
  lastFetchSignatureRef: RefObject<string | null>
  lastFilterResetSignatureRef: RefObject<string>
  lastScrollYRef: RefObject<number>
  mastheadVisibleRef: RefObject<boolean>
  restoreInProgressRef: RefObject<boolean>
  snapshotAnchorRef: RefObject<SnapshotAnchor | null>
}

export type RestoreActions = CatalogSnapshotSetters & {
  setHasMore: Dispatch<SetStateAction<boolean>>
  setMastheadVisibility: (next: boolean) => void
  setOffset: Dispatch<SetStateAction<number>>
}

function anchorFromSnapshot(snapshot: CatalogSnapshot): SnapshotAnchor | null {
  if (!snapshot.focusedGameSlug || typeof snapshot.focusedGameViewportTop !== 'number') {
    return null
  }
  return {
    slug: snapshot.focusedGameSlug,
    viewportTop: snapshot.focusedGameViewportTop,
  }
}

export function prepareRestoreRefs(
  snapshot: CatalogSnapshot,
  pendingApply: number,
  refs: RestoreRefs,
): void {
  refs.restoreInProgressRef.current = true
  refs.filtersRef.current = snapshot.filters
  refs.lastFilterResetSignatureRef.current = catalogFilterSignature(
    snapshot.filters,
    pendingApply,
  )
  refs.lastFetchSignatureRef.current = `0:${snapshot.offset}`
  refs.lastScrollYRef.current = snapshot.scrollY
  refs.mastheadVisibleRef.current = snapshot.mastheadVisible
  refs.snapshotAnchorRef.current = anchorFromSnapshot(snapshot)
}

export function applyRestoredState(snapshot: CatalogSnapshot, actions: RestoreActions): void {
  actions.setActivePage(snapshot.activePage)
  actions.setActivePreset(snapshot.activePreset)
  actions.setFilters(snapshot.filters)
  actions.setGames(snapshot.games)
  actions.setCatalogTotal(snapshot.catalogTotal)
  actions.setLibraryTotal(snapshot.libraryTotal)
  actions.setViewMode(snapshot.viewMode)
  actions.setFiltersOpen(snapshot.filtersOpen)
  actions.setOffset(snapshot.offset)
  actions.setHasMore(snapshot.hasMore)
  actions.setMastheadVisibility(snapshot.mastheadVisible)
  actions.setIsLoading(false)
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

export function anchorForGame(game: Game): SnapshotAnchor {
  const card = findGameCardElement(game.slug)
  return {
    slug: game.slug,
    viewportTop: card?.getBoundingClientRect().top ?? 0,
  }
}

/**
 * Scrolls back to the saved position, re-running across the next two frames and
 * once more after a settle delay because images/cards change layout height as
 * they mount. Returns a cleanup that cancels the pending frames/timer.
 */
export function restoreScrollPosition(
  snapshot: CatalogSnapshot,
  lastScrollYRef: RefObject<number>,
): () => void {
  const restorePosition = () => {
    const nextScrollY = anchoredScrollY(snapshot)
    const previousBehavior = document.documentElement.style.scrollBehavior
    document.documentElement.style.scrollBehavior = 'auto'
    window.scrollTo(0, Math.max(0, nextScrollY))
    document.documentElement.style.scrollBehavior = previousBehavior
    lastScrollYRef.current = window.scrollY
  }

  restorePosition()
  const frameIds: number[] = []
  const firstFrame = window.requestAnimationFrame(() => {
    restorePosition()
    frameIds.push(window.requestAnimationFrame(restorePosition))
  })
  frameIds.push(firstFrame)
  const settleTimer = window.setTimeout(restorePosition, RESTORE_SETTLE_DELAY_MS)

  return () => {
    frameIds.forEach((frameId) => window.cancelAnimationFrame(frameId))
    window.clearTimeout(settleTimer)
  }
}

function anchoredScrollY(snapshot: CatalogSnapshot): number {
  if (!snapshot.focusedGameSlug || typeof snapshot.focusedGameViewportTop !== 'number') {
    return snapshot.scrollY
  }
  const card = findGameCardElement(snapshot.focusedGameSlug)
  if (!card) return snapshot.scrollY
  return window.scrollY + card.getBoundingClientRect().top - snapshot.focusedGameViewportTop
}
