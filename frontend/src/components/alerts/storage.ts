import {
  DEFAULT_PREFERENCES,
  DISCOUNT_RANGE,
  PREFERENCES_KEY,
  SCORE_RANGE,
  UPCOMING_DAYS_RANGE,
  type AlertPreferences,
} from './types'

export function clampNumber(value: string, min: number, max: number, fallback: number): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.min(max, Math.max(min, parsed)) : fallback
}

function clampSetting(
  value: unknown,
  range: { min: number; max: number },
  fallback: number,
): number {
  return Math.min(range.max, Math.max(range.min, Number(value) || fallback))
}

export function loadStringSet(key: string): Set<string> {
  if (typeof window === 'undefined') return new Set()
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? '[]')
    if (!Array.isArray(value)) return new Set()
    return new Set(value.filter((item): item is string => typeof item === 'string'))
  } catch {
    return new Set()
  }
}

export function loadPreferences(): AlertPreferences {
  if (typeof window === 'undefined') return DEFAULT_PREFERENCES
  try {
    const value = JSON.parse(
      localStorage.getItem(PREFERENCES_KEY) ?? '{}',
    ) as Partial<AlertPreferences>
    return {
      minDiscount: clampSetting(value.minDiscount, DISCOUNT_RANGE, DEFAULT_PREFERENCES.minDiscount),
      minScore: clampSetting(value.minScore, SCORE_RANGE, DEFAULT_PREFERENCES.minScore),
      upcomingDays: clampSetting(
        value.upcomingDays,
        UPCOMING_DAYS_RANGE,
        DEFAULT_PREFERENCES.upcomingDays,
      ),
    }
  } catch {
    return DEFAULT_PREFERENCES
  }
}

export function persistSet(key: string, values: Set<string>): void {
  localStorage.setItem(key, JSON.stringify(Array.from(values)))
}
