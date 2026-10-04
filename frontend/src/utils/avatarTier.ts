import type { CSSProperties } from 'react'
import type { AvatarRingAccent } from '../types/user'
import { hasAvatarRingChoice } from './levelUnlocks'

// Same 8/15 breakpoints as max_difficulty_for_level in
// app/core/training_block.py (backend) -- purely cosmetic here, but reusing
// the numbers rather than inventing a second set that could drift from the
// gameplay-facing thresholds.
const AVATAR_TIER_LEVEL_THRESHOLDS = { MID: 8, TOP: 15 } as const

const ICE = '#D7EFFF'
const PERSIMMON = '#FF5C34'
// Matches the `dark-bg` Tailwind token (tailwind.config.js) -- the gradient
// ring's border needs an actual color here, not just "transparent",
// because it's built from two stacked background-image layers (see below),
// not a plain `border-color`.
const DARK_BG = '#111827'

export type AvatarTier = 1 | 2 | 3

export interface AvatarTierStyle {
  tier: AvatarTier
  style: CSSProperties
}

// Two-layer background-clip trick for a gradient border: the first (solid)
// layer fills the interior up to the padding box, so it reads as the same
// dark disc as the solid-ring tiers behind the photo/fallback icon; the
// second (gradient) layer paints only the ring between padding-box and
// border-box. Shared by the automatic level-15+ tier and the level-10+
// "Микс" ring choice (2026-08-30 gamification pass) -- same visual, two
// different reasons to show it.
const GRADIENT_RING_STYLE: CSSProperties = {
  border: '3px solid transparent',
  backgroundImage: `linear-gradient(${DARK_BG}, ${DARK_BG}), linear-gradient(135deg, ${ICE}, ${PERSIMMON})`,
  backgroundOrigin: 'border-box',
  backgroundClip: 'padding-box, border-box',
  boxShadow: `0 0 16px rgba(215,239,255,0.45), 0 0 16px rgba(255,92,52,0.3)`,
}

// Premium gold ring (2026-10-04) -- same two-layer gradient trick as above.
const GOLD_RING_STYLE: CSSProperties = {
  border: '3px solid transparent',
  backgroundImage: `linear-gradient(${DARK_BG}, ${DARK_BG}), linear-gradient(135deg, #FBE7B0, #B8862F 50%, #F6D98A)`,
  backgroundOrigin: 'border-box',
  backgroundClip: 'padding-box, border-box',
  boxShadow: '0 0 16px rgba(214,170,80,0.45)',
}

function solidRingStyle(color: string): CSSProperties {
  return { border: `3px solid ${color}`, boxShadow: `0 0 12px ${color}66` }
}

// Plain function, not a `use*` hook -- it's a pure derivation from
// `level`/`ringAccent` with no state/effects of its own, so naming it like
// a hook would only invite react-hooks lint rules that don't apply here.
//
// `ringAccent` only matters between levels 10-14: below 10 the choice isn't
// unlocked yet (see hasAvatarRingChoice), and at 15+ the automatic gradient
// tier always wins regardless of any earlier choice -- it's the level-15
// reward, not something a level-10 pick should let you keep instead of
// grow into.
export function getAvatarTierStyle(
  level: number,
  ringAccent?: AvatarRingAccent | null,
): AvatarTierStyle {
  const tier = level >= AVATAR_TIER_LEVEL_THRESHOLDS.TOP ? 3 : 2
  // Premium gold: any level (the server only keeps it while premium lasts).
  if (ringAccent === 'gold') {
    return { tier, style: GOLD_RING_STYLE }
  }
  // The player's own pick wins at every level it's unlocked at -- at 15+ it
  // used to be overridden by the gradient, so the setting did nothing there.
  if (hasAvatarRingChoice(level) && ringAccent != null) {
    if (ringAccent === 'mix') {
      return { tier, style: GRADIENT_RING_STYLE }
    }
    return { tier, style: solidRingStyle(ringAccent === 'persimmon' ? PERSIMMON : ICE) }
  }
  if (level >= AVATAR_TIER_LEVEL_THRESHOLDS.TOP) {
    return { tier: 3, style: GRADIENT_RING_STYLE }
  }
  if (level >= AVATAR_TIER_LEVEL_THRESHOLDS.MID) {
    return { tier: 2, style: solidRingStyle(ICE) }
  }
  return {
    tier: 1,
    style: {
      border: `2px solid ${ICE}`,
    },
  }
}
