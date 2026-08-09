import type { CSSProperties } from 'react'

// Same 8/15 breakpoints as max_difficulty_for_level in
// app/core/training_block.py (backend) -- purely cosmetic here, but reusing
// the numbers rather than inventing a second set that could drift from the
// gameplay-facing thresholds.
const AVATAR_TIER_LEVEL_THRESHOLDS = { MID: 8, TOP: 15 } as const

const ICE = '#D7EFFF'
const PERSIMMON = '#FF5C34'
// Matches the `dark-bg` Tailwind token (tailwind.config.js) -- the tier-3
// border needs an actual color here, not just "transparent", because it's
// built from two stacked background-image layers (see below), not a plain
// `border-color`.
const DARK_BG = '#111827'

export type AvatarTier = 1 | 2 | 3

export interface AvatarTierStyle {
  tier: AvatarTier
  style: CSSProperties
}

// Plain function, not a `use*` hook -- it's a pure derivation from `level`
// with no state/effects of its own, so naming it like a hook would only
// invite react-hooks lint rules that don't apply here.
export function getAvatarTierStyle(level: number): AvatarTierStyle {
  if (level >= AVATAR_TIER_LEVEL_THRESHOLDS.TOP) {
    return {
      tier: 3,
      style: {
        border: '3px solid transparent',
        // Two-layer background-clip trick for a gradient border: the first
        // (solid) layer fills the interior up to the padding box, so it
        // reads as the same dark disc as tiers 1-2 behind the photo/
        // fallback icon; the second (gradient) layer paints only the ring
        // between padding-box and border-box.
        backgroundImage: `linear-gradient(${DARK_BG}, ${DARK_BG}), linear-gradient(135deg, ${ICE}, ${PERSIMMON})`,
        backgroundOrigin: 'border-box',
        backgroundClip: 'padding-box, border-box',
        boxShadow: `0 0 16px rgba(215,239,255,0.45), 0 0 16px rgba(255,92,52,0.3)`,
      },
    }
  }
  if (level >= AVATAR_TIER_LEVEL_THRESHOLDS.MID) {
    return {
      tier: 2,
      style: {
        border: `3px solid ${ICE}`,
        boxShadow: '0 0 12px rgba(215,239,255,0.4)',
      },
    }
  }
  return {
    tier: 1,
    style: {
      border: `2px solid ${ICE}`,
    },
  }
}
