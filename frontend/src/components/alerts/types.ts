import type { Game } from '../../types/game'

export const READ_KEY = 'gamemetrix.alerts.read.v1'
export const DISMISSED_KEY = 'gamemetrix.alerts.dismissed.v1'
export const PREFERENCES_KEY = 'gamemetrix.alerts.preferences.v1'

export const DISCOUNT_RANGE = { min: 1, max: 90 } as const
export const SCORE_RANGE = { min: 1, max: 100 } as const
export const UPCOMING_DAYS_RANGE = { min: 1, max: 365 } as const

export interface AlertPreferences {
  minDiscount: number
  minScore: number
  upcomingDays: number
}

export type AlertKind = 'free' | 'deal' | 'release' | 'score'

export interface GameAlert {
  id: string
  kind: AlertKind
  title: string
  detail: string
  game: Game
}

export const DEFAULT_PREFERENCES: AlertPreferences = {
  minDiscount: 20,
  minScore: 80,
  upcomingDays: 45,
}
