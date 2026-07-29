import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from 'react'

import type { ViewMode } from '../components/CatalogToolbar'
import { getCatalogGames } from '../services/games'
import type { CatalogGame, GameFilters } from '../types/game'
import type { ActivePage } from './config'
import { PAGE_SIZE } from './config'
import type { CatalogSnapshot } from './snapshot'
import {
  anchorForGame,
  restoreScrollPosition,
  writeCurrentSnapshot,
  type SnapshotAnchor,
} from './snapshotRestore'
import type { CatalogPagination } from './useCatalogPagination'
import type { CatalogScroll } from './useCatalogScroll'

const useIsomorphicLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect

export interface CatalogSnapshotValues {
  activePage: ActivePage
  activePreset: string | null
  catalogTotal: number
  filters: GameFilters
  filtersOpen: boolean
  games: CatalogGame[]
  libraryTotal: number
  viewMode: ViewMode
}

interface UseCatalogSnapshotProps {
  enabled: boolean
  initialSnapshot: CatalogSnapshot | null
  pagination: CatalogPagination
  scroll: CatalogScroll
  values: CatalogSnapshotValues
}

function anchorFromSnapshot(snapshot: CatalogSnapshot | null): SnapshotAnchor | null {
  if (
    !snapshot?.focusedGameSlug
    || typeof snapshot.focusedGameViewportTop !== 'number'
  ) {
    return null
  }
  return {
    slug: snapshot.focusedGameSlug,
    viewportTop: snapshot.focusedGameViewportTop,
  }
}

export function useCatalogSnapshot({
  enabled,
  initialSnapshot,
  pagination,
  scroll,
  values,
}: UseCatalogSnapshotProps) {
  const latestCatalogRef = useRef<CatalogSnapshot | null>(
    enabled ? initialSnapshot : null,
  )
  const snapshotAnchorRef = useRef<SnapshotAnchor | null>(anchorFromSnapshot(initialSnapshot))
  const restoreInProgressRef = useRef(false)
  const filtersRef = useRef(values.filters)

  useEffect(() => {
    filtersRef.current = values.filters
  }, [values.filters])

  useLatestCatalogSnapshot(
    enabled,
    latestCatalogRef,
    pagination,
    scroll,
    snapshotAnchorRef,
    values,
  )
  const saveCatalogSnapshot = useSnapshotPersistence(
    enabled,
    latestCatalogRef,
    scroll,
    snapshotAnchorRef,
  )
  useRestoredCatalogScroll(initialSnapshot, scroll, snapshotAnchorRef)

  return {
    filtersRef,
    restoreInProgressRef,
    saveCatalogSnapshot,
    snapshotAnchorRef,
  }
}

function useLatestCatalogSnapshot(
  enabled: boolean,
  latestCatalogRef: RefObject<CatalogSnapshot | null>,
  pagination: CatalogPagination,
  scroll: CatalogScroll,
  snapshotAnchorRef: RefObject<SnapshotAnchor | null>,
  values: CatalogSnapshotValues,
) {
  const {
    activePage,
    activePreset,
    catalogTotal,
    filters,
    filtersOpen,
    games,
    libraryTotal,
    viewMode,
  } = values

  useEffect(() => {
    if (!enabled) {
      latestCatalogRef.current = null
      return
    }
    latestCatalogRef.current = {
      version: 1,
      savedAt: Date.now(),
      activePage,
      activePreset,
      catalogTotal,
      filters,
      filtersOpen,
      games,
      libraryTotal,
      viewMode,
      offset: pagination.offset,
      hasMore: pagination.hasMore,
      scrollY: window.scrollY,
      mastheadVisible: scroll.mastheadVisible,
      focusedGameSlug: snapshotAnchorRef.current?.slug ?? null,
      focusedGameViewportTop: snapshotAnchorRef.current?.viewportTop ?? null,
    }
  }, [
    activePage,
    activePreset,
    catalogTotal,
    enabled,
    filters,
    filtersOpen,
    games,
    latestCatalogRef,
    libraryTotal,
    pagination.hasMore,
    pagination.offset,
    scroll.mastheadVisible,
    snapshotAnchorRef,
    viewMode,
  ])
}

function useSnapshotPersistence(
  enabled: boolean,
  latestCatalogRef: RefObject<CatalogSnapshot | null>,
  scroll: CatalogScroll,
  snapshotAnchorRef: RefObject<SnapshotAnchor | null>,
) {
  const { lastScrollYRef, mastheadVisibleRef } = scroll

  const saveCatalogSnapshot = useCallback(
    (focusedGame?: CatalogGame) => {
      if (!enabled) return
      const snapshot = latestCatalogRef.current
      if (!snapshot) return
      const scrollY = window.scrollY
      if (focusedGame) snapshotAnchorRef.current = anchorForGame(focusedGame)
      lastScrollYRef.current = scrollY
      writeCurrentSnapshot(snapshot, scrollY, mastheadVisibleRef.current, snapshotAnchorRef)
    },
    [enabled, lastScrollYRef, latestCatalogRef, mastheadVisibleRef, snapshotAnchorRef],
  )

  useEffect(() => {
    if (!enabled) return
    const saveSnapshot = () => {
      const snapshot = latestCatalogRef.current
      if (!snapshot) return
      writeCurrentSnapshot(
        snapshot,
        lastScrollYRef.current,
        mastheadVisibleRef.current,
        snapshotAnchorRef,
      )
    }
    window.addEventListener('pagehide', saveSnapshot)
    return () => {
      saveSnapshot()
      window.removeEventListener('pagehide', saveSnapshot)
    }
  }, [enabled, lastScrollYRef, latestCatalogRef, mastheadVisibleRef, snapshotAnchorRef])

  return saveCatalogSnapshot
}

function useRestoredCatalogScroll(
  initialSnapshot: CatalogSnapshot | null,
  scroll: CatalogScroll,
  snapshotAnchorRef: RefObject<SnapshotAnchor | null>,
) {
  const { lastScrollYRef, mastheadVisibleRef } = scroll
  useIsomorphicLayoutEffect(() => {
    if (!initialSnapshot?.games.length) return
    mastheadVisibleRef.current = initialSnapshot.mastheadVisible
    if (
      !initialSnapshot.focusedGameSlug
      || typeof initialSnapshot.focusedGameViewportTop !== 'number'
    ) return
    restoreScrollPosition(initialSnapshot, lastScrollYRef)
    snapshotAnchorRef.current = null
  }, [initialSnapshot, lastScrollYRef, mastheadVisibleRef, snapshotAnchorRef])
}

interface CatalogBackgroundRefreshProps {
  enabled: boolean
  snapshot: CatalogSnapshot | null
  setCatalogTotal: Dispatch<SetStateAction<number>>
  setGames: Dispatch<SetStateAction<CatalogGame[]>>
}

export function useCatalogBackgroundRefresh({
  enabled,
  snapshot,
  setCatalogTotal,
  setGames,
}: CatalogBackgroundRefreshProps) {
  useEffect(() => {
    if (!enabled || !snapshot?.games.length) return
    let active = true
    let timerId: number | null = null
    const frameId = window.requestAnimationFrame(() => {
      timerId = window.setTimeout(() => {
        void getCatalogGames(snapshot.filters, PAGE_SIZE, 0)
          .then((response) => {
            if (!active) return
            const refreshedBySlug = new Map(response.games.map((game) => [game.slug, game]))
            setGames((current) => current.map((game) => refreshedBySlug.get(game.slug) ?? game))
            setCatalogTotal(response.total)
          })
          .catch(() => undefined)
      }, 0)
    })
    return () => {
      active = false
      window.cancelAnimationFrame(frameId)
      if (timerId !== null) window.clearTimeout(timerId)
    }
  }, [enabled, setCatalogTotal, setGames, snapshot])
}
