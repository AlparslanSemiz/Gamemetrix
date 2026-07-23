import { useEffect, type Dispatch, type SetStateAction } from 'react'
import {
  getFacets,
  getGames,
  getIntegrationStatus,
} from '../services/games'
import type { Facets, ProviderStatus } from '../types/game'
import { DEFAULT_FILTERS } from './config'

interface CatalogBootstrapProps {
  setError: Dispatch<SetStateAction<string | null>>
  setFacets: Dispatch<SetStateAction<Facets>>
  setLibraryTotal: Dispatch<SetStateAction<number>>
  setProviderStatuses: Dispatch<SetStateAction<ProviderStatus[]>>
}

export function useCatalogBootstrap({
  setError,
  setFacets,
  setLibraryTotal,
  setProviderStatuses,
}: CatalogBootstrapProps) {
  useEffect(() => {
    let active = true

    void getFacets()
      .then((facets) => {
        if (active) setFacets(facets)
      })
      .catch(() => {
        if (active) setError('Backend facets could not be loaded.')
      })
    void getGames(DEFAULT_FILTERS, 1, 0)
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
  }, [setError, setFacets, setLibraryTotal, setProviderStatuses])
}
