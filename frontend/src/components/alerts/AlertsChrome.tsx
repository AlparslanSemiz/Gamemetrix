import { Bell, CheckCheck, RefreshCw } from 'lucide-react'
import type { Dispatch, SetStateAction } from 'react'

import { clampNumber } from './storage'
import {
  DISCOUNT_RANGE,
  SCORE_RANGE,
  UPCOMING_DAYS_RANGE,
  type AlertPreferences,
} from './types'

const TOOLBAR_ICON_SIZE = 16
const EMPTY_ICON_SIZE = 22

export function AlertsToolbar({
  isLoading,
  onMarkAllRead,
  onRefresh,
  unreadCount,
  watchlistCount,
}: {
  isLoading: boolean
  onMarkAllRead: () => void
  onRefresh: () => void
  unreadCount: number
  watchlistCount: number
}) {
  return (
    <div className="alerts-toolbar">
      <div className="alerts-summary">
        <strong>{unreadCount} unread</strong>
        <span>{watchlistCount} wishlist games monitored</span>
      </div>
      <div className="alerts-actions">
        <button type="button" title="Refresh alerts" onClick={onRefresh} disabled={isLoading}>
          <RefreshCw size={TOOLBAR_ICON_SIZE} aria-hidden="true" />
        </button>
        <button
          type="button"
          title="Mark all as read"
          onClick={onMarkAllRead}
          disabled={!unreadCount}
        >
          <CheckCheck size={TOOLBAR_ICON_SIZE} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

export function AlertPreferencesForm({
  preferences,
  setPreferences,
}: {
  preferences: AlertPreferences
  setPreferences: Dispatch<SetStateAction<AlertPreferences>>
}) {
  const updateNumber = (
    field: keyof AlertPreferences,
    value: string,
    range: { min: number; max: number },
  ) =>
    setPreferences((current) => ({
      ...current,
      [field]: clampNumber(value, range.min, range.max, current[field]),
    }))

  return (
    <div className="alerts-preferences">
      <PreferenceField
        label="Deal"
        suffix="%"
        range={DISCOUNT_RANGE}
        value={preferences.minDiscount}
        onChange={(value) => updateNumber('minDiscount', value, DISCOUNT_RANGE)}
      />
      <PreferenceField
        label="Score"
        range={SCORE_RANGE}
        value={preferences.minScore}
        onChange={(value) => updateNumber('minScore', value, SCORE_RANGE)}
      />
      <PreferenceField
        label="Release"
        suffix="days"
        range={UPCOMING_DAYS_RANGE}
        value={preferences.upcomingDays}
        onChange={(value) => updateNumber('upcomingDays', value, UPCOMING_DAYS_RANGE)}
      />
    </div>
  )
}

function PreferenceField({
  label,
  suffix,
  range,
  value,
  onChange,
}: {
  label: string
  suffix?: string
  range: { min: number; max: number }
  value: number
  onChange: (value: string) => void
}) {
  return (
    <label>
      <span>{label}</span>
      <input
        type="number"
        min={range.min}
        max={range.max}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {suffix ? <small>{suffix}</small> : null}
    </label>
  )
}

export function AlertsStatus({
  alertCount,
  error,
  isLoading,
  watchlistCount,
}: {
  alertCount: number
  error: string | null
  isLoading: boolean
  watchlistCount: number
}) {
  const emptyMessage = watchlistCount
    ? 'No wishlist games currently match your alert rules.'
    : 'Add games to your wishlist to start monitoring them.'

  return (
    <>
      {error ? <p className="status status-error">{error}</p> : null}
      {isLoading ? <p className="status">Loading alerts...</p> : null}
      {!isLoading && !alertCount ? (
        <div className="alerts-empty">
          <Bell size={EMPTY_ICON_SIZE} aria-hidden="true" />
          <p>{emptyMessage}</p>
        </div>
      ) : null}
    </>
  )
}
