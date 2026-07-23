import type React from 'react'
import type { Game } from '../types/game'
import { storeUrlForGroup } from '../utils/storeLinks'
import './PlatformIcons.css'

// ─── Platform icon SVGs ───────────────────────────────────────────────────────
// All icons: 16×16 viewBox, fill="currentColor" for CSS color control.
// Intrinsic width/height keep the icons at a sane size even before CSS applies —
// a viewBox-only SVG falls back to the 300×150 replaced-element default. CSS
// still controls the final size (14px list, 16px detail) since it overrides
// presentation attributes.

const BrandIcon = ({ paths }: { paths: string[] }) => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {paths.map((path) => <path d={path} key={path} />)}
  </svg>
)

const WindowsIcon = () => (
  <BrandIcon paths={[
    'M6.555 1.375 0 2.237v5.45h6.555zM0 13.795l6.555.933V8.313H0zm7.278-5.4.026 6.378L16 16V8.395zM16 0 7.33 1.244v6.414H16z',
  ]} />
)

const SteamIcon = () => (
  <BrandIcon paths={[
    'M.329 10.333A8.01 8.01 0 0 0 7.99 16C12.414 16 16 12.418 16 8s-3.586-8-8.009-8A8.006 8.006 0 0 0 0 7.468l.003.006 4.304 1.769A2.2 2.2 0 0 1 5.62 8.88l1.96-2.844-.001-.04a3.046 3.046 0 0 1 3.042-3.043 3.046 3.046 0 0 1 3.042 3.043 3.047 3.047 0 0 1-3.111 3.044l-2.804 2a2.223 2.223 0 0 1-3.075 2.11 2.22 2.22 0 0 1-1.312-1.568L.33 10.333Z',
    'M4.868 12.683a1.715 1.715 0 0 0 1.318-3.165 1.7 1.7 0 0 0-1.263-.02l1.023.424a1.261 1.261 0 1 1-.97 2.33l-.99-.41a1.7 1.7 0 0 0 .882.84Zm3.726-6.687a2.03 2.03 0 0 0 2.027 2.029 2.03 2.03 0 0 0 2.027-2.029 2.03 2.03 0 0 0-2.027-2.027 2.03 2.03 0 0 0-2.027 2.027m2.03-1.527a1.524 1.524 0 1 1-.002 3.048 1.524 1.524 0 0 1 .002-3.048',
  ]} />
)

const PsIcon = () => (
  <BrandIcon paths={[
    'M15.858 11.451c-.313.395-1.079.676-1.079.676l-5.696 2.046v-1.509l4.192-1.493c.476-.17.549-.412.162-.538-.386-.127-1.085-.09-1.56.08l-2.794.984v-1.566l.161-.054s.807-.286 1.942-.412c1.135-.125 2.525.017 3.616.43 1.23.39 1.368.962 1.056 1.356M9.625 8.883v-3.86c0-.453-.083-.87-.508-.988-.326-.105-.528.198-.528.65v9.664l-2.606-.827V2c1.108.206 2.722.692 3.59.985 2.207.757 2.955 1.7 2.955 3.825 0 2.071-1.278 2.856-2.903 2.072Zm-8.424 3.625C-.061 12.15-.271 11.41.304 10.984c.532-.394 1.436-.69 1.436-.69l3.737-1.33v1.515l-2.69.963c-.474.17-.547.411-.161.538.386.126 1.085.09 1.56-.08l1.29-.469v1.356l-.257.043a8.45 8.45 0 0 1-4.018-.323Z',
  ]} />
)

const XboxIcon = () => (
  <BrandIcon paths={[
    'M7.202 15.967a8 8 0 0 1-3.552-1.26c-.898-.585-1.101-.826-1.101-1.306 0-.965 1.062-2.656 2.879-4.583C6.459 7.723 7.897 6.44 8.052 6.475c.302.068 2.718 2.423 3.622 3.531 1.43 1.753 2.088 3.189 1.754 3.829-.254.486-1.83 1.437-2.987 1.802-.954.301-2.207.429-3.239.33m-5.866-3.57C.589 11.253.212 10.127.03 8.497c-.06-.539-.038-.846.137-1.95.218-1.377 1.002-2.97 1.945-3.95.401-.417.437-.427.926-.263.595.2 1.23.638 2.213 1.528l.574.519-.313.385C4.056 6.553 2.52 9.086 1.94 10.653c-.315.852-.442 1.707-.306 2.063.091.24.007.15-.3-.319Zm13.101.195c.074-.36-.019-1.02-.238-1.687-.473-1.443-2.055-4.128-3.508-5.953l-.457-.575.494-.454c.646-.593 1.095-.948 1.58-1.25.381-.237.927-.448 1.161-.448.145 0 .654.528 1.065 1.104a8.4 8.4 0 0 1 1.343 3.102c.153.728.166 2.286.024 3.012a9.5 9.5 0 0 1-.6 1.893c-.179.393-.624 1.156-.82 1.404-.1.128-.1.127-.043-.148ZM7.335 1.952c-.67-.34-1.704-.705-2.276-.803a4 4 0 0 0-.759-.043c-.471.024-.45 0 .306-.358A7.8 7.8 0 0 1 6.47.128c.8-.169 2.306-.17 3.094-.005.85.18 1.853.552 2.418.9l.168.103-.385-.02c-.766-.038-1.88.27-3.078.853-.361.176-.676.316-.699.312a12 12 0 0 1-.654-.319Z',
  ]} />
)

const SwitchIcon = () => (
  <BrandIcon paths={[
    'M9.34 8.005c0-4.38.01-7.972.023-7.982C9.373.01 10.036 0 10.831 0c1.153 0 1.51.01 1.743.05 1.73.298 3.045 1.6 3.373 3.326.046.242.053.809.053 4.61 0 4.06.005 4.537-.123 4.976-.022.076-.048.15-.08.242a4.14 4.14 0 0 1-3.426 2.767c-.317.033-2.889.046-2.978.013-.05-.02-.053-.752-.053-7.979m4.675.269a1.62 1.62 0 0 0-1.113-1.034 1.61 1.61 0 0 0-1.938 1.073 1.9 1.9 0 0 0-.014.935 1.63 1.63 0 0 0 1.952 1.107c.51-.136.908-.504 1.11-1.028.11-.285.113-.742.003-1.053M3.71 3.317c-.208.04-.526.199-.695.348-.348.301-.52.729-.494 1.232.013.262.03.332.136.544.155.321.39.556.712.715.222.11.278.123.567.133.261.01.354 0 .53-.06.719-.242 1.153-.94 1.03-1.656-.142-.852-.95-1.422-1.786-1.256',
    'M3.425.053a4.14 4.14 0 0 0-3.28 3.015C0 3.628-.01 3.956.005 8.3c.01 3.99.014 4.082.08 4.39.368 1.66 1.548 2.844 3.224 3.235.22.05.497.06 2.29.07 1.856.012 2.048.009 2.097-.04.05-.05.053-.69.053-7.94 0-5.374-.01-7.906-.033-7.952-.033-.06-.09-.063-2.03-.06-1.578.004-2.052.014-2.26.05Zm3 14.665-1.35-.016c-1.242-.013-1.375-.02-1.623-.083a2.81 2.81 0 0 1-2.08-2.167c-.074-.335-.074-8.579-.004-8.907a2.85 2.85 0 0 1 1.716-2.05c.438-.176.64-.196 2.058-.2l1.282-.003v13.426Z',
  ]} />
)

// Apple logo path, inlined (viewBox 0 0 24 24) to match the other brand icons in
// this file and drop the whole simple-icons dependency used for this one glyph.
const APPLE_PATH =
  'M12.152 6.896c-.948 0-2.415-1.078-3.96-1.04-2.04.027-3.91 1.183-4.961 3.014-2.117 3.675-.546 9.103 1.519 12.09 1.013 1.454 2.208 3.09 3.792 3.039 1.52-.065 2.09-.987 3.935-.987 1.831 0 2.35.987 3.96.948 1.637-.026 2.676-1.48 3.676-2.948 1.156-1.688 1.636-3.325 1.662-3.415-.039-.013-3.182-1.221-3.22-4.857-.026-3.04 2.48-4.494 2.597-4.559-1.429-2.09-3.623-2.324-4.39-2.376-2-.156-3.675 1.09-4.61 1.09zM15.53 3.83c.843-1.012 1.4-2.427 1.245-3.83-1.207.052-2.662.805-3.532 1.818-.78.896-1.454 2.338-1.273 3.714 1.338.104 2.715-.688 3.559-1.701'

const AppleIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path d={APPLE_PATH} />
  </svg>
)

const LinuxIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {/* Tux: round head with ears, eyes, beak, body */}
    <path d="M8 1C6.3 1 5 2.5 5 4c0 1 .4 2 1 2.7-1.3.5-3 1.6-3 3.8 0 1.8 1.2 2.5 2 2.5.5 0 1-.2 1.5-.5 1 .5 1.7.7 2.5.7s1.5-.2 2.5-.7c.5.3 1 .5 1.5.5.8 0 2-.7 2-2.5 0-2.2-1.7-3.3-3-3.8.6-.7 1-1.7 1-2.7C13 2.5 11.7 1 10 1c-.7 0-1.3.3-1.7.7L8 1.5l-.3.2C7.3 1.3 6.7 1 8 1zM7 3.5a1 1 0 112 0 1 1 0 01-2 0zm-1 7a.75.75 0 110-1.5.75.75 0 010 1.5zm4 0a.75.75 0 110-1.5.75.75 0 010 1.5z" />
  </svg>
)

const AndroidIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {/* Android robot head */}
    <path d="M5.18 3.7L3.9 1.5l.87-.5 1.28 2.2C6.6 3.1 7.3 3 8 3s1.4.1 1.95.2L11.23 1l.87.5L10.82 3.7A5 5 0 0113 8H3a5 5 0 012.18-4.3zM5.5 6a.75.75 0 100 1.5A.75.75 0 005.5 6zm5 0a.75.75 0 100 1.5.75.75 0 000-1.5zM3 9h10v2.5c0 .83-.67 1.5-1.5 1.5H11v2h-1.5v-2h-3v2H5v-2H4.5C3.67 13 3 12.33 3 11.5V9z" />
  </svg>
)

const GogIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
    {/* GOG.com: G in a circle */}
    <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm.5 4.5H11v5H9.5V9H7.5v-1.5h2V7H7a2 2 0 00-2 2 2 2 0 002 2h1V9.5H6.5A.5.5 0 016 9a.5.5 0 01.5-.5H8V10h.5v.5H7a3.5 3.5 0 110-7h1.5v2z" />
  </svg>
)

const EpicIcon = () => (
  <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
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
  Icon: () => React.ReactElement
}

// Each entry: canonical key → display info
const PLATFORM_DEFS: Record<string, PlatformDef> = {
  pc:         { name: 'Windows PC',       short: 'Win',  color: '#00A4EF', group: 'pc',    priority: 2, Icon: WindowsIcon },
  steam:      { name: 'Steam',            short: 'Steam',color: '#66C0F4', group: 'pc',    priority: 1, Icon: SteamIcon },
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
  /** When provided, icons become links to the game's store page (price
   *  snapshot URL → Steam app page → store search, in that order). */
  game?: Game
}

export function PlatformIcons({ platforms, mode = 'list', maxVisible, game }: PlatformIconsProps) {
  const defaultMax = mode === 'compact' ? 4 : 99
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
        const href = game ? storeUrlForGroup(def.group, game) : null
        const style = { '--pf-color': def.color } as React.CSSProperties
        if (href) {
          return (
            <a
              key={def.group}
              className="pf-icon pf-icon-link"
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              style={style}
              title={`${def.name} — view in store`}
              aria-label={`${def.name} store page`}
            >
              <def.Icon />
              {label ? <span className="pf-label">{label}</span> : null}
            </a>
          )
        }
        return (
          <span
            key={def.group}
            className="pf-icon"
            style={style}
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
