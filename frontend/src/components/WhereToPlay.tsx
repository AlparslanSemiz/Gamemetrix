import { ExternalLink } from 'lucide-react'

interface WhereToPlayProps {
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

const subscriptionAvailability: Record<string, string[]> = {
  'hi-fi-rush': ['Game Pass'],
  hades: ['PS Plus'],
}

export function WhereToPlay({ platforms, slug, title }: WhereToPlayProps) {
  const stores: Array<{ label: string; href?: string }> = []
  const steamAppId = steamAppIds[slug]

  if (steamAppId) {
    stores.push({
      label: 'Steam',
      href: `https://store.steampowered.com/app/${steamAppId}`,
    })
  }

  if (platforms.some((platform) => platform.toLowerCase().includes('playstation'))) {
    stores.push({
      label: 'PlayStation',
      href: `https://store.playstation.com/search/${encodeURIComponent(title)}`,
    })
  }

  if (platforms.some((platform) => platform.toLowerCase().includes('xbox'))) {
    stores.push({
      label: 'Xbox',
      href: `https://www.xbox.com/search?q=${encodeURIComponent(title)}`,
    })
  }

  for (const label of subscriptionAvailability[slug] ?? []) {
    stores.unshift({ label })
  }

  return (
    <div className="where-to-play" aria-label="Where to play">
      {stores.slice(0, 4).map((store) =>
        store.href ? (
          <a href={store.href} key={store.label} target="_blank" rel="noreferrer">
            {store.label}
            <ExternalLink size={11} aria-hidden="true" />
          </a>
        ) : (
          <span key={store.label}>{store.label}</span>
        ),
      )}
    </div>
  )
}
