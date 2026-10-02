import type { AvatarTier } from '../utils/avatarTier'

// PlayerCard's colours per level tier (the same tiers as the avatar ring,
// utils/avatarTier), shared with the shared-card canvas in utils/cardImage.

export interface TierLook {
  frame: string
  glow: string
  stripe: string
  accent: string
  // Spotlight colour washed over the top of the backdrop.
  tint: string
  // The frame and stripe gradients again, as stops for the shared-card
  // canvas (utils/cardImage) -- canvas can't take CSS gradient strings.
  frameStops: [number, string][]
  stripeStops: [string, string]
}

const TIER_LOOKS: Record<AvatarTier, TierLook> = {
  1: {
    frame: 'linear-gradient(150deg, #A9B4C6, #4A5568 55%, #8B96AB)',
    glow: '0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #8B96AB, #C9D2DE)',
    accent: '#F5F7FA',
    tint: 'rgba(169,180,198,0.22)',
    frameStops: [[0, '#A9B4C6'], [0.55, '#4A5568'], [1, '#8B96AB']],
    stripeStops: ['#8B96AB', '#C9D2DE'],
  },
  2: {
    frame: 'linear-gradient(150deg, #FFFFFF, #D7EFFF 30%, #6F92B5 62%, #D7EFFF)',
    glow: '0 0 28px rgba(215,239,255,0.28), 0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #7FA6C9, #D7EFFF)',
    accent: '#D7EFFF',
    tint: 'rgba(215,239,255,0.28)',
    frameStops: [[0, '#FFFFFF'], [0.3, '#D7EFFF'], [0.62, '#6F92B5'], [1, '#D7EFFF']],
    stripeStops: ['#7FA6C9', '#D7EFFF'],
  },
  3: {
    frame: 'linear-gradient(150deg, #D7EFFF, #FF5C34 55%, #FFB199)',
    glow: '0 0 30px rgba(255,92,52,0.35), 0 0 18px rgba(215,239,255,0.25), 0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #D7EFFF, #FF5C34)',
    accent: '#FFD2C4',
    tint: 'rgba(255,92,52,0.30)',
    frameStops: [[0, '#D7EFFF'], [0.55, '#FF5C34'], [1, '#FFB199']],
    stripeStops: ['#D7EFFF', '#FF5C34'],
  },
}

export function getPlayerCardLook(tier: AvatarTier): TierLook {
  return TIER_LOOKS[tier]
}
