import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from 'react'

import type { Game, GameFilters } from '../types/game'
import {
  catalogFilterSignature,
  startCatalogPageLoad,
  type PrefetchedPage,
} from './catalogFetch'
import { PAGE_SIZE } from './config'

const SCROLL_SENTINEL_ROOT_MARGIN = '300px'

export function useCatalogPaginationState({
  filters,
  hasUrlFilters,
  initialGames,
  initialTotal,
  pendingApply,
}: {
  filters: GameFilters
  hasUrlFilters: boolean
  initialGames: Game[]
  initialTotal: number
  pendingApply: number
}) {
  const [fetchKey, setFetchKey] = useState(0)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(!hasUrlFilters && initialGames.length < initialTotal)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null)
  const loaderRef = useRef<HTMLDivElement>(null)
  // Seeded so SSR-provided games are not immediately refetched on hydration.
  const lastFetchSignatureRef = useRef<string | null>(
    initialGames.length && !hasUrlFilters ? '0:0' : null,
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
  filters: GameFilters
  filtersRef: RefObject<GameFilters>
  pagination: CatalogPagination
  pendingApply: number
  restoreInProgressRef: RefObject<boolean>
  setCatalogTotal: Dispatch<SetStateAction<number>>
  setError: Dispatch<SetStateAction<string | null>>
  setGames: Dispatch<SetStateAction<Game[]>>
  setIsLoading: Dispatch<SetStateAction<boolean>>
}

export function useCatalogLoadEffects({ ...props }: CatalogLoadEffectsProps) {
  useCatalogFilterReset(props)
  useCatalogPageLoad(props)
}

function useCatalogFilterReset({
  filters,
  pagination,
  pendingApply,
  restoreInProgressRef,
}: CatalogLoadEffectsProps) {
  const { lastFilterResetSignatureRef, prefetchRef, setFetchKey, setOffset } = pagination
  const filterResetSignature = catalogFilterSignature(filters, pendingApply)

  useEffect(() => {
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
    lastFilterResetSignatureRef,
    prefetchRef,
    restoreInProgressRef,
    setFetchKey,
    setOffset,
  ])
}

function useCatalogPageLoad({
  catalogTotal,
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

  useEffect(
    () =>
      startCatalogPageLoad({
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
      }),
    [
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
    ],
  )
}

export function useCatalogInfiniteScroll({
  catalogTotal,
  isLoading,
  pagination,
}: {
  catalogTotal: number
  isLoading: boolean
  pagination: CatalogPagination
}) {
  const { hasMore, isLoadingMore, loaderRef, setOffset } = pagination

  useEffect(() => {
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
  }, [catalogTotal, hasMore, isLoading, isLoadingMore, loaderRef, setOffset])
}
