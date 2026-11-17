import { useCallback, useEffect, useState, type Dispatch, type SetStateAction } from 'react'
import {
  getFacets,
  getCatalogGames,
  getIntegrationStatus,
} from '../services/games'
import type { Facets, ProviderStatus } from '../types/game'
import { DEFAULT_FILTERS } from './config'

export const FACETS_ERROR = 'Backend facets could not be loaded.'

interface CatalogBootstrapProps {
  enabled: boolean
  setError: Dispatch<SetStateAction<string | null>>
  setFacets: Dispatch<SetStateAction<Facets>>
  setLibraryTotal: Dispatch<SetStateAction<number>>
  setProviderStatuses: Dispatch<SetStateAction<ProviderStatus[]>>
}

export function useCatalogBootstrap({
  enabled,
  setError,
  setFacets,
  setLibraryTotal,
  setProviderStatuses,
}: CatalogBootstrapProps) {
  const [attempt, setAttempt] = useState(0)
  const retry = useCallback(() => {
    setError((current) => (current === FACETS_ERROR ? null : current))
    setAttempt((count) => count + 1)
  }, [setError])

  useEffect(() => {
    if (!enabled) return
    let active = true

    void getFacets()
      .then((facets) => {
        if (active) setFacets(facets)
      })
      .catch(() => {
        if (active) setError(FACETS_ERROR)
      })
    void getCatalogGames(DEFAULT_FILTERS, 1, 0)
      .then((response) => {
        if (active) setLibraryTotal(response.total)
      })
      .catch(() => undefined)
    void getIntegrationStatus()
      .then((statuses) => {
        if (active) setProviderStatuses(statuses)
      })
      .catch(() => undefined)

    return () => {
      active = false
    }
  }, [attempt, enabled, setError, setFacets, setLibraryTotal, setProviderStatuses])

  return { retry }
}
