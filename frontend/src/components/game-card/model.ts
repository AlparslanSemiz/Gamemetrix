import type { CSSProperties } from 'react'
import type { Game, SourceScore } from '../../types/game'
import { bestCoverUrl } from '../../utils/coverImage'
import { formatPlaytimeHours, isEndlessGame } from '../../utils/playtime'
import { isProtonTier } from '../../utils/proton'
import { CARD_PRIMARY_SOURCE_ORDER } from '../../utils/ratingSources'
import { scoreColor, scoreColorRgb } from '../../utils/scoreColors'
import { safeExternalUrl } from '../../utils/url'
import type { GameCardModel } from './types'

const ALL_PRIMARY_SOURCES = new Set<string>(CARD_PRIMARY_SOURCE_ORDER)

export function buildGameCardModel(game: Game): GameCardModel {
  const isEndless = isEndlessGame(game)
  const hltbMinutes = game.hltb_main_story_minutes > 0
    ? game.hltb_main_story_minutes
    : game.playtime_minutes
  const playtimeLabel = isEndless
    ? '∞'
    : hltbMinutes > 0
      ? formatPlaytimeHours(hltbMinutes)
      : null
  const protonTier = game.proton_tier && isProtonTier(game.proton_tier)
    ? game.proton_tier
    : null
  const applicableSources = new Set(
    game.applicable_sources?.length
      ? game.applicable_sources
      : ALL_PRIMARY_SOURCES,
  )
  const displayedSources = buildDisplayedSources(game, applicableSources)
  const livePrimaryCount = displayedSources.filter(
    (source) => source.status === 'live' && source.score > 0,
  ).length
  const confidenceLevel = game.confidence_level ?? 'Limited'
  const isRankedLower = (
    game.content_type === 'game'
    && game.is_rankable === false
    && confidenceLevel !== 'Catalog'
  )
  const coverSrc = bestCoverUrl(game)
  const displayScore = Math.round(game.metrix_score)

  return {
    cardStyle: {
      '--score-color': scoreColor(displayScore),
      '--score-rgb': scoreColorRgb(displayScore),
      '--cover-image': `url("${coverSrc.replaceAll('"', '\\"')}")`,
    } as CSSProperties,
    coverSrc,
    displayedSources,
    applicableSourceCount: game.applicable_source_count ?? applicableSources.size,
    confidenceLevel,
    confidenceTitle: isRankedLower
      ? 'Score based on limited source coverage. Ranked lower in default lists until more sources confirm this rating.'
      : 'Confidence is based on live Metacritic, OpenCritic, IGDB, and Steam coverage.',
    hltbHref: safeExternalUrl(game.hltb_url)
      ?? `https://howlongtobeat.com/?q=${encodeURIComponent(game.title)}`,
    hltbMinutes,
    isEndless,
    isRankedLower,
    playtimeLabel,
    primarySourceCount: game.live_primary_source_count ?? livePrimaryCount,
    protonTier,
    scoreProfile: game.score_profile ?? 'sparse',
  }
}

function buildDisplayedSources(
  game: Game,
  applicableSources: Set<string>,
): SourceScore[] {
  const scoreBySource = new Map(
    game.source_scores.map((source) => [source.source, source]),
  )
  return CARD_PRIMARY_SOURCE_ORDER.map((source) => (
    scoreBySource.get(source) ?? {
      source,
      score: 0,
      scale: 100,
      status: 'unavailable',
      detail: applicableSources.has(source)
        ? 'Rating pending.'
        : 'Not applicable to this platform.',
    }
  ))
}

export function playtimeColor(minutes: number): string {
  const hours = minutes / 60
  let score: number
  if (hours >= 50 && hours <= 60) {
    score = 100
  } else if (hours < 50) {
    score = Math.max(0, (hours / 50) * 100)
  } else {
    score = Math.max(0, 100 - ((hours - 60) / 160) * 100)
  }
  if (score >= 80) return '#16a34a'
  if (score >= 65) return '#22c55e'
  if (score >= 50) return '#84cc16'
  if (score >= 35) return '#eab308'
  if (score >= 20) return '#ea580c'
  return '#dc2626'
}

export function hltbTooltip(game: Game): string {
  const rows = [
    ['Main', game.hltb_main_story_minutes],
    ['Extra', game.hltb_main_extra_minutes],
    ['100%', game.hltb_completionist_minutes],
    ['Avg', game.hltb_all_styles_minutes],
  ]
    .filter(([, minutes]) => Number(minutes) > 0)
    .map(([label, minutes]) => (
      `${label}: ${formatPlaytimeHours(Number(minutes))}`
    ))
  return rows.length > 0
    ? `HowLongToBeat - ${rows.join(' | ')}`
    : 'HowLongToBeat - click to search'
}
