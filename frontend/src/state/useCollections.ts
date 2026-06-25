import { useContext } from 'react'
import { CollectionsContext } from './collections'

export function useCollections() {
  const value = useContext(CollectionsContext)
  if (!value) {
    throw new Error('useCollections must be used inside CollectionsProvider')
  }

  return value
}
