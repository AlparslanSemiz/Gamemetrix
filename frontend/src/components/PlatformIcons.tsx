import type React from 'react'

// ─── Platform icon SVGs ───────────────────────────────────────────────────────
// All icons: 16×16 viewBox, fill="currentColor" for CSS color control

const PcIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M0 0h7v7H0zM9 0h7v7H9zM0 9h7v7H0zM9 9h7v7H9z" />
  </svg>
)

const SteamIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 2a5 5 0 110 10A5 5 0 018 3zm0 1.5a3.5 3.5 0 100 7 3.5 3.5 0 000-7zm0 1.5a2 2 0 110 4 2 2 0 010-4z" />
  </svg>
)

const PsIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {/* PlayStation "PS" mark: P column + S tail */}
    <path d="M4 3v10l2 .6V9.2h1.8c1.3 0 2.2-.9 2.2-2.1V5.1C10 3.9 9.1 3 7.8 3H4zm2 1.6h1.8c.4 0 .7.3.7.7v1.9c0 .4-.3.7-.7.7H6V4.6z" />
    <path d="M11 13L9 9.7h1.7L12.7 13H11z" />
  </svg>
)

const XboxIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm2.8 9.9L8 8.1l-2.8 2.8-1.1-1.1L6.9 7 4.1 4.2l1.1-1.1L8 5.9l2.8-2.8 1.1 1.1L9.1 7l2.8 2.8-1.1 1.1z" />
  </svg>
)

const SwitchIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    <path d="M4.5 1C2.57 1 1 2.57 1 4.5v7C1 13.43 2.57 15 4.5 15H7V1H4.5zM3 5.5a1 1 0 112 0 1 1 0 01-2 0zM9 1v14h2.5C13.43 15 15 13.43 15 11.5v-7C15 2.57 13.43 1 11.5 1H9zm2.5 7a1 1 0 110-2 1 1 0 010 2z" />
  </svg>
)

const AppleIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {/* Apple logo: round body with bite + leaf stem */}
    <path d="M10.5 5.7C9.9 5 9.1 4.6 8.3 4.6c-.7 0-1.2.3-1.7.5-.4.2-.7.3-1 .3-.3 0-.6-.1-1-.3C4.1 4.9 3.5 4.6 2.8 4.7 1.7 4.9 1 5.9 1 7.3c0 2.6 2.1 6 3.5 6 .5 0 1-.3 1.5-.5.4-.2.8-.3 1-.3.2 0 .6.1 1 .3.5.2 1 .5 1.5.5 1.5 0 3-3.1 3.5-5.5-.7-.4-1.2-1.2-1.5-2.1zM9 1.5c-.3.4-.8 1-1.5 1.3.7.3 1.5-.2 1.8-.7.2-.3.4-.7.4-1.1C9.4.9 9.2 1.2 9 1.5z" />
  </svg>
)

const LinuxIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {/* Tux: round head with ears, eyes, beak, body */}
    <path d="M8 1C6.3 1 5 2.5 5 4c0 1 .4 2 1 2.7-1.3.5-3 1.6-3 3.8 0 1.8 1.2 2.5 2 2.5.5 0 1-.2 1.5-.5 1 .5 1.7.7 2.5.7s1.5-.2 2.5-.7c.5.3 1 .5 1.5.5.8 0 2-.7 2-2.5 0-2.2-1.7-3.3-3-3.8.6-.7 1-1.7 1-2.7C13 2.5 11.7 1 10 1c-.7 0-1.3.3-1.7.7L8 1.5l-.3.2C7.3 1.3 6.7 1 8 1zM7 3.5a1 1 0 112 0 1 1 0 01-2 0zm-1 7a.75.75 0 110-1.5.75.75 0 010 1.5zm4 0a.75.75 0 110-1.5.75.75 0 010 1.5z" />
  </svg>
)

const AndroidIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {/* Android robot head */}
    <path d="M5.18 3.7L3.9 1.5l.87-.5 1.28 2.2C6.6 3.1 7.3 3 8 3s1.4.1 1.95.2L11.23 1l.87.5L10.82 3.7A5 5 0 0113 8H3a5 5 0 012.18-4.3zM5.5 6a.75.75 0 100 1.5A.75.75 0 005.5 6zm5 0a.75.75 0 100 1.5.75.75 0 000-1.5zM3 9h10v2.5c0 .83-.67 1.5-1.5 1.5H11v2h-1.5v-2h-3v2H5v-2H4.5C3.67 13 3 12.33 3 11.5V9z" />
  </svg>
)

const GogIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {/* GOG.com: G in a circle */}
    <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm.5 4.5H11v5H9.5V9H7.5v-1.5h2V7H7a2 2 0 00-2 2 2 2 0 002 2h1V9.5H6.5A.5.5 0 016 9a.5.5 0 01.5-.5H8V10h.5v.5H7a3.5 3.5 0 110-7h1.5v2z" />
  </svg>
)

const EpicIcon = () => (
  <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {/* Epic Games: shield with horizontal stripes */}
    <path d="M8 1L2 4v5c0 3 3 5.5 6 7 3-1.5 6-4 6-7V4L8 1zm-2 3h4v1.5H6V4zm0 2.5h4V8H6V6.5zm0 2.5h4v1.5H6V9z" />
  </svg>
)

// ─── Platform normalization map ───────────────────────────────────────────────

const NORMALIZE: Record<string, string> = {
  pc: 'pc', windows: 'pc', 'microsoft windows': 'pc', 'pc windows': 'pc',
  steam: 'steam',
  macos: 'macos', 'mac os': 'macos', mac: 'macos', 'apple mac': 'macos', 'os x': 'macos',
  linux: 'linux',
  playstation: 'ps', 'playstation 3': 'ps3', ps3: 'ps3',
  'playstation 4': 'ps4', ps4: 'ps4',
  'playstation 5': 'ps5', ps5: 'ps5',
  xbox: 'xbox',
  'xbox 360': 'xbox360',
  'xbox one': 'xboxone',
  'xbox series x': 'xboxseries', 'xbox series x/s': 'xboxseries',
  'xbox series': 'xboxseries', 'xbox series s': 'xboxseries',
  'nintendo switch': 'switch', switch: 'switch',
  ios: 'ios', iphone: 'ios', ipad: 'ios',
  android: 'android',
  gog: 'gog', 'gog.com': 'gog',
  'epic games store': 'epic', 'epic games': 'epic', epic: 'epic',
  'nintendo wii': 'wii', wii: 'wii',
  'nintendo wii u': 'wiiu', 'wii u': 'wiiu',
  'nintendo 3ds': '3ds', '3ds': '3ds',
  'nintendo ds': 'ds',
  'playstation vita': 'vita', vita: 'vita',
  'playstation portable': 'psp', psp: 'psp',
}

interface PlatformDef {
  name: string
  short: string
  color: string
  group: string
  priority: number
  Icon: () => JSX.Element
}

// Each entry: canonical key → display info
const PLATFORM_DEFS: Record<string, PlatformDef> = {
  pc:         { name: 'PC',               short: 'PC',   color: '#00A4EF', group: 'pc',    priority: 2, Icon: PcIcon },
  steam:      { name: 'Steam',            short: 'Steam',color: '#1B75BB', group: 'pc',    priority: 1, Icon: SteamIcon },
  macos:      { name: 'macOS',            short: 'Mac',  color: '#A2AAAD', group: 'macos', priority: 1, Icon: AppleIcon },
  linux:      { name: 'Linux',            short: 'Linux',color: '#FCC624', group: 'linux', priority: 1, Icon: LinuxIcon },
  ps3:        { name: 'PlayStation 3',    short: 'PS3',  color: '#0070CC', group: 'ps',    priority: 3, Icon: PsIcon },
  ps4:        { name: 'PlayStation 4',    short: 'PS4',  color: '#0070CC', group: 'ps',    priority: 2, Icon: PsIcon },
  ps5:        { name: 'PlayStation 5',    short: 'PS5',  color: '#0070CC', group: 'ps',    priority: 1, Icon: PsIcon },
  ps:         { name: 'PlayStation',      short: 'PS',   color: '#0070CC', group: 'ps',    priority: 4, Icon: PsIcon },
  xbox:       { name: 'Xbox',             short: 'XB',   color: '#107C10', group: 'xbox',  priority: 4, Icon: XboxIcon },
  xbox360:    { name: 'Xbox 360',         short: 'X360', color: '#107C10', group: 'xbox',  priority: 3, Icon: XboxIcon },
  xboxone:    { name: 'Xbox One',         short: 'XB1',  color: '#107C10', group: 'xbox',  priority: 2, Icon: XboxIcon },
  xboxseries: { name: 'Xbox Series X/S',  short: 'XBS',  color: '#107C10', group: 'xbox',  priority: 1, Icon: XboxIcon },
  switch:     { name: 'Nintendo Switch',  short: 'NSW',  color: '#E60012', group: 'switch',priority: 1, Icon: SwitchIcon },
  ios:        { name: 'iOS',              short: 'iOS',  color: '#A2AAAD', group: 'ios',   priority: 1, Icon: AppleIcon },
  android:    { name: 'Android',          short: 'And',  color: '#3DDC84', group: 'android',priority:1, Icon: AndroidIcon },
  gog:        { name: 'GOG',              short: 'GOG',  color: '#86328A', group: 'gog',   priority: 1, Icon: GogIcon },
  epic:       { name: 'Epic Games Store', short: 'Epic', color: '#D3D3D3', group: 'epic',  priority: 1, Icon: EpicIcon },
  wii:        { name: 'Wii',              short: 'Wii',  color: '#E60012', group: 'wii',   priority: 1, Icon: SwitchIcon },
  wiiu:       { name: 'Wii U',            short: 'WiiU', color: '#E60012', group: 'wiiu',  priority: 1, Icon: SwitchIcon },
}

// ─── Normalization helpers ────────────────────────────────────────────────────

function normalizePlatform(raw: string): string {
  return NORMALIZE[raw.toLowerCase().trim()] ?? 'other'
}

/** Deduplicate platforms: keep only the highest-priority entry per group */
function deduplicatePlatforms(platforms: string[]): PlatformDef[] {
  const bestPerGroup = new Map<string, PlatformDef & { key: string }>()

  for (const raw of platforms) {
    const key = normalizePlatform(raw)
    const def = PLATFORM_DEFS[key]
    if (!def) continue

    const existing = bestPerGroup.get(def.group)
    if (!existing || def.priority < existing.priority) {
      bestPerGroup.set(def.group, { ...def, key })
    }
  }

  return Array.from(bestPerGroup.values()).sort((a, b) => {
    const ORDER = ['pc', 'steam', 'ps', 'xbox', 'switch', 'macos', 'linux', 'ios', 'android', 'gog', 'epic']
    return (ORDER.indexOf(a.group) ?? 99) - (ORDER.indexOf(b.group) ?? 99)
  })
}

// ─── PlatformIcons component ──────────────────────────────────────────────────

interface PlatformIconsProps {
  platforms: string[]
  mode?: 'compact' | 'list' | 'detail'
  maxVisible?: number
}

export function PlatformIcons({ platforms, mode = 'list', maxVisible }: PlatformIconsProps) {
  const defaultMax = mode === 'compact' ? 4 : mode === 'list' ? 5 : 99
  const limit = maxVisible ?? defaultMax

  const defs = deduplicatePlatforms(platforms)
  const visible = defs.slice(0, limit)
  const overflow = defs.length - visible.length

  if (visible.length === 0) return null

  return (
    <div
      className={`platform-icons platform-icons-${mode}`}
      aria-label="Platforms"
    >
      {visible.map((def) => {
        const label = mode === 'detail' ? def.name : mode === 'list' ? def.short : undefined
        return (
          <span
            key={def.group}
            className="pf-icon"
            style={{ '--pf-color': def.color } as React.CSSProperties}
            title={def.name}
            aria-label={def.name}
          >
            <def.Icon />
            {label ? <span className="pf-label">{label}</span> : null}
          </span>
        )
      })}
      {overflow > 0 ? (
        <span className="pf-overflow" title={defs.slice(limit).map((d) => d.name).join(', ')}>
          +{overflow}
        </span>
      ) : null}
    </div>
  )
}
