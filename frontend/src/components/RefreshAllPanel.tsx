import { useEffect, useState } from 'react'
import { getRateLimits, refreshAllScores } from '../services/games'

export function RefreshAllPanel() {
  const [status, setStatus] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [rateLimits, setRateLimits] = useState<Record<string, { remaining: number; limit: number }> | null>(null)

  useEffect(() => {
    void getRateLimits().then(setRateLimits).catch(() => {})
  }, [])

  const trigger = async (force: boolean) => {
    setBusy(true)
    setStatus(null)
    try {
      const { message } = await refreshAllScores(force, 3)
      setStatus(message)
      void getRateLimits().then(setRateLimits).catch(() => {})
    } catch {
      setStatus('Failed to start refresh.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="score-weight-panel">
      <p>Scores are fetched automatically every 6 hours. Use the buttons below for manual control.</p>
      <div className="refresh-actions">
        <button type="button" className="apply-button" disabled={busy} onClick={() => trigger(false)}>
          {busy ? 'Starting…' : '⚡ Refresh stale games'}
        </button>
        <button type="button" className="apply-button refresh-danger" disabled={busy} onClick={() => trigger(true)}>
          {busy ? 'Starting…' : '🔄 Force refresh ALL'}
        </button>
      </div>
      {status && <p className="refresh-status">{status}</p>}
      {rateLimits && (
        <div className="rate-limit-block">
          <p className="rate-limit-caption">Today's API budget (resets at midnight):</p>
          <div className="rate-limit-grid">
            {Object.entries(rateLimits).map(([source, { remaining, limit }]) => {
              const pct = limit > 0 ? (remaining / limit) * 100 : 0
              const color = remaining === 0 ? '#dc2626' : pct < 20 ? '#f59e0b' : '#22c55e'
              return (
                <div key={source} className="rate-limit-row">
                  <span>{source}</span>
                  <div className="rate-limit-track">
                    <div className="rate-limit-fill" style={{ width: `${pct}%`, background: color }} />
                  </div>
                  <span className="rate-limit-value" style={{ color }}>{remaining}/{limit}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
