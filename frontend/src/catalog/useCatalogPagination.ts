import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from 'react'

import type { CatalogGame, GameFilters } from '../types/game'
import {
  catalogFilterSignature,
  startCatalogPageLoad,
  type PrefetchedPage,
} from './catalogFetch'
import { PAGE_SIZE } from './config'

const SCROLL_SENTINEL_ROOT_MARGIN = '300px'

export function useCatalogPaginationState({
  filters,
  initialGames,
  initialHasMore,
  initialOffset,
  initialTotal,
  pendingApply,
}: {
  filters: GameFilters
  initialGames: CatalogGame[]
  initialHasMore?: boolean
  initialOffset?: number
  initialTotal: number
  pendingApply: number
}) {
  const [fetchKey, setFetchKey] = useState(0)
  const [offset, setOffset] = useState(initialOffset ?? 0)
  const [hasMore, setHasMore] = useState(
    initialHasMore ?? initialGames.length < initialTotal,
  )
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null)
  const loaderRef = useRef<HTMLDivElement>(null)
  // Seeded so SSR-provided games are not immediately refetched on hydration.
  const lastFetchSignatureRef = useRef<string | null>(
    initialGames.length ? `0:${initialOffset ?? 0}` : null,
  )
  const lastFilterResetSignatureRef = useRef(catalogFilterSignature(filters, pendingApply))
  const prefetchRef = useRef<PrefetchedPage | null>(null)
  const retryLoadMore = useCallback(() => {
    prefetchRef.current = null
    setLoadMoreError(null)
    setFetchKey((key) => key + 1)
  }, [])

  return {
    fetchKey,
    hasMore,
    isLoadingMore,
    lastFetchSignatureRef,
    lastFilterResetSignatureRef,
    loadMoreError,
    loaderRef,
    offset,
    prefetchRef,
    retryLoadMore,
    setFetchKey,
    setHasMore,
    setIsLoadingMore,
    setLoadMoreError,
    setOffset,
  }
}

export type CatalogPagination = ReturnType<typeof useCatalogPaginationState>

interface CatalogLoadEffectsProps {
  catalogTotal: number
  enabled: boolean
  filters: GameFilters
  filtersRef: RefObject<GameFilters>
  pagination: CatalogPagination
  pendingApply: number
  restoreInProgressRef: RefObject<boolean>
  setCatalogTotal: Dispatch<SetStateAction<number>>
  setError: Dispatch<SetStateAction<string | null>>
  setGames: Dispatch<SetStateAction<CatalogGame[]>>
  setIsLoading: Dispatch<SetStateAction<boolean>>
}

export function useCatalogLoadEffects({ ...props }: CatalogLoadEffectsProps) {
  useCatalogFilterReset(props)
  useCatalogPageLoad(props)
}

function useCatalogFilterReset({
  enabled,
  filters,
  pagination,
  pendingApply,
  restoreInProgressRef,
}: CatalogLoadEffectsProps) {
  const { lastFilterResetSignatureRef, prefetchRef, setFetchKey, setOffset } = pagination
  const filterResetSignature = catalogFilterSignature(filters, pendingApply)

  useEffect(() => {
    if (!enabled) return
    // Mid-restore this effect still sees pre-restore filters; syncing the
    // signature without resetting keeps the restored page/offset intact.
    if (restoreInProgressRef.current) {
      lastFilterResetSignatureRef.current = filterResetSignature
      return
    }
    if (lastFilterResetSignatureRef.current === filterResetSignature) return
    lastFilterResetSignatureRef.current = filterResetSignature
    prefetchRef.current = null
    setOffset(0)
    setFetchKey((key) => key + 1)
  }, [
    filterResetSignature,
    enabled,
    lastFilterResetSignatureRef,
    prefetchRef,
    restoreInProgressRef,
    setFetchKey,
    setOffset,
  ])
}

function useCatalogPageLoad({
  catalogTotal,
  enabled,
  filtersRef,
  pagination,
  restoreInProgressRef,
  setCatalogTotal,
  setError,
  setGames,
  setIsLoading,
}: CatalogLoadEffectsProps) {
  const {
    fetchKey,
    lastFetchSignatureRef,
    offset,
    prefetchRef,
    setHasMore,
    setIsLoadingMore,
    setLoadMoreError,
  } = pagination

  useEffect(() => {
    if (!enabled) return
    return startCatalogPageLoad({
        catalogTotal,
        fetchKey,
        filtersRef,
        lastFetchSignatureRef,
        offset,
        prefetchRef,
        restoreInProgressRef,
        setCatalogTotal,
        setError,
        setGames,
        setHasMore,
        setIsLoading,
        setIsLoadingMore,
        setLoadMoreError,
      })
  },
    [
      catalogTotal,
      enabled,
      fetchKey,
      filtersRef,
      lastFetchSignatureRef,
      offset,
      prefetchRef,
      restoreInProgressRef,
      setCatalogTotal,
      setError,
      setGames,
      setHasMore,
      setIsLoading,
      setIsLoadingMore,
      setLoadMoreError,
    ],
  )
}

export function useCatalogInfiniteScroll({
  catalogTotal,
  enabled,
  isLoading,
  pagination,
}: {
  catalogTotal: number
  enabled: boolean
  isLoading: boolean
  pagination: CatalogPagination
}) {
  const { hasMore, isLoadingMore, loaderRef, setOffset } = pagination

  useEffect(() => {
    if (!enabled) return
    const element = loaderRef.current
    if (!element) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting || !hasMore || isLoadingMore || isLoading) return
        setOffset((previous) => {
          const lastPageOffset = Math.max(0, catalogTotal - PAGE_SIZE)
          if (catalogTotal > 0 && previous >= lastPageOffset) return previous
          return previous + PAGE_SIZE
        })
      },
      { rootMargin: SCROLL_SENTINEL_ROOT_MARGIN },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [catalogTotal, enabled, hasMore, isLoading, isLoadingMore, loaderRef, setOffset])
}
