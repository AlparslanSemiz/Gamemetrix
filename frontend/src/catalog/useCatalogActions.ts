import { useCallback, type Dispatch, type RefObject, type SetStateAction } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { ClearableFilterKey } from '../components/ActiveFilterChips'
import type { GameFilters } from '../types/game'
import {
  CURRENT_YEAR,
  DEFAULT_FILTERS,
  type ActivePage,
  type CuratedPreset,
  type MainPage,
  type UtilityPage,
} from './config'

interface CatalogActionsProps {
  accountIsActive: boolean
  scrollToTop: () => void
  setActivePage: Dispatch<SetStateAction<ActivePage>>
  setActivePreset: Dispatch<SetStateAction<string | null>>
  setFilters: Dispatch<SetStateAction<GameFilters>>
  setMobileMoreOpen: Dispatch<SetStateAction<boolean>>
  setPendingApply: Dispatch<SetStateAction<number>>
  snapshotAnchorRef: RefObject<{
    slug: string
    viewportTop: number
  } | null>
}

function presetFilters(preset: CuratedPreset): GameFilters {
  if (preset.id === 'best-of-year') {
    return {
      ...DEFAULT_FILTERS,
      yearMin: CURRENT_YEAR,
      yearMax: CURRENT_YEAR,
      sort: 'rank_score',
      direction: 'desc',
    }
  }
  return { ...DEFAULT_FILTERS, ...preset.filters }
}

export function useCatalogActions({
  accountIsActive,
  scrollToTop,
  setActivePage,
  setActivePreset,
  setFilters,
  setMobileMoreOpen,
  setPendingApply,
  snapshotAnchorRef,
}: CatalogActionsProps) {
  const location = useLocation()
  const navigate = useNavigate()

  const goHome = useCallback(() => {
    if (location.pathname !== '/' || location.search) navigate('/')
    snapshotAnchorRef.current = null
    scrollToTop()
    setActivePage('catalog')
    setFilters(DEFAULT_FILTERS)
    setActivePreset(null)
    setPendingApply((count) => count + 1)
  }, [
    location.pathname,
    location.search,
    navigate,
    scrollToTop,
    setActivePage,
    setActivePreset,
    setFilters,
    setPendingApply,
    snapshotAnchorRef,
  ])

  const openPreset = useCallback((preset: CuratedPreset) => {
    if (preset.id === 'best-deals') return navigate('/deals')
    if (preset.id === 'free-games') return navigate('/best/free-pc-games')
    setActivePage('catalog')
    setActivePreset(preset.id)
    setFilters(presetFilters(preset))
    setPendingApply((count) => count + 1)
  }, [navigate, setActivePage, setActivePreset, setFilters, setPendingApply])

  const openMainPage = useCallback((id: MainPage) => {
    setActivePage(id)
    setActivePreset(null)
    const target = id === 'catalog' ? '/' : `/?view=${encodeURIComponent(id)}`
    if (`${location.pathname}${location.search}` !== target) navigate(target)
  }, [
    location.pathname,
    location.search,
    navigate,
    setActivePage,
    setActivePreset,
  ])

  const openUtilityPage = useCallback((id: UtilityPage) => {
    setMobileMoreOpen(false)
    if (location.pathname !== `/${id}`) navigate(`/${id}`)
  }, [location.pathname, navigate, setMobileMoreOpen])

  const clearFilter = useCallback((key: ClearableFilterKey) => {
    setFilters((current) => ({ ...current, [key]: '' }))
  }, [setFilters])

  const clearDealMode = useCallback(() => {
    setFilters((current) => ({ ...current, dealMode: 'all' }))
    setActivePreset(null)
  }, [setActivePreset, setFilters])

  const openAccount = useCallback(
    () => navigate(accountIsActive ? '/account' : '/login'),
    [accountIsActive, navigate],
  )

  return {
    clearDealMode,
    clearFilter,
    goHome,
    openAccount,
    openMainPage,
    openPreset,
    openUtilityPage,
  }
}

export function useCatalogFilterActions(
  setActivePage: Dispatch<SetStateAction<ActivePage>>,
  setFilters: Dispatch<SetStateAction<GameFilters>>,
) {
  const filterBy = useCallback((
    field: 'developer' | 'genre' | 'publisher',
    value: string,
  ) => {
    setActivePage('catalog')
    setFilters((current) => ({
      ...current,
      [field]: value,
      ...(field === 'developer' ? { publisher: '' } : {}),
      ...(field === 'publisher' ? { developer: '' } : {}),
    }))
  }, [setActivePage, setFilters])

  return {
    filterDeveloper: useCallback(
      (developer: string) => filterBy('developer', developer),
      [filterBy],
    ),
    filterGenre: useCallback(
      (genre: string) => filterBy('genre', genre),
      [filterBy],
    ),
    filterPublisher: useCallback(
      (publisher: string) => filterBy('publisher', publisher),
      [filterBy],
    ),
  }
}
