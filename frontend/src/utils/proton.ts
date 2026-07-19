import type { ProtonTier } from '../types/game'

export const PROTON_TIER_LABELS: Record<ProtonTier, string> = {
  platinum: 'Platinum',
  gold: 'Gold',
  silver: 'Silver',
  bronze: 'Bronze',
  borked: 'Borked',
}

export const PROTON_TIER_DESCRIPTIONS: Record<ProtonTier, string> = {
  platinum: 'Runs perfectly out of the box',
  gold: 'Runs perfectly after tweaks',
  silver: 'Runs with minor issues',
  bronze: 'Runs, but crashes often or has major issues',
  borked: 'Does not run',
}

export function isProtonTier(value: string): value is ProtonTier {
  return value in PROTON_TIER_LABELS
}
