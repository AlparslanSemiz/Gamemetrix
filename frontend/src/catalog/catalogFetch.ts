/**
 * Non-hook catalog page loading: request, apply, prefetch.
 *
 * `startCatalogPageLoad` is written as an effect body — it returns a cleanup
 * that marks the in-flight request inactive and, when the request never
 * settled, clears the fetch signature so a remount refetches the same page.
 */

import type { Dispatch, RefObject, SetStateAction } from 'react'

import { getCatalogGames } from '../services/games'
import type { CatalogGame, GameFilters } from '../types/game'
import { PAGE_SIZE } from './config'

export interface PrefetchedPage {
  offset: number
  request: Promise<{ games: CatalogGame[]; total: number }>
}

/** Identity of a filter set; a change means the list must reset to page 0. */
export function catalogFilterSignature(filters: GameFilters, pendingApply: number): string {
  return JSON.stringify([
    filters.q,
    filters.genre,
    filters.platform,
    filters.developer,
    filters.publisher,
    filters.minRatings,
    filters.minLiveSources,
    filters.requireCritic,
    filters.sort,
    filters.direction,
    pendingApply,
  ])
}

export interface StartCatalogPageLoadProps {
  catalogTotal: number
  fetchKey: number
  filtersRef: RefObject<GameFilters>
  lastFetchSignatureRef: RefObject<string | null>
  offset: number
  prefetchRef: RefObject<PrefetchedPage | null>
  restoreInProgressRef: RefObject<boolean>
  setCatalogTotal: Dispatch<SetStateAction<number>>
  setError: Dispatch<SetStateAction<string | null>>
  setGames: Dispatch<SetStateAction<CatalogGame[]>>
  setHasMore: Dispatch<SetStateAction<boolean>>
  setIsLoading: Dispatch<SetStateAction<boolean>>
  setIsLoadingMore: Dispatch<SetStateAction<boolean>>
  setLoadMoreError: Dispatch<SetStateAction<string | null>>
}

export function startCatalogPageLoad(props: StartCatalogPageLoadProps): (() => void) | undefined {
  // Mid-restore the effect still sees pre-restore offset/filters; syncing the
  // signature without fetching stops it wiping the restored multi-page list.
  if (props.restoreInProgressRef.current) {
    props.lastFetchSignatureRef.current = `${props.fetchKey}:${props.offset}`
    return
  }
  if (props.offset > 0 && props.catalogTotal > 0 && props.offset >= props.catalogTotal) {
    props.setHasMore(false)
    props.setIsLoadingMore(false)
    props.setLoadMoreError(null)
    return
  }

  const fetchSignature = `${props.fetchKey}:${props.offset}`
  if (props.lastFetchSignatureRef.current === fetchSignature) return
  props.lastFetchSignatureRef.current = fetchSignature

  let active = true
  let settled = false
  const activeFilters = props.filtersRef.current
  const isFirstPage = props.offset === 0

  if (isFirstPage) {
    props.setIsLoading(true)
    props.setGames([])
  } else {
    props.setIsLoadingMore(true)
  }
  props.setLoadMoreError(null)
  props.setError(null)

  const applyPage = (pageGames: CatalogGame[], total: number) => {
    settled = true
    applyLoadedPage({
      activeFilters,
      isActive: () => active,
      isFirstPage,
      offset: props.offset,
      pageGames,
      prefetchRef: props.prefetchRef,
      setCatalogTotal: props.setCatalogTotal,
      setGames: props.setGames,
      setHasMore: props.setHasMore,
      setIsLoading: props.setIsLoading,
      setIsLoadingMore: props.setIsLoadingMore,
      setLoadMoreError: props.setLoadMoreError,
      total,
    })
  }

  const handleError = () => {
    settled = true
    if (!active) return
    if (isFirstPage) {
      props.setGames([])
      props.setIsLoading(false)
      props.setError('GameMetrix API is not reachable yet.')
    } else {
      props.setHasMore(false)
      props.setIsLoadingMore(false)
      props.setLoadMoreError('More games could not be loaded. Check your connection and try again.')
    }
  }

  void requestCatalogPage(
    activeFilters,
    props.offset,
    isFirstPage,
    props.prefetchRef,
    applyPage,
    handleError,
  )

  return () => {
    active = false
    if (!settled) props.lastFetchSignatureRef.current = null
  }
}

async function requestCatalogPage(
  filters: GameFilters,
  offset: number,
  isFirstPage: boolean,
  prefetchRef: RefObject<PrefetchedPage | null>,
  onSuccess: (games: CatalogGame[], total: number) => void,
  onError: () => void,
) {
  const cached = prefetchRef.current
  try {
    const response = !isFirstPage && cached?.offset === offset
      ? await cached.request
      : await getCatalogGames(filters, PAGE_SIZE, offset)
    if (cached?.offset === offset) prefetchRef.current = null
    onSuccess(response.games, response.total)
  } catch {
    if (cached?.offset === offset) prefetchRef.current = null
    onError()
  }
}

interface ApplyLoadedPageProps {
  activeFilters: GameFilters
  isActive: () => boolean
  isFirstPage: boolean
  offset: number
  pageGames: CatalogGame[]
  prefetchRef: RefObject<PrefetchedPage | null>
  setCatalogTotal: Dispatch<SetStateAction<number>>
  setGames: Dispatch<SetStateAction<CatalogGame[]>>
  setHasMore: Dispatch<SetStateAction<boolean>>
  setIsLoading: Dispatch<SetStateAction<boolean>>
  setIsLoadingMore: Dispatch<SetStateAction<boolean>>
  setLoadMoreError: Dispatch<SetStateAction<string | null>>
  total: number
}

function applyLoadedPage({
  activeFilters,
  isActive,
  isFirstPage,
  offset,
  pageGames,
  prefetchRef,
  setCatalogTotal,
  setGames,
  setHasMore,
  setIsLoading,
  setIsLoadingMore,
  setLoadMoreError,
  total,
}: ApplyLoadedPageProps) {
  if (!isActive()) return
  setGames((current) => (isFirstPage ? pageGames : [...current, ...pageGames]))
  setCatalogTotal(total)

  const loadedCount = offset + pageGames.length
  setHasMore(pageGames.length > 0 && loadedCount < total)
  setLoadMoreError(null)
  if (isFirstPage) setIsLoading(false)
  else setIsLoadingMore(false)

  if (pageGames.length > 0) {
    prefetchNextPage(activeFilters, loadedCount, total, isActive, prefetchRef)
  }
}

function prefetchNextPage(
  filters: GameFilters,
  offset: number,
  total: number,
  isActive: () => boolean,
  prefetchRef: RefObject<PrefetchedPage | null>,
) {
  if (offset >= total) return
  const request = getCatalogGames(filters, PAGE_SIZE, offset)
  prefetchRef.current = { offset, request }
  void request.catch(() => {
    if (isActive() && prefetchRef.current?.request === request) {
      prefetchRef.current = null
    }
  })
}
