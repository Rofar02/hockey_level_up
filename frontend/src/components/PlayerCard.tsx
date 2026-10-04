import type { CSSProperties, Ref } from 'react'
import { COLLAR_PATH, JERSEY_PATH } from './ui/JerseyBadge'
import { JERSEY_NUMBER_COLORS, getPlayerCardLook } from './playerCardLook'
import type { CardStyle } from './playerCardLook'
import { hasCardShine } from '../utils/levelUnlocks'
import { xpToNextLevel } from '../utils/xpProgress'
import type { TargetStat } from '../types/exercise'
import type { JerseyColor, Position } from '../types/user'

// The profile's hero, styled after a hockey video game's player card: big
// overall rating and position on the left, the photo on the right, the
// surname on a nameplate, stats in two columns. The frame follows the same
// level tiers as the avatar ring (utils/avatarTier), so the card visibly
// "upgrades" at levels 8 and 15.

const POSITION_SHORT: Record<Position, string> = {
  forward: 'НАП',
  defense: 'ЗАЩ',
  goalie: 'ВРТ',
}

// The photo spans the card and dissolves downwards into the nameplate and
// stats -- the player standing in the arena rather than a picture in a
// frame. Only the bottom fades: fading the top too ate heads on tall photos.
const PHOTO_MASK = 'linear-gradient(to bottom, #000 52%, transparent 94%)'

// Darkens the card's left edge under the rating column so the number reads
// over any photo.
const RATING_SCRIM = 'linear-gradient(to right, rgba(14,21,36,0.78) 0%, rgba(14,21,36,0.35) 32%, transparent 55%)'
const PHOTO_MASK_STYLE: CSSProperties = { maskImage: PHOTO_MASK, WebkitMaskImage: PHOTO_MASK }

// Keeps the rating and the nameplate legible over a bright photo or arena.
const TEXT_SHADOW: CSSProperties = { textShadow: '0 2px 12px rgba(0,0,0,0.75)' }

export interface PlayerCardStat {
  type: TargetStat
  label: string
  // null when the player has no value for it yet -- the slot stays so the
  // two columns keep their pairing.
  value: number | null
}

interface PlayerCardProps {
  // From cardStyleFor -- the same level/ring-accent rules as the avatar ring.
  cardStyle: CardStyle
  // The jersey number's colour (level 15+); null keeps the card's accent.
  jerseyColor: JerseyColor | null
  rating: number | null
  position: Position | null
  jerseyNumber: number | null
  surname: string
  subtitle: string
  level: number
  xp: number
  avatarUrl: string | null
  teamLogoUrl: string | null
  stats: PlayerCardStat[]
  isUploadingAvatar?: boolean
  statGridRef?: Ref<HTMLDivElement>
  // Overrides the level rule for the sheen (the premium preview always has it).
  shine?: boolean
  // All optional: without them the card is read-only (someone else's
  // profile) -- no camera button, nothing tappable.
  onAvatarClick?: () => void
  onChangePhoto?: () => void
  onLevelClick?: () => void
  onStatClick?: (stat: TargetStat) => void
}

export function PlayerCard({
  cardStyle,
  jerseyColor,
  rating,
  position,
  jerseyNumber,
  surname,
  subtitle,
  level,
  xp,
  avatarUrl,
  teamLogoUrl,
  stats,
  isUploadingAvatar = false,
  statGridRef,
  shine,
  onAvatarClick,
  onChangePhoto,
  onLevelClick,
  onStatClick,
}: PlayerCardProps) {
  const look = getPlayerCardLook(cardStyle)
  const accent: CSSProperties = { color: look.accent, ...TEXT_SHADOW }
  const numberColor = jerseyColor !== null ? JERSEY_NUMBER_COLORS[jerseyColor] : look.accent
  const xpNext = xpToNextLevel(level)
  const xpPercent = xpNext > 0 ? Math.max(0, Math.min(100, (xp / xpNext) * 100)) : 0

  const photo = (
    <>
      {avatarUrl !== null ? (
        <img
          src={avatarUrl}
          alt="Аватар"
          data-card="photo"
          className="h-full w-full object-cover object-[50%_15%]"
          style={PHOTO_MASK_STYLE}
        />
      ) : (
        // No photo yet: the player's own jersey stands in for them.
        <svg data-card="jersey" viewBox="0 0 130 110" className="mb-[92px] ml-auto mr-6 w-[196px] opacity-90" aria-hidden="true" style={{ color: numberColor }}>
          <path d={JERSEY_PATH} fill="rgba(14,21,36,0.55)" stroke="currentColor" strokeWidth={1.5} strokeLinejoin="round" />
          <path d={COLLAR_PATH} fill="none" stroke="currentColor" strokeWidth={1.5} />
          <text x={65} y={34} textAnchor="middle" fontSize={10} letterSpacing={0.5} fill="currentColor" className="font-display font-semibold uppercase">
            {surname}
          </text>
          <text x={65} y={70} textAnchor="middle" fontSize={30} fill="currentColor" className="font-display font-bold">
            {jerseyNumber ?? ''}
          </text>
        </svg>
      )}
      {isUploadingAvatar && (
        <span className="absolute inset-0 flex items-center justify-center bg-black/60">
          <i className="ti ti-loader-2 animate-spin text-3xl text-text-primary" aria-hidden="true" />
        </span>
      )}
    </>
  )

  return (
    <div
      data-card="frame"
      className="relative overflow-hidden rounded-2xl p-[3px]"
      style={{ background: look.frame, boxShadow: look.glow }}
    >
      <div data-card="inner" className="relative h-[478px] overflow-hidden rounded-[13px] bg-[#0E1524]">
        <img
          data-card="arena"
          src="/images/arena-bg.webp"
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-[70%_40%] opacity-90"
        />
        <div
          className="absolute inset-0"
          style={{
            background: `radial-gradient(ellipse at 75% -5%, ${look.tint}, transparent 60%), linear-gradient(180deg, rgba(14,21,36,0.10) 0%, rgba(14,21,36,0.45) 48%, #0E1524 80%)`,
          }}
        />
        {/* Top stripe under the frame. Not on the gold card (2026-10-04): there it
            doubled the frame into a thick two-tone line along the top edge. */}
        {cardStyle !== 'gold' && (
          <div data-card="stripe-line" className="absolute inset-x-0 top-0 z-[2] h-1" style={{ background: look.stripe }} />
        )}

        {/* Premium gold card (2026-10-04): a "PREMIUM" plate in the free top-right corner.
            The shared PNG draws the plate from [data-card="premium-badge"] and its text. */}
        {cardStyle === 'gold' && (
          <span
            data-card="premium-badge"
            className="absolute right-4 top-5 z-[3] rounded-full border border-[#FBE7B0]/60 bg-[#FBE7B0]/15 px-2.5 py-1"
          >
            <span data-card-text className="block font-display text-[11px] font-semibold tracking-[1.5px] text-[#FBE7B0]">
              PREMIUM
            </span>
          </span>
        )}

        <div className="absolute left-5 top-5 z-[2] flex flex-col items-start gap-1">
          <span data-card-text className="font-display text-[62px] font-bold leading-[0.9]" style={accent}>
            {rating ?? '—'}
          </span>
          <span data-card-text className="font-display text-[11px] tracking-[1.2px] text-text-secondary">ОБЩИЙ</span>
          {position !== null && (
            <span data-card-text className="mt-1 font-display text-[17px] font-semibold tracking-wider text-text-primary">
              {POSITION_SHORT[position]}
            </span>
          )}
          {jerseyNumber !== null && (
            <>
              <span data-card="rule" className="my-1 h-px w-[34px] bg-white/25" />
              <span data-card-text className="font-display text-xl font-semibold" style={{ ...TEXT_SHADOW, color: numberColor }}>
                #{jerseyNumber}
              </span>
            </>
          )}
          <span data-card="emblem" className="mt-1 flex h-[34px] w-[34px] items-center justify-center overflow-hidden rounded-full border border-accent-ice/35 bg-[#22304A] text-accent-ice">
            {teamLogoUrl !== null ? (
              <img data-card="emblem-logo" src={teamLogoUrl} alt="" className="h-full w-full object-cover" />
            ) : (
              // Inline, not the Tabler icon font: the shared-card export would
              // otherwise have to embed the whole 500 KB font for this one glyph.
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 3a12 12 0 0 0 8.5 3a12 12 0 0 1 -8.5 15a12 12 0 0 1 -8.5 -15a12 12 0 0 0 8.5 -3" />
              </svg>
            )}
          </span>
        </div>

        {onAvatarClick !== undefined ? (
          <button
            type="button"
            onClick={onAvatarClick}
            disabled={isUploadingAvatar}
            aria-label={avatarUrl !== null ? 'Просмотреть фото профиля' : 'Загрузить фото профиля'}
            className="absolute inset-x-0 top-0 z-[1] flex h-[330px] items-end disabled:cursor-wait"
          >
            {photo}
          </button>
        ) : (
          <div className="absolute inset-x-0 top-0 z-[1] flex h-[330px] items-end">{photo}</div>
        )}
        {avatarUrl !== null && (
          <div data-card="scrim" className="pointer-events-none absolute inset-y-0 left-0 z-[1] w-full" style={{ background: RATING_SCRIM }} />
        )}
        {onChangePhoto !== undefined && (
          <button
            type="button"
            onClick={onChangePhoto}
            data-share-hide
            disabled={isUploadingAvatar}
            aria-label="Изменить фото профиля"
            className="absolute right-4 top-[208px] z-[3] flex h-9 w-9 items-center justify-center rounded-full border border-white/25 bg-white/10 text-white/85 backdrop-blur-sm transition-colors hover:bg-white/20 hover:text-white"
          >
            <i className="ti ti-camera text-base" aria-hidden="true" />
          </button>
        )}

        <div className="absolute inset-x-4 top-[254px] z-[2] flex flex-col items-center gap-0.5" style={TEXT_SHADOW}>
          <span data-card-text className="text-[11px] uppercase tracking-[2px] text-text-secondary">{subtitle}</span>
          <div className="flex w-full items-center gap-2.5">
            <span data-card="stripe-line" className="h-px flex-1" style={{ background: look.stripe }} />
            <span data-card-text className="max-w-[240px] truncate font-display text-[30px] font-bold uppercase tracking-[2px] text-text-primary">
              {surname}
            </span>
            <span data-card="stripe-line" className="h-px flex-1" style={{ background: look.stripe }} />
          </div>
        </div>

        <div ref={statGridRef} className="absolute inset-x-[22px] top-[320px] z-[2] grid grid-cols-2 gap-y-0.5">
          {stats.map((stat, index) => (
            <button
              key={stat.type}
              type="button"
              onClick={() => onStatClick?.(stat.type)}
              disabled={onStatClick === undefined}
              data-card={index % 2 === 0 ? 'stat-left' : undefined}
              className={`flex min-h-[34px] items-baseline gap-2.5 rounded transition-colors hover:bg-white/5 ${
                index % 2 === 0 ? 'border-r border-white/15 pr-3.5' : 'pl-[18px]'
              }`}
            >
              <span data-card-text="right" className="w-[34px] text-right font-display text-2xl font-bold" style={accent}>
                {stat.value !== null ? Math.round(stat.value) : '—'}
              </span>
              <span data-card-text className="font-display text-[15px] tracking-wider text-[#C9D2DE]">{stat.label}</span>
            </button>
          ))}
        </div>

        {/* Level and XP as the card's footer strip -- one line under the
            stats instead of a pill floating between them. */}
        <button
          type="button"
          onClick={onLevelClick}
          disabled={onLevelClick === undefined}
          aria-label={`Уровень ${level}: что открывается`}
          data-card="xp-row"
          className="absolute inset-x-[22px] bottom-4 z-[2] flex items-center gap-3 border-t border-white/10 pt-3"
        >
          <span data-card-text className="font-display text-sm font-semibold tracking-wider" style={accent}>
            УР. {level}
          </span>
          <span data-card="xp-track" className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
            <span data-card="xp-fill" className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${xpPercent}%`, background: look.stripe }} />
          </span>
          <span data-card-text className="font-mono text-[11px] text-text-secondary">
            {xp} / {xpNext}
          </span>
        </button>
      </div>
      {/* From LEVEL_CARD_SHINE: a sheen sweeps across the whole card now and
          then, like a rare card in the games. Over everything, never tappable;
          the shared picture (utils/cardImage) is a still and leaves it out. */}
      {(shine ?? (hasCardShine(level) || cardStyle === 'gold')) && (
        <span className="card-shine pointer-events-none absolute inset-0 z-[5] rounded-2xl" aria-hidden="true" />
      )}
    </div>
  )
}
