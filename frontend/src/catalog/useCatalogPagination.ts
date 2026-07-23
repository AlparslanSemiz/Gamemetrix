import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from 'react'
import { getGames } from '../services/games'
import type { Game, GameFilters } from '../types/game'
import { PAGE_SIZE } from './config'

const SCROLL_SENTINEL_ROOT_MARGIN = '300px'

interface PrefetchedPage {
  games: Game[]
  offset: number
  total: number
}

export function catalogFilterSignature(
  filters: GameFilters,
  pendingApply: number,
): string {
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
  const [hasMore, setHasMore] = useState(
    !hasUrlFilters && initialGames.length < initialTotal,
  )
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const loaderRef = useRef<HTMLDivElement>(null)
  const lastFetchSignatureRef = useRef<string | null>(
    initialGames.length && !hasUrlFilters ? '0:0' : null,
  )
  const lastFilterResetSignatureRef = useRef(
    catalogFilterSignature(filters, pendingApply),
  )
  const prefetchRef = useRef<PrefetchedPage | null>(null)

  return {
    fetchKey,
    hasMore,
    isLoadingMore,
    lastFetchSignatureRef,
    lastFilterResetSignatureRef,
    loaderRef,
    offset,
    prefetchRef,
    setFetchKey,
    setHasMore,
    setIsLoadingMore,
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

export function useCatalogLoadEffects({
  ...props
}: CatalogLoadEffectsProps) {
  useCatalogFilterReset(props)
  useCatalogPageLoad(props)
}

function useCatalogFilterReset({
  filters,
  pagination,
  pendingApply,
  restoreInProgressRef,
}: CatalogLoadEffectsProps) {
  const {
    lastFilterResetSignatureRef,
    prefetchRef,
    setFetchKey,
    setOffset,
  } = pagination
  const filterResetSignature = catalogFilterSignature(filters, pendingApply)

  useEffect(() => {
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
  } = pagination

  useEffect(() => startCatalogPageLoad({
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
  }), [
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
  ])
}

interface StartCatalogPageLoadProps {
  catalogTotal: number
  fetchKey: number
  filtersRef: RefObject<GameFilters>
  lastFetchSignatureRef: RefObject<string | null>
  offset: number
  prefetchRef: RefObject<PrefetchedPage | null>
  restoreInProgressRef: RefObject<boolean>
  setCatalogTotal: Dispatch<SetStateAction<number>>
  setError: Dispatch<SetStateAction<string | null>>
  setGames: Dispatch<SetStateAction<Game[]>>
  setHasMore: Dispatch<SetStateAction<boolean>>
  setIsLoading: Dispatch<SetStateAction<boolean>>
  setIsLoadingMore: Dispatch<SetStateAction<boolean>>
}

function startCatalogPageLoad(props: StartCatalogPageLoadProps) {
  if (props.restoreInProgressRef.current) {
    props.lastFetchSignatureRef.current = `${props.fetchKey}:${props.offset}`
    return
  }
  if (
    props.offset > 0
    && props.catalogTotal > 0
    && props.offset >= props.catalogTotal
  ) {
    props.setHasMore(false)
    props.setIsLoadingMore(false)
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
  props.setError(null)

  const applyPage = (pageGames: Game[], total: number) => {
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
      total,
    })
  }
  const handleError = () => {
    settled = true
    if (!active) return
    if (isFirstPage) {
      props.setGames([])
      props.setIsLoading(false)
    } else {
      props.setIsLoadingMore(false)
    }
    props.setError('GameMetrix API is not reachable yet.')
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
  onSuccess: (games: Game[], total: number) => void,
  onError: () => void,
) {
  const cached = prefetchRef.current
  if (!isFirstPage && cached?.offset === offset) {
    prefetchRef.current = null
    onSuccess(cached.games, cached.total)
    return
  }
  try {
    const response = await getGames(filters, PAGE_SIZE, offset)
    onSuccess(response.games, response.total)
  } catch {
    onError()
  }
}

interface ApplyLoadedPageProps {
  activeFilters: GameFilters
  isActive: () => boolean
  isFirstPage: boolean
  offset: number
  pageGames: Game[]
  prefetchRef: RefObject<PrefetchedPage | null>
  setCatalogTotal: Dispatch<SetStateAction<number>>
  setGames: Dispatch<SetStateAction<Game[]>>
  setHasMore: Dispatch<SetStateAction<boolean>>
  setIsLoading: Dispatch<SetStateAction<boolean>>
  setIsLoadingMore: Dispatch<SetStateAction<boolean>>
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
  total,
}: ApplyLoadedPageProps) {
  if (!isActive()) return
  setGames((current) => (
    isFirstPage ? pageGames : [...current, ...pageGames]
  ))
  setCatalogTotal(total)
  const loadedCount = offset + pageGames.length
  setHasMore(pageGames.length > 0 && loadedCount < total)
  if (isFirstPage) setIsLoading(false)
  else setIsLoadingMore(false)
  if (pageGames.length > 0) {
    prefetchNextPage(
      activeFilters,
      loadedCount,
      total,
      isActive,
      prefetchRef,
    )
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
  void getGames(filters, PAGE_SIZE, offset)
    .then((response) => {
      if (isActive()) {
        prefetchRef.current = {
          offset,
          games: response.games,
          total: response.total,
        }
      }
    })
    .catch(() => undefined)
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
  const {
    hasMore,
    isLoadingMore,
    loaderRef,
    setOffset,
  } = pagination

  useEffect(() => {
    const element = loaderRef.current
    if (!element) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries[0]?.isIntersecting || !hasMore || isLoadingMore || isLoading) {
          return
        }
        setOffset((previous) => {
          if (
            catalogTotal > 0
            && previous >= Math.max(0, catalogTotal - PAGE_SIZE)
          ) {
            return previous
          }
          return previous + PAGE_SIZE
        })
      },
      { rootMargin: SCROLL_SENTINEL_ROOT_MARGIN },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [
    catalogTotal,
    hasMore,
    isLoading,
    isLoadingMore,
    loaderRef,
    setOffset,
  ])
}
