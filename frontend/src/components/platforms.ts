// Platform vocabulary and brand metadata. Deliberately JSX-free and separate from
// PlatformIcons.tsx: that file may only export components, so the lookup helpers
// non-component callers need live here. Icons are paired by key in PlatformIcons.

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

export interface PlatformMeta {
  name: string
  short: string
  color: string
  group: string
  priority: number
}

export type PlatformEntry = PlatformMeta & { key: string }

// Each entry: canonical key → display info
export const PLATFORM_META: Record<string, PlatformMeta> = {
  pc:         { name: 'Windows PC',       short: 'Win',  color: '#00A4EF', group: 'pc',    priority: 2 },
  steam:      { name: 'Steam',            short: 'Steam',color: '#66C0F4', group: 'pc',    priority: 1 },
  macos:      { name: 'macOS',            short: 'Mac',  color: '#A2AAAD', group: 'macos', priority: 1 },
  linux:      { name: 'Linux',            short: 'Linux',color: '#FCC624', group: 'linux', priority: 1 },
  ps3:        { name: 'PlayStation 3',    short: 'PS3',  color: '#0070CC', group: 'ps',    priority: 3 },
  ps4:        { name: 'PlayStation 4',    short: 'PS4',  color: '#0070CC', group: 'ps',    priority: 2 },
  ps5:        { name: 'PlayStation 5',    short: 'PS5',  color: '#0070CC', group: 'ps',    priority: 1 },
  ps:         { name: 'PlayStation',      short: 'PS',   color: '#0070CC', group: 'ps',    priority: 4 },
  xbox:       { name: 'Xbox',             short: 'XB',   color: '#107C10', group: 'xbox',  priority: 4 },
  xbox360:    { name: 'Xbox 360',         short: 'X360', color: '#107C10', group: 'xbox',  priority: 3 },
  xboxone:    { name: 'Xbox One',         short: 'XB1',  color: '#107C10', group: 'xbox',  priority: 2 },
  xboxseries: { name: 'Xbox Series X/S',  short: 'XBS',  color: '#107C10', group: 'xbox',  priority: 1 },
  switch:     { name: 'Nintendo Switch',  short: 'NSW',  color: '#E60012', group: 'switch',priority: 1 },
  ios:        { name: 'iOS',              short: 'iOS',  color: '#A2AAAD', group: 'ios',   priority: 1 },
  android:    { name: 'Android',          short: 'And',  color: '#3DDC84', group: 'android',priority:1 },
  gog:        { name: 'GOG',              short: 'GOG',  color: '#86328A', group: 'gog',   priority: 1 },
  epic:       { name: 'Epic Games Store', short: 'Epic', color: '#D3D3D3', group: 'epic',  priority: 1 },
  wii:        { name: 'Wii',              short: 'Wii',  color: '#E60012', group: 'wii',   priority: 1 },
  wiiu:       { name: 'Wii U',            short: 'WiiU', color: '#E60012', group: 'wiiu',  priority: 1 },
}

const GROUP_ORDER = ['pc', 'steam', 'ps', 'xbox', 'switch', 'macos', 'linux', 'ios', 'android', 'gog', 'epic']

// ─── Normalization helpers ────────────────────────────────────────────────────

export function normalizePlatform(raw: string): string {
  return NORMALIZE[raw.toLowerCase().trim()] ?? 'other'
}

/** Deduplicate platforms: keep only the highest-priority entry per group */
export function deduplicatePlatforms(platforms: string[]): PlatformEntry[] {
  const bestPerGroup = new Map<string, PlatformEntry>()

  for (const raw of platforms) {
    const key = normalizePlatform(raw)
    const meta = PLATFORM_META[key]
    if (!meta) continue

    const existing = bestPerGroup.get(meta.group)
    if (!existing || meta.priority < existing.priority) {
      bestPerGroup.set(meta.group, { ...meta, key })
    }
  }

  return Array.from(bestPerGroup.values()).sort(
    (a, b) => GROUP_ORDER.indexOf(a.group) - GROUP_ORDER.indexOf(b.group),
  )
}

/** Brand colour for a platform string, for callers that tint their own chrome. */
export function platformBrandColor(platform: string): string | null {
  return PLATFORM_META[normalizePlatform(platform)]?.color ?? null
}
