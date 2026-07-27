import { Gauge, Rocket } from 'lucide-react'
import { type CSSProperties, useState } from 'react'
import { PlatformGlyph } from '../../components/PlatformIcons'
import { platformBrandColor } from '../../components/platforms'
import type { SystemRequirement } from '../../types/game'
import { parseRequirements } from './sysReqTable'

type Tier = 'minimum' | 'recommended'

function PlatformPicker({
  requirements,
  selected,
  onSelect,
}: {
  requirements: SystemRequirement[]
  selected: string
  onSelect: (platform: string) => void
}) {
  return (
    <div className="dp-sysreq-platforms">
      {requirements.map((requirement) => {
        const isActive = requirement.platform === selected
        const brand = platformBrandColor(requirement.platform)
        return (
          <button
            key={requirement.platform}
            type="button"
            className={isActive ? 'dp-sysreq-platform is-active' : 'dp-sysreq-platform'}
            style={brand ? ({ '--pf-color': brand } as CSSProperties) : undefined}
            onClick={() => onSelect(requirement.platform)}
            aria-pressed={isActive}
          >
            <PlatformGlyph platform={requirement.platform} />
            {requirement.platform}
          </button>
        )
      })}
    </div>
  )
}

function TierTabs({ tier, onSelect }: { tier: Tier; onSelect: (tier: Tier) => void }) {
  return (
    <div className="dp-sysreq-tabs">
      <button
        type="button"
        className={tier === 'minimum' ? 'dp-sysreq-tab is-active' : 'dp-sysreq-tab'}
        onClick={() => onSelect('minimum')}
      >
        <Gauge size={13} aria-hidden="true" />
        Minimum
      </button>
      <button
        type="button"
        className={tier === 'recommended' ? 'dp-sysreq-tab is-active' : 'dp-sysreq-tab'}
        onClick={() => onSelect('recommended')}
      >
        <Rocket size={13} aria-hidden="true" />
        Recommended
      </button>
    </div>
  )
}

export function SysReqPanel({ requirements }: { requirements: SystemRequirement[] }) {
  const [platform, setPlatform] = useState(requirements[0]?.platform ?? '')
  const [preferredTier, setPreferredTier] = useState<Tier>('recommended')

  const active = requirements.find((item) => item.platform === platform) ?? requirements[0]
  if (!active) return null

  const hasRecommended = Boolean(active.recommended)
  const tier: Tier = hasRecommended ? preferredTier : 'minimum'
  const { notes, rows } = parseRequirements(tier === 'minimum' ? active.minimum : active.recommended)

  return (
    <div className="dp-sysreq-panel">
      {requirements.length > 1 ? (
        <PlatformPicker requirements={requirements} selected={active.platform} onSelect={setPlatform} />
      ) : (
        <div className="dp-sysreq-platforms">
          <span className="dp-sysreq-platform is-active is-static">
            <PlatformGlyph platform={active.platform} />
            {active.platform}
          </span>
        </div>
      )}

      {hasRecommended ? <TierTabs tier={tier} onSelect={setPreferredTier} /> : null}

      <dl className="dp-sysreq-table">
        {rows.map((row, index) => (
          <div className="dp-sysreq-row" key={`${active.platform}-${tier}-${index}-${row.label}`}>
            <dt className="dp-sysreq-label">{row.label}</dt>
            <dd className="dp-sysreq-value">{row.value}</dd>
          </div>
        ))}
      </dl>

      {notes.map((note) => (
        <p className="dp-sysreq-note" key={note}>{note}</p>
      ))}
    </div>
  )
}
