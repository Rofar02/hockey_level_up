import type { CSSProperties } from 'react'
import { API_BASE_URL } from '../../api/client'
import type { TeamCardRead } from '../../types/team'
import { getPlayerCardLook } from '../playerCardLook'
import type { CardStyle } from '../playerCardLook'

// The team card (2026-10-09), in the style of the player card: the team's
// rating and place on the left, the emblem on the right, the name on a
// nameplate, the season in two columns and three leaders at the bottom.
// Same data-card markup as PlayerCard, so utils/cardImage paints it as a
// PNG for sharing.

const TEXT_SHADOW: CSSProperties = { textShadow: '0 2px 12px rgba(0,0,0,0.75)' }

// The frame grows with the team's average "ОБЩИЙ", like a player's card
// grows with level: steel, ice, fire, then the ice-and-fire mix.
export function teamCardStyle(rating: number | null): CardStyle {
  if (rating === null || rating < 25) {
    return 'steel'
  }
  if (rating < 45) {
    return 'ice'
  }
  if (rating < 65) {
    return 'fire'
  }
  return 'mix'
}

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length >= 2) {
    return (words[0][0] + words[1][0]).toUpperCase()
  }
  return name.trim().slice(0, 2).toUpperCase()
}

// "Новокузнецк · Ночная лига · Лига Надежды" -- "хоккейная" dropped so the
// line fits the card on a phone.
export function teamLocationLine(card: { city: string | null; league_name: string | null; division_name: string | null }) {
  const league = card.league_name?.replace(/ хоккейная/i, '') ?? null
  return [card.city, league, card.division_name].filter((part): part is string => !!part).join(' · ')
}

export function TeamCard({ card }: { card: TeamCardRead }) {
  const look = getPlayerCardLook(teamCardStyle(card.rating))
  const accent: CSSProperties = { color: look.accent, ...TEXT_SHADOW }
  const resultLine = card.draws > 0 ? `${card.wins}-${card.draws}-${card.losses}` : `${card.wins}-${card.losses}`
  const stats: { label: string; value: string }[] = [
    { label: 'ИГРЫ', value: String(card.games) },
    { label: card.draws > 0 ? 'В-Н-П' : 'В-П', value: card.games > 0 ? resultLine : '—' },
    { label: 'ЗАБИТО', value: String(card.goals_for) },
    { label: 'ПРОПУЩЕНО', value: String(card.goals_against) },
    { label: 'НА ТРЕНИР.', value: card.attendance_percent !== null ? `${card.attendance_percent}%` : '—' },
    { label: 'СЕРИЯ', value: card.streak ?? '—' },
  ]
  const location = teamLocationLine(card)

  return (
    <div data-card="frame" className="relative overflow-hidden rounded-2xl p-[3px]" style={{ background: look.frame, boxShadow: look.glow }}>
      <div data-card="inner" className="relative h-[520px] overflow-hidden rounded-[13px] bg-[#0E1524]">
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

        <div className="absolute left-5 top-5 z-[2] flex flex-col items-start gap-1">
          <span data-card-text className="font-display text-[62px] font-bold leading-[0.9]" style={accent}>
            {card.rating ?? '—'}
          </span>
          <span data-card-text className="font-display text-[11px] tracking-[1.2px] text-text-secondary">ОБЩИЙ</span>
          {card.league_place !== null && (
            <>
              <span data-card-text className="mt-1 font-display text-[17px] font-semibold tracking-wider text-text-primary">
                #{card.league_place} В ЛИГЕ
              </span>
              <span data-card-text className="text-[10px] tracking-wider text-text-secondary">
                из {card.league_team_count} в городе
              </span>
            </>
          )}
          <span data-card="rule" className="my-1 h-px w-[34px] bg-white/25" />
          <span data-card-text className="font-display text-sm font-medium tracking-wider text-text-secondary">
            СЕЗОН {card.season_label}
          </span>
        </div>

        <div className="absolute right-6 top-6 z-[2]">
          {card.logo_url !== null ? (
            <span data-card="emblem" className="flex h-[150px] w-[150px] items-center justify-center overflow-hidden rounded-full border border-accent-ice/35 bg-[#22304A]">
              <img data-card="emblem-logo" src={`${API_BASE_URL}${card.logo_url}`} alt="" className="h-full w-full object-cover" />
            </span>
          ) : (
            <span
              data-card-box
              className="flex h-[150px] w-[150px] items-center justify-center rounded-full border-2 bg-[rgba(23,31,48,0.85)]"
              style={{ borderColor: look.accent }}
            >
              <span data-card-text className="font-display text-5xl font-bold" style={accent}>
                {initials(card.name)}
              </span>
            </span>
          )}
        </div>

        <div className="absolute inset-x-4 top-[214px] z-[2] flex flex-col items-center gap-0.5" style={TEXT_SHADOW}>
          {location !== '' && (
            <span data-card-text className="max-w-full truncate text-[10px] uppercase tracking-[0.8px] text-text-secondary">
              {location}
            </span>
          )}
          <div className="flex w-full items-center gap-2.5">
            <span data-card="stripe-line" className="h-px flex-1" style={{ background: look.stripe }} />
            <span data-card-text className="max-w-[260px] truncate font-display text-[32px] font-bold uppercase tracking-[2px] text-text-primary">
              {card.name}
            </span>
            <span data-card="stripe-line" className="h-px flex-1" style={{ background: look.stripe }} />
          </div>
        </div>

        <div className="absolute inset-x-[22px] top-[290px] z-[2] grid grid-cols-2 gap-y-0.5">
          {stats.map((stat, index) => (
            <div
              key={stat.label}
              data-card={index % 2 === 0 ? 'stat-left' : undefined}
              className={`flex min-h-[34px] items-baseline justify-between gap-2 ${index % 2 === 0 ? 'border-r border-white/15 pr-3.5' : 'pl-[18px]'}`}
            >
              <span data-card-text className="font-display text-[13px] tracking-wider text-[#C9D2DE]">{stat.label}</span>
              <span data-card-text="right" className="font-display text-xl font-bold" style={accent}>
                {stat.value}
              </span>
            </div>
          ))}
        </div>

        <div className="absolute inset-x-[22px] bottom-4 z-[2] flex flex-col gap-2">
          <span data-card-text className="font-display text-[11px] tracking-[1.4px] text-text-secondary">ЛИДЕРЫ СЕЗОНА</span>
          {card.leaders.length > 0 ? (
            <div className="grid grid-cols-3 gap-2">
              {card.leaders.map((leader) => (
                <div
                  key={leader.title}
                  data-card-box
                  className="flex min-w-0 flex-col gap-0.5 rounded-[10px] border border-white/10 bg-white/5 px-2.5 py-2"
                >
                  <span data-card-text className="text-[10px] uppercase tracking-wider text-text-secondary">{leader.title}</span>
                  <span data-card-text className="truncate font-display text-[15px] font-semibold text-text-primary">{leader.name}</span>
                  <span data-card-text className="font-display text-[13px]" style={{ color: look.accent }}>{leader.value}</span>
                </div>
              ))}
            </div>
          ) : (
            <span className="text-xs text-text-secondary">Появятся после первых отчётов об играх.</span>
          )}
        </div>
      </div>
    </div>
  )
}
