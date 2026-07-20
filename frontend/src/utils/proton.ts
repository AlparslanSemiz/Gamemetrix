import type { ProtonTier } from '../types/game'

export const PROTON_TIER_LABELS: Record<ProtonTier, string> = {
  native: 'Native',
  platinum: 'Platinum',
  gold: 'Gold',
  silver: 'Silver',
  bronze: 'Bronze',
  borked: 'Borked',
}

export const PROTON_TIER_DESCRIPTIONS: Record<ProtonTier, string> = {
  native: 'Runs through a native Linux build',
  platinum: 'Runs perfectly out of the box',
  gold: 'Runs perfectly after tweaks',
  silver: 'Runs with minor issues',
  bronze: 'Runs, but crashes often or has major issues',
  borked: 'Does not run',
}

export function isProtonTier(value: string): value is ProtonTier {
  return value in PROTON_TIER_LABELS
}

export function formatProtonScore(score: number | null | undefined): string | null {
  if (typeof score !== 'number' || !Number.isFinite(score)) return null
  return String(Math.round(score))
}
