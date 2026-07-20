import { useContext } from 'react'
import { AccountContext } from './account'

export function useAccount() {
  const value = useContext(AccountContext)
  if (!value) throw new Error('useAccount must be used within AccountProvider')
  return value
}
