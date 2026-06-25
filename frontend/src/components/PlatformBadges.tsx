import { Gamepad2, Monitor, Smartphone } from 'lucide-react'

interface PlatformBadgesProps {
  platforms: string[]
}

function platformKind(platform: string) {
  const value = platform.toLowerCase()
  if (value.includes('windows') || value === 'pc' || value.includes('steam')) {
    return { label: 'PC', className: 'platform-steam' }
  }
  if (value.includes('mac')) {
    return { label: 'MAC', className: 'platform-mac' }
  }
  if (value.includes('linux')) {
    return { label: 'LIN', className: 'platform-linux' }
  }
  if (value.includes('playstation') || value.includes('ps4') || value.includes('ps5')) {
    const label = value.includes('5') || value.includes('ps5') ? 'PS5' : value.includes('4') || value.includes('ps4') ? 'PS4' : 'PS'
    return { label, className: 'platform-playstation' }
  }
  if (value.includes('xbox')) {
    return { label: 'XB', className: 'platform-xbox' }
  }
  if (value.includes('nintendo') || value.includes('switch')) {
    return { label: 'NS', className: 'platform-nintendo' }
  }
  if (value.includes('ios') || value.includes('android')) {
    return { label: 'MOB', className: 'platform-mobile' }
  }
  return { label: 'GM', className: 'platform-generic' }
}

export function PlatformBadges({ platforms }: PlatformBadgesProps) {
  // Deduplicate by className so "Windows", "PC", "Steam" don't all show as PC
  const seen = new Set<string>()
  const badges = platforms
    .map((p) => ({ platform: p, kind: platformKind(p) }))
    .filter(({ kind }) => {
      if (seen.has(kind.className)) return false
      seen.add(kind.className)
      return true
    })
    .slice(0, 5)

  return (
    <div className="platform-badges" aria-label="Platforms">
      {badges.map(({ platform, kind }) => {
        const Icon =
          kind.className === 'platform-mobile'
            ? Smartphone
            : ['platform-steam', 'platform-mac', 'platform-linux'].includes(kind.className)
              ? Monitor
              : Gamepad2

        return (
          <span className={`platform-badge ${kind.className}`} key={kind.className} title={platform}>
            <Icon size={12} aria-hidden="true" />
            {kind.label}
          </span>
        )
      })}
    </div>
  )
}
