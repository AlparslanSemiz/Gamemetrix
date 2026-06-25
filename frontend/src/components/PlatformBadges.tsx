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
  if (value.includes('playstation')) {
    return { label: 'PS', className: 'platform-playstation' }
  }
  if (value.includes('xbox')) {
    return { label: 'XB', className: 'platform-xbox' }
  }
  if (value.includes('nintendo') || value.includes('switch')) {
    return { label: 'NS', className: 'platform-nintendo' }
  }
  if (value.includes('ios') || value.includes('android')) {
    return { label: 'MO', className: 'platform-mobile' }
  }

  return { label: 'GM', className: 'platform-generic' }
}

export function PlatformBadges({ platforms }: PlatformBadgesProps) {
  return (
    <div className="platform-badges" aria-label="Platforms">
      {platforms.slice(0, 5).map((platform) => {
        const kind = platformKind(platform)
        const Icon = kind.className === 'platform-mobile'
          ? Smartphone
          : ['platform-steam', 'platform-mac', 'platform-linux'].includes(kind.className)
            ? Monitor
            : Gamepad2

        return (
          <span className={`platform-badge ${kind.className}`} key={platform} title={platform}>
            <Icon size={13} aria-hidden="true" />
            {kind.label}
          </span>
        )
      })}
    </div>
  )
}
