import { Gamepad2, Monitor, Smartphone } from 'lucide-react'

interface PlatformBadgesProps {
  platforms: string[]
  slug: string
  title: string
}

const steamAppIds: Record<string, number> = {
  'baldurs-gate-3': 1086940,
  'elden-ring': 1245620,
  hades: 1145360,
  'disco-elysium-the-final-cut': 632470,
  'hi-fi-rush': 1817230,
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

function platformHref(className: string, slug: string, title: string): string | undefined {
  if (className === 'platform-steam') {
    const steamAppId = steamAppIds[slug]
    if (steamAppId) return `https://store.steampowered.com/app/${steamAppId}`
    return `https://store.steampowered.com/search/?term=${encodeURIComponent(title)}`
  }

  if (className === 'platform-playstation') {
    return `https://store.playstation.com/search/${encodeURIComponent(title)}`
  }

  if (className === 'platform-xbox') {
    return `https://www.xbox.com/search?q=${encodeURIComponent(title)}`
  }

  if (className === 'platform-nintendo') {
    return `https://www.nintendo.com/search/#q=${encodeURIComponent(title)}&p=1&cat=gme`
  }

  return undefined
}

export function PlatformBadges({ platforms, slug, title }: PlatformBadgesProps) {
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

        const href = platformHref(kind.className, slug, title)
        const className = `platform-badge ${kind.className}`
        const content = (
          <>
            <Icon size={12} aria-hidden="true" />
            {kind.label}
          </>
        )

        return href ? (
          <a
            className={className}
            href={href}
            key={kind.className}
            target="_blank"
            rel="noreferrer"
            title={`${platform} store`}
          >
            {content}
          </a>
        ) : (
          <span className={className} key={kind.className} title={platform}>
            {content}
          </span>
        )
      })}
    </div>
  )
}
