import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from 'react'

import type { ViewMode } from '../components/CatalogToolbar'
import type { Game, GameFilters } from '../types/game'
import type { ActivePage } from './config'
import { readCatalogSnapshot, type CatalogSnapshot } from './snapshot'
import {
  anchorForGame,
  applyRestoredState,
  prepareRestoreRefs,
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
  games: Game[]
  libraryTotal: number
  viewMode: ViewMode
}

export interface CatalogSnapshotSetters {
  setActivePage: Dispatch<SetStateAction<ActivePage>>
  setActivePreset: Dispatch<SetStateAction<string | null>>
  setCatalogTotal: Dispatch<SetStateAction<number>>
  setFilters: Dispatch<SetStateAction<GameFilters>>
  setFiltersOpen: Dispatch<SetStateAction<boolean>>
  setGames: Dispatch<SetStateAction<Game[]>>
  setIsLoading: Dispatch<SetStateAction<boolean>>
  setLibraryTotal: Dispatch<SetStateAction<number>>
  setViewMode: Dispatch<SetStateAction<ViewMode>>
}

interface UseCatalogSnapshotProps {
  hasUrlFilters: boolean
  pagination: CatalogPagination
  pendingApply: number
  routeInitialPage: ActivePage
  scroll: CatalogScroll
  setters: CatalogSnapshotSetters
  values: CatalogSnapshotValues
}

export function useCatalogSnapshot({
  hasUrlFilters,
  pagination,
  pendingApply,
  routeInitialPage,
  scroll,
  setters,
  values,
}: UseCatalogSnapshotProps) {
  const latestCatalogRef = useRef<CatalogSnapshot | null>(null)
  const snapshotAnchorRef = useRef<SnapshotAnchor | null>(null)
  const restoreInProgressRef = useRef(false)
  const filtersRef = useRef(values.filters)

  const restoredSnapshot = useInitialCatalogRestore({
    filtersRef,
    hasUrlFilters,
    pagination,
    pendingApply,
    restoreInProgressRef,
    routeInitialPage,
    scroll,
    setters,
    snapshotAnchorRef,
  })

  useEffect(() => {
    filtersRef.current = values.filters
  }, [values.filters])

  useLatestCatalogSnapshot(latestCatalogRef, pagination, scroll, snapshotAnchorRef, values)
  const saveCatalogSnapshot = useSnapshotPersistence(
    latestCatalogRef,
    scroll,
    snapshotAnchorRef,
  )
  useRestoredCatalogScroll(restoredSnapshot, scroll)

  return {
    filtersRef,
    restoredSnapshot,
    restoreInProgressRef,
    saveCatalogSnapshot,
    snapshotAnchorRef,
  }
}

interface InitialCatalogRestoreProps {
  filtersRef: RefObject<GameFilters>
  hasUrlFilters: boolean
  pagination: CatalogPagination
  pendingApply: number
  restoreInProgressRef: RefObject<boolean>
  routeInitialPage: ActivePage
  scroll: CatalogScroll
  setters: CatalogSnapshotSetters
  snapshotAnchorRef: RefObject<SnapshotAnchor | null>
}

function useInitialCatalogRestore({
  filtersRef,
  hasUrlFilters,
  pagination,
  pendingApply,
  restoreInProgressRef,
  routeInitialPage,
  scroll,
  setters,
  snapshotAnchorRef,
}: InitialCatalogRestoreProps) {
  const [restoredSnapshot, setRestoredSnapshot] = useState<CatalogSnapshot | null>(null)
  // Captured once: restore must reflect the values at mount, not later edits.
  const initialRestoreRef = useRef({ hasUrlFilters, pendingApply })
  const {
    setActivePage,
    setActivePreset,
    setCatalogTotal,
    setFilters,
    setFiltersOpen,
    setGames,
    setIsLoading,
    setLibraryTotal,
    setViewMode,
  } = setters

  useIsomorphicLayoutEffect(() => {
    const initial = initialRestoreRef.current
    if (routeInitialPage !== 'catalog' || initial.hasUrlFilters) return
    const snapshot = readCatalogSnapshot()
    if (!snapshot?.games.length) return

    prepareRestoreRefs(snapshot, initial.pendingApply, {
      filtersRef,
      lastFetchSignatureRef: pagination.lastFetchSignatureRef,
      lastFilterResetSignatureRef: pagination.lastFilterResetSignatureRef,
      lastScrollYRef: scroll.lastScrollYRef,
      mastheadVisibleRef: scroll.mastheadVisibleRef,
      restoreInProgressRef,
      snapshotAnchorRef,
    })
    applyRestoredState(snapshot, {
      setActivePage,
      setActivePreset,
      setCatalogTotal,
      setFilters,
      setFiltersOpen,
      setGames,
      setHasMore: pagination.setHasMore,
      setIsLoading,
      setLibraryTotal,
      setMastheadVisibility: scroll.setMastheadVisibility,
      setOffset: pagination.setOffset,
      setViewMode,
    })
    setRestoredSnapshot(snapshot)
  }, [
    filtersRef,
    pagination.lastFetchSignatureRef,
    pagination.lastFilterResetSignatureRef,
    pagination.setHasMore,
    pagination.setOffset,
    restoreInProgressRef,
    routeInitialPage,
    scroll.lastScrollYRef,
    scroll.mastheadVisibleRef,
    scroll.setMastheadVisibility,
    setActivePage,
    setActivePreset,
    setCatalogTotal,
    setFilters,
    setFiltersOpen,
    setGames,
    setIsLoading,
    setLibraryTotal,
    setViewMode,
    snapshotAnchorRef,
  ])

  return restoredSnapshot
}

function useLatestCatalogSnapshot(
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
  latestCatalogRef: RefObject<CatalogSnapshot | null>,
  scroll: CatalogScroll,
  snapshotAnchorRef: RefObject<SnapshotAnchor | null>,
) {
  const { lastScrollYRef, mastheadVisibleRef } = scroll

  const saveCatalogSnapshot = useCallback(
    (focusedGame?: Game) => {
      const snapshot = latestCatalogRef.current
      if (!snapshot) return
      const scrollY = window.scrollY
      if (focusedGame) {
        snapshotAnchorRef.current = anchorForGame(focusedGame)
      }
      lastScrollYRef.current = scrollY
      writeCurrentSnapshot(snapshot, scrollY, mastheadVisibleRef.current, snapshotAnchorRef)
    },
    [lastScrollYRef, latestCatalogRef, mastheadVisibleRef, snapshotAnchorRef],
  )

  useEffect(() => {
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
    const previousScrollRestoration = window.history.scrollRestoration
    window.history.scrollRestoration = 'manual'
    window.addEventListener('pagehide', saveSnapshot)
    return () => {
      saveSnapshot()
      window.removeEventListener('pagehide', saveSnapshot)
      window.history.scrollRestoration = previousScrollRestoration
    }
  }, [lastScrollYRef, latestCatalogRef, mastheadVisibleRef, snapshotAnchorRef])

  return saveCatalogSnapshot
}

function useRestoredCatalogScroll(
  restoredSnapshot: CatalogSnapshot | null,
  scroll: CatalogScroll,
) {
  const { lastScrollYRef, mastheadVisibleRef } = scroll
  useIsomorphicLayoutEffect(() => {
    if (!restoredSnapshot?.games.length) return
    mastheadVisibleRef.current = restoredSnapshot.mastheadVisible
    return restoreScrollPosition(restoredSnapshot, lastScrollYRef)
  }, [lastScrollYRef, mastheadVisibleRef, restoredSnapshot])
}

/**
 * Clears the restore guard. Must be called AFTER the fetch and filter-reset
 * effects so those still see the guard set during the settling commit.
 */
export function useCatalogRestoreCompletion(
  restoredSnapshot: CatalogSnapshot | null,
  restoreInProgressRef: RefObject<boolean>,
) {
  useEffect(() => {
    if (restoredSnapshot) restoreInProgressRef.current = false
  }, [restoredSnapshot, restoreInProgressRef])
}
