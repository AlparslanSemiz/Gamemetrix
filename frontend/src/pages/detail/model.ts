import type { CSSProperties } from 'react'
import type { Game, PriceSnapshot } from '../../types/game'
import { bestCoverUrl } from '../../utils/coverImage'
import { isEndlessGame } from '../../utils/playtime'
import {
  PROTON_TIER_LABELS,
  formatProtonScore,
  isProtonTier,
} from '../../utils/proton'
import { PANEL_PRICE_MAX_AGE_MS, currentPriceSnapshots } from '../../utils/prices'
import { scoreColor, scoreColorRgb } from '../../utils/scoreColors'
import { steamAppIdFromGame } from '../../utils/steam'
import { safeExternalUrl } from '../../utils/url'
import { formatDate } from './format'

export interface PlaytimeDetail {
  detailRows: [string, number][]
  endless: boolean
  hasData: boolean
  primaryMinutes: number
  url: string | null
}

export interface GameDetailModel {
  aboutParagraphs: string[]
  backgroundImage: string
  detailStyle: CSSProperties
  earlyAccessSuffix: string
  gameModes: string[]
  playtime: PlaytimeDetail
  priceSnapshots: PriceSnapshot[]
  primaryReleaseLabel: string
  protonText: string | null
  protonUrl: string
  releaseLabel: string
  websiteUrl: string | null
}

export function buildGameDetailModel(game: Game): GameDetailModel {
  const releaseLabel = game.release_year > 1970
    ? new Date(game.release_date).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : 'Unknown'
  const earlyAccessLabel = formatDate(game.early_access_date)
  const officialReleaseLabel = formatDate(
    game.official_release_date ?? game.release_date,
  )
  const primaryReleaseLabel = officialReleaseLabel !== 'Not tracked'
    ? officialReleaseLabel
    : releaseLabel
  const earlyAccessSuffix = (
    earlyAccessLabel !== 'Not tracked'
    && earlyAccessLabel !== primaryReleaseLabel
  )
    ? ` · Early access ${earlyAccessLabel}`
    : ''
  const displayScore = Math.round(game.metrix_score)
  const steamAppId = steamAppIdFromGame(game)

  return {
    aboutParagraphs: aboutParagraphs(game),
    backgroundImage: bestCoverUrl(game),
    detailStyle: {
      '--score-color': scoreColor(displayScore),
      '--score-rgb': scoreColorRgb(displayScore),
    } as CSSProperties,
    earlyAccessSuffix,
    gameModes: (game.game_modes ?? []).filter(Boolean),
    playtime: playtimeDetail(game),
    priceSnapshots: currentPriceSnapshots(game.price_snapshots ?? [], PANEL_PRICE_MAX_AGE_MS),
    primaryReleaseLabel,
    protonText: protonLabel(game),
    protonUrl: steamAppId
      ? `https://www.protondb.com/app/${steamAppId}`
      : 'https://www.protondb.com/',
    releaseLabel,
    websiteUrl: safeExternalUrl(game.website_url),
  }
}

function playtimeDetail(game: Game): PlaytimeDetail {
  const primaryMinutes = (
    game.hltb_main_story_minutes
    || game.playtime_minutes
    || game.hltb_all_styles_minutes
    || game.hltb_completionist_minutes
    || game.hltb_main_extra_minutes
  )
  const detailRows = ([
    ['Extra', game.hltb_main_extra_minutes],
    ['100%', game.hltb_completionist_minutes],
    ['Avg', game.hltb_all_styles_minutes],
  ] as [string, number][]).filter(([, minutes]) => Number(minutes) > 0)
  return {
    detailRows,
    endless: isEndlessGame(game),
    hasData: primaryMinutes > 0 || detailRows.length > 0,
    primaryMinutes,
    url: safeExternalUrl(game.hltb_url),
  }
}

function protonLabel(game: Game): string | null {
  const tier = game.proton_tier
  if (!tier || !isProtonTier(tier)) return null
  const scoreText = formatProtonScore(game.proton_score)
  return scoreText
    ? `${PROTON_TIER_LABELS[tier]} · ${scoreText}`
    : PROTON_TIER_LABELS[tier]
}

function aboutParagraphs(game: Game): string[] {
  const summary = (game.summary ?? '').trim()
  if (!summary) return []
  return summary
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
}
