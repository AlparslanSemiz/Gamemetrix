import { useState } from 'react'
import type { SystemRequirement } from '../../types/game'

function formatReqs(raw: string): string {
  return raw
    .replace(/Minimum:\r?\n?/i, '')
    .replace(/Recommended:\r?\n?/i, '')
    .trim()
}

export function SysReqBlock({ req }: { req: SystemRequirement }) {
  const [tab, setTab] = useState<'minimum' | 'recommended'>(
    req.recommended ? 'recommended' : 'minimum',
  )
  const hasRecommended = Boolean(req.recommended)

  return (
    <div className="dp-sysreq-block">
      <h4 className="dp-sysreq-platform">{req.platform}</h4>
      {hasRecommended && (
        <div className="dp-sysreq-tabs">
          <button
            type="button"
            className={tab === 'minimum' ? 'dp-sysreq-tab is-active' : 'dp-sysreq-tab'}
            onClick={() => setTab('minimum')}
          >
            Minimum
          </button>
          <button
            type="button"
            className={tab === 'recommended' ? 'dp-sysreq-tab is-active' : 'dp-sysreq-tab'}
            onClick={() => setTab('recommended')}
          >
            Recommended
          </button>
        </div>
      )}
      <pre className="dp-sysreq-text">
        {tab === 'minimum' ? formatReqs(req.minimum) : formatReqs(req.recommended)}
      </pre>
    </div>
  )
}
