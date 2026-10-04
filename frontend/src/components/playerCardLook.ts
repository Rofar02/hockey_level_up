import type { AvatarRingAccent, JerseyColor } from '../types/user'
import { hasAvatarRingChoice } from '../utils/levelUnlocks'

// PlayerCard's colours, shared with the shared-card canvas in
// utils/cardImage. The card follows the same rules as the avatar ring
// (utils/avatarTier): steel until level 8, ice from 8, the player's own ring
// accent from 10 (Лёд / Огонь / Микс) at any level, the ice-to-fire mix from
// 15 when nothing's picked. The jersey number takes the colour picked from
// level 15 (JerseyColor). From LEVEL_CARD_SHINE the frame also glints.

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

// 'gold' is the premium look -- not a level tier: picked as the 'gold' ring
// accent (premium only), and the premium page previews it.
export type CardStyle = 'steel' | 'ice' | 'fire' | 'mix' | 'gold'

const CARD_LOOKS: Record<CardStyle, TierLook> = {
  steel: {
    frame: 'linear-gradient(150deg, #A9B4C6, #4A5568 55%, #8B96AB)',
    glow: '0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #8B96AB, #C9D2DE)',
    accent: '#F5F7FA',
    tint: 'rgba(169,180,198,0.22)',
    frameStops: [[0, '#A9B4C6'], [0.55, '#4A5568'], [1, '#8B96AB']],
    stripeStops: ['#8B96AB', '#C9D2DE'],
  },
  ice: {
    frame: 'linear-gradient(150deg, #FFFFFF, #D7EFFF 30%, #6F92B5 62%, #D7EFFF)',
    glow: '0 0 28px rgba(215,239,255,0.28), 0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #7FA6C9, #D7EFFF)',
    accent: '#D7EFFF',
    tint: 'rgba(215,239,255,0.28)',
    frameStops: [[0, '#FFFFFF'], [0.3, '#D7EFFF'], [0.62, '#6F92B5'], [1, '#D7EFFF']],
    stripeStops: ['#7FA6C9', '#D7EFFF'],
  },
  fire: {
    frame: 'linear-gradient(150deg, #FFD2C4, #FF5C34 45%, #7A2410 78%, #FF8A6B)',
    glow: '0 0 28px rgba(255,92,52,0.35), 0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #FF8A6B, #FF5C34)',
    accent: '#FFB199',
    tint: 'rgba(255,92,52,0.34)',
    frameStops: [[0, '#FFD2C4'], [0.45, '#FF5C34'], [0.78, '#7A2410'], [1, '#FF8A6B']],
    stripeStops: ['#FF8A6B', '#FF5C34'],
  },
  mix: {
    frame: 'linear-gradient(150deg, #D7EFFF, #FF5C34 55%, #FFB199)',
    glow: '0 0 30px rgba(255,92,52,0.35), 0 0 18px rgba(215,239,255,0.25), 0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #D7EFFF, #FF5C34)',
    accent: '#FFD2C4',
    tint: 'rgba(255,92,52,0.30)',
    frameStops: [[0, '#D7EFFF'], [0.55, '#FF5C34'], [1, '#FFB199']],
    stripeStops: ['#D7EFFF', '#FF5C34'],
  },
  gold: {
    frame: 'linear-gradient(150deg, #FBE7B0, #B8862F 45%, #F6D98A 70%, #9C6B1E)',
    glow: '0 0 30px rgba(214,170,80,0.32), 0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #B8862F, #FBE7B0)',
    accent: '#FBE7B0',
    tint: 'rgba(246,217,138,0.28)',
    frameStops: [[0, '#FBE7B0'], [0.45, '#B8862F'], [0.7, '#F6D98A'], [1, '#9C6B1E']],
    stripeStops: ['#B8862F', '#FBE7B0'],
  },
}

// Mirrors getAvatarTierStyle, so the card and the avatar ring always agree.
export function cardStyleFor(level: number, ringAccent: AvatarRingAccent | null | undefined): CardStyle {
  // Premium gold (2026-10-04): any level -- the server only stores it for premium players.
  if (ringAccent === 'gold') {
    return 'gold'
  }
  if (hasAvatarRingChoice(level) && ringAccent != null) {
    return ringAccent === 'persimmon' ? 'fire' : ringAccent
  }
  if (level >= 15) {
    return 'mix'
  }
  return level >= 8 ? 'ice' : 'steel'
}

export function getPlayerCardLook(style: CardStyle): TierLook {
  return CARD_LOOKS[style]
}

// The jersey number's colour choice (level 15+). Fire is a touch lighter than
// the brand persimmon so a number still reads on the dark card.
export const JERSEY_NUMBER_COLORS: Record<JerseyColor, string> = {
  white: '#F5F7FA',
  ice: '#D7EFFF',
  persimmon: '#FF7A54',
  gold: '#FFC94A',
}
