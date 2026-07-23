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

function resetFiltersForRange(minYear: number, maxYear: number): GameFilters {
  return {
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
  }
}

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

function QuickFilters({
  facets,
  filters,
  onChange,
  qualityIndex,
}: Pick<FilterBarProps, 'facets' | 'filters' | 'onChange'> & {
  qualityIndex: number
}) {
  return (
    <div className="quick-filters">
      <select aria-label="Genre" value={filters.genre} onChange={(event) => onChange((current) => ({ ...current, genre: event.target.value }))}>
        <option value="">All Genres</option>
        {facets.genres.map((genre) => <option value={genre} key={genre}>{genre}</option>)}
      </select>
      <select aria-label="Platform" value={filters.platform} onChange={(event) => onChange((current) => ({ ...current, platform: event.target.value }))}>
        <option value="">All Platforms</option>
        {facets.platforms.map((platform) => <option value={platform} key={platform}>{platform}</option>)}
      </select>
      <div className="pill-select-wrapper">
        <span className="pill-label">No. of Ratings:</span>
        <select aria-label="Minimum ratings count" value={filters.minRatings} onChange={(event) => onChange((current) => ({ ...current, minRatings: Number(event.target.value) }))}>
          {MIN_RATINGS_OPTIONS.map((option) => (
            <option value={option.value} key={option.value}>{option.label}</option>
          ))}
        </select>
      </div>
      <div className="pill-select-wrapper">
        <span className="pill-label">Sources:</span>
        <select
          aria-label="Minimum quality sources"
          value={qualityIndex}
          onChange={(event) => {
            const option = QUALITY_OPTIONS[Number(event.target.value)]
            if (option) {
              onChange((current) => ({
                ...current,
                minLiveSources: option.minSources,
                requireCritic: option.critic,
              }))
            }
          }}
        >
          {QUALITY_OPTIONS.map((option, index) => (
            <option value={index} key={index}>{option.label}</option>
          ))}
        </select>
      </div>
    </div>
  )
}

function RangeField({
  label,
  max,
  min,
  onChangeMax,
  onChangeMin,
  valueMax,
  valueMin,
}: DualRangeProps & { label: string }) {
  return (
    <div className="range-field">
      <label>{label}</label>
      <div className="range-row">
        <DualRangeSlider
          min={min}
          max={max}
          valueMin={valueMin}
          valueMax={valueMax}
          onChangeMin={onChangeMin}
          onChangeMax={onChangeMax}
        />
      </div>
    </div>
  )
}

function AdvancedFilters({
  facets,
  filters,
  onChange,
  playtimeIndex,
}: Pick<FilterBarProps, 'facets' | 'filters' | 'onChange'> & {
  playtimeIndex: number
}) {
  return (
    <div className="advanced-filters">
      <select aria-label="Player mode" value={filters.playerMode} onChange={(event) => onChange((current) => ({ ...current, playerMode: event.target.value as PlayerMode | '' }))}>
        {PLAYER_MODE_OPTIONS.map((option) => (
          <option value={option.value} key={option.value || 'any'}>{option.label}</option>
        ))}
      </select>
      <select aria-label="Studio" value={filters.developer} onChange={(event) => onChange((current) => ({ ...current, developer: event.target.value }))}>
        <option value="">Any studio</option>
        {facets.developers.map((developer) => <option value={developer} key={developer}>{developer}</option>)}
      </select>
      <select
        aria-label="Playtime"
        value={playtimeIndex}
        onChange={(event) => {
          const option = PLAYTIME_OPTIONS[Number(event.target.value)]
          if (option) {
            onChange((current) => ({
              ...current,
              playtimeMinHours: option.min,
              playtimeMaxHours: option.max,
            }))
          }
        }}
      >
        {PLAYTIME_OPTIONS.map((option, index) => (
          <option value={index} key={option.label}>{option.label}</option>
        ))}
      </select>
    </div>
  )
}

function FilterActions({
  onReset,
  onToggleMore,
  showMore,
}: {
  onReset: () => void
  onToggleMore: () => void
  showMore: boolean
}) {
  return (
    <div className="filter-actions">
      <button type="button" className="ghost-button" onClick={onReset}>
        <RotateCcw size={14} aria-hidden="true" />
        Reset
      </button>
      <button type="submit" className="apply-button">Apply</button>
      <button type="button" className="ghost-button" onClick={onToggleMore}>
        More Options
        <ChevronDown
          size={14}
          aria-hidden="true"
          style={{
            transform: showMore ? 'rotate(180deg)' : undefined,
            transition: 'transform 0.2s',
          }}
        />
      </button>
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
    onChange(resetFiltersForRange(minYear, maxYear))
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
      <QuickFilters
        facets={facets}
        filters={filters}
        onChange={onChange}
        qualityIndex={qualityIndex}
      />
      <RangeField
        label="Year"
        min={minYear}
        max={maxYear}
        valueMin={draftYearMin}
        valueMax={draftYearMax}
        onChangeMin={setDraftYearMin}
        onChangeMax={setDraftYearMax}
      />
      <RangeField
        label="GameMetrix Score"
        min={0}
        max={100}
        valueMin={draftScoreMin}
        valueMax={draftScoreMax}
        onChangeMin={setDraftScoreMin}
        onChangeMax={setDraftScoreMax}
      />
      <FilterActions
        onReset={resetFilters}
        onToggleMore={() => setShowMore((open) => !open)}
        showMore={showMore}
      />

      {showMore ? (
        <AdvancedFilters
          facets={facets}
          filters={filters}
          onChange={onChange}
          playtimeIndex={playtimeIndex}
        />
      ) : null}
    </form>
  )
}
