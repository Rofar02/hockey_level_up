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
  // Direction of the frame gradient, shared by the CSS frame and the canvas
  // (degrees, CSS convention); 150 when not set.
  frameAngle?: number
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
  // 2026-10-04 redesign (owner picked from a preview): "Пламя" -- amber to
  // deep red instead of a flat persimmon; "Лёд и пламя" -- ice on the left,
  // fire on the right instead of a washed-out pink-to-orange.
  fire: {
    frame: 'linear-gradient(150deg, #FFC56B, #FF8A3D 30%, #FF3D1F 60%, #8C1D0B)',
    glow: '0 0 26px rgba(255,92,52,0.5), 0 0 40px rgba(255,61,31,0.2), 0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #FF8A3D, #FF3D1F)',
    accent: '#FFC9A8',
    tint: 'rgba(255,92,52,0.34)',
    frameStops: [[0, '#FFC56B'], [0.3, '#FF8A3D'], [0.6, '#FF3D1F'], [1, '#8C1D0B']],
    stripeStops: ['#FF8A3D', '#FF3D1F'],
  },
  mix: {
    frame: 'linear-gradient(90deg, #7FC4FF, #D7EFFF 40%, #FF8A3D 60%, #FF5C34)',
    glow: '-10px 0 26px rgba(127,196,255,0.35), 10px 0 26px rgba(255,92,52,0.35), 0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #7FC4FF, #FF5C34)',
    accent: '#FFD2C4',
    tint: 'rgba(255,92,52,0.26)',
    frameStops: [[0, '#7FC4FF'], [0.4, '#D7EFFF'], [0.6, '#FF8A3D'], [1, '#FF5C34']],
    stripeStops: ['#7FC4FF', '#FF5C34'],
    frameAngle: 90,
  },
  // 2026-10-04: champagne gold -- the first palette's dark end (#B8862F ->
  // #9C6B1E) and amber glow read as an orange outline on a phone screen.
  gold: {
    frame: 'linear-gradient(150deg, #FFF4D6, #E6C36A 40%, #FFF0C2 65%, #D4AE55)',
    glow: '0 0 28px rgba(246,224,160,0.3), 0 14px 30px -12px rgba(0,0,0,0.7)',
    stripe: 'linear-gradient(90deg, #D9B458, #FFF0C2)',
    accent: '#FBE7B0',
    tint: 'rgba(246,224,160,0.24)',
    frameStops: [[0, '#FFF4D6'], [0.4, '#E6C36A'], [0.65, '#FFF0C2'], [1, '#D4AE55']],
    stripeStops: ['#D9B458', '#FFF0C2'],
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
