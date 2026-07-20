import { type Dispatch, type SetStateAction, useState } from 'react'
import { ChevronDown, RotateCcw } from 'lucide-react'
import type { Facets, GameFilters, PlayerMode } from '../types/game'

interface FilterBarProps {
  facets: Facets
  filters: GameFilters
  onChange: Dispatch<SetStateAction<GameFilters>>
  onApply: () => void
}

const CURRENT_YEAR = new Date().getFullYear()

const MIN_RATINGS_OPTIONS = [
  { label: 'Any', value: 0 },
  { label: '> 500', value: 500 },
  { label: '> 1,000', value: 1000 },
  { label: '> 10,000', value: 10000 },
  { label: '> 100,000', value: 100000 },
]

const QUALITY_OPTIONS = [
  { label: 'Any', minSources: 0, critic: false },
  { label: 'Critic score', minSources: 1, critic: true },
  { label: '2+ primary', minSources: 2, critic: false },
  { label: 'Critic + 2 src', minSources: 2, critic: true },
]

const PLAYER_MODE_OPTIONS: Array<{ label: string; value: PlayerMode | '' }> = [
  { label: 'Any player mode', value: '' },
  { label: 'Single-player', value: 'singleplayer' },
  { label: 'Multiplayer', value: 'multiplayer' },
  { label: 'Co-op', value: 'coop' },
]

const PLAYTIME_OPTIONS: Array<{ label: string; min: number | null; max: number | null }> = [
  { label: 'Any playtime', min: null, max: null },
  { label: 'Under 10 hours', min: null, max: 10 },
  { label: '10–30 hours', min: 10, max: 30 },
  { label: '30–80 hours', min: 30, max: 80 },
  { label: '80+ hours', min: 80, max: null },
]

interface DualRangeProps {
  min: number
  max: number
  valueMin: number
  valueMax: number
  onChangeMin: (v: number) => void
  onChangeMax: (v: number) => void
}

function DualRangeSlider({ min, max, valueMin, valueMax, onChangeMin, onChangeMax }: DualRangeProps) {
  const range = max - min || 1
  // Fill always spans lo→hi regardless of which thumb is where
  const lo = Math.min(valueMin, valueMax)
  const hi = Math.max(valueMin, valueMax)
  const fillLeft = ((lo - min) / range) * 100
  const fillRight = ((max - hi) / range) * 100
  // Compensate for browser thumb offset at the edges (18px thumb width)
  const loAdj = (0.5 - fillLeft / 100) * 18
  const hiAdj = (0.5 - (100 - fillRight) / 100) * 18

  return (
    <div className="range-dual-wrapper">
      <span className="range-floating-value" style={{ left: `calc(${fillLeft}% + ${loAdj}px)` }}>
        {lo}
      </span>
      <span className="range-floating-value" style={{ left: `calc(${100 - fillRight}% + ${hiAdj}px)` }}>
        {hi}
      </span>
      <div className="range-dual-track">
        <div className="range-dual-fill" style={{ left: `${fillLeft}%`, right: `${fillRight}%` }} />
      </div>
      <input
        type="range" min={min} max={max} value={valueMin} className="range-thumb"
        onChange={(e) => onChangeMin(Number(e.target.value))}
      />
      <input
        type="range" min={min} max={max} value={valueMax} className="range-thumb"
        onChange={(e) => onChangeMax(Number(e.target.value))}
      />
    </div>
  )
}

export function FilterBar({ facets, filters, onChange, onApply }: FilterBarProps) {
  const [showMore, setShowMore] = useState(false)

  const minYear = facets.years.length > 0 ? Math.min(...facets.years) : 1970
  const maxYear = facets.years.length > 0
    ? Math.min(Math.max(...facets.years), CURRENT_YEAR)
    : CURRENT_YEAR

  // Local draft state for year and score ranges — committed only on Apply.
  const [draftYearMin, setDraftYearMin] = useState(Math.max(filters.yearMin, minYear))
  const [draftYearMax, setDraftYearMax] = useState(Math.min(filters.yearMax, maxYear))
  const [draftScoreMin, setDraftScoreMin] = useState(filters.minScore)
  const [draftScoreMax, setDraftScoreMax] = useState(filters.maxScore)

  const resetFilters = () => {
    setDraftYearMin(minYear)
    setDraftYearMax(maxYear)
    setDraftScoreMin(0)
    setDraftScoreMax(100)
    onChange({
      q: '',
      genre: '',
      platform: '',
      developer: '',
      publisher: '',
      yearMin: minYear,
      yearMax: maxYear,
      minScore: 0,
      maxScore: 100,
      minRatings: 0,
      maxRatings: 0,
      minLiveSources: 0,
      requireCritic: false,
      hasAward: false,
      dealMode: 'all',
      playerMode: '',
      playtimeMinHours: null,
      playtimeMaxHours: null,
      sort: 'rank_score',
      direction: 'desc',
    })
  }

  const handleApply = () => {
    onChange((cur) => ({
      ...cur,
      yearMin: draftYearMin,
      yearMax: draftYearMax,
      minScore: draftScoreMin,
      maxScore: draftScoreMax,
    }))
    onApply()
  }

  const activeQuality = QUALITY_OPTIONS.find(
    (o) => o.minSources === filters.minLiveSources && o.critic === filters.requireCritic,
  ) ?? QUALITY_OPTIONS[0]

  const qualityIndex = QUALITY_OPTIONS.indexOf(activeQuality)

  const playtimeIndex = Math.max(
    0,
    PLAYTIME_OPTIONS.findIndex(
      (o) => o.min === filters.playtimeMinHours && o.max === filters.playtimeMaxHours,
    ),
  )

  return (
    <form className="filters" onSubmit={(e) => { e.preventDefault(); handleApply() }}>

      {/* Quick-filter pill row */}
      <div className="quick-filters">
        <select
          aria-label="Genre"
          value={filters.genre}
          onChange={(e) => onChange((c) => ({ ...c, genre: e.target.value }))}
        >
          <option value="">All Genres</option>
          {facets.genres.map((g) => <option value={g} key={g}>{g}</option>)}
        </select>

        <select
          aria-label="Platform"
          value={filters.platform}
          onChange={(e) => onChange((c) => ({ ...c, platform: e.target.value }))}
        >
          <option value="">All Platforms</option>
          {facets.platforms.map((p) => <option value={p} key={p}>{p}</option>)}
        </select>

        {/* Min ratings pill */}
        <div className="pill-select-wrapper">
          <span className="pill-label">No. of Ratings:</span>
          <select
            aria-label="Minimum ratings count"
            value={filters.minRatings}
            onChange={(e) => onChange((c) => ({ ...c, minRatings: Number(e.target.value) }))}
          >
            {MIN_RATINGS_OPTIONS.map((o) => (
              <option value={o.value} key={o.value}>{o.label}</option>
            ))}
          </select>
        </div>

        {/* Quality sources pill */}
        <div className="pill-select-wrapper">
          <span className="pill-label">Sources:</span>
          <select
            aria-label="Minimum quality sources"
            value={qualityIndex}
            onChange={(e) => {
              const opt = QUALITY_OPTIONS[Number(e.target.value)]
              if (opt) {
                onChange((c) => ({
                  ...c,
                  minLiveSources: opt.minSources,
                  requireCritic: opt.critic,
                }))
              }
            }}
          >
            {QUALITY_OPTIONS.map((o, i) => (
              <option value={i} key={i}>{o.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Year range */}
      <div className="range-field">
        <label>Year</label>
        <div className="range-row">
          <DualRangeSlider
            min={minYear} max={maxYear}
            valueMin={draftYearMin} valueMax={draftYearMax}
            onChangeMin={setDraftYearMin} onChangeMax={setDraftYearMax}
          />
        </div>
      </div>

      {/* Score range (dual) */}
      <div className="range-field">
        <label>GameMetrix Score</label>
        <div className="range-row">
          <DualRangeSlider
            min={0} max={100}
            valueMin={draftScoreMin} valueMax={draftScoreMax}
            onChangeMin={setDraftScoreMin} onChangeMax={setDraftScoreMax}
          />
        </div>
      </div>

      {/* Actions row */}
      <div className="filter-actions">
        <button type="button" className="ghost-button" onClick={resetFilters}>
          <RotateCcw size={14} aria-hidden="true" />
          Reset
        </button>
        <button type="submit" className="apply-button">Apply</button>
        <button
          type="button"
          className="ghost-button"
          onClick={() => setShowMore((p) => !p)}
        >
          More Options
          <ChevronDown
            size={14}
            aria-hidden="true"
            style={{ transform: showMore ? 'rotate(180deg)' : undefined, transition: 'transform 0.2s' }}
          />
        </button>
      </div>

      {showMore ? (
        <div className="advanced-filters">
          <select
            aria-label="Player mode"
            value={filters.playerMode}
            onChange={(e) => onChange((c) => ({ ...c, playerMode: e.target.value as PlayerMode | '' }))}
          >
            {PLAYER_MODE_OPTIONS.map((o) => (
              <option value={o.value} key={o.value || 'any'}>{o.label}</option>
            ))}
          </select>

          <select
            aria-label="Studio"
            value={filters.developer}
            onChange={(e) => onChange((c) => ({ ...c, developer: e.target.value }))}
          >
            <option value="">Any studio</option>
            {facets.developers.map((d) => <option value={d} key={d}>{d}</option>)}
          </select>

          <select
            aria-label="Playtime"
            value={playtimeIndex}
            onChange={(e) => {
              const opt = PLAYTIME_OPTIONS[Number(e.target.value)]
              if (opt) {
                onChange((c) => ({ ...c, playtimeMinHours: opt.min, playtimeMaxHours: opt.max }))
              }
            }}
          >
            {PLAYTIME_OPTIONS.map((o, i) => (
              <option value={i} key={o.label}>{o.label}</option>
            ))}
          </select>
        </div>
      ) : null}
    </form>
  )
}
