import type { CSSProperties } from 'react'
import { cardStyleFor, getPlayerCardLook } from '../playerCardLook'
import { teamCardStyle } from './TeamCard'
import type { LineupSlot, TeamEventLineupGroupRead, TeamEventLineupPlayerRead } from '../../types/teamEvent'
import { LINEUP_SLOT_LABELS } from '../../types/teamEvent'
import { POSITION_LABELS } from '../../types/user'

// "Состав по звеньям" pieces (2026-10-09): a player's mini-card, the line
// card (shareable, same data-card markup as the player card so
// utils/cardImage can paint it).

const TEXT_SHADOW: CSSProperties = { textShadow: '0 2px 12px rgba(0,0,0,0.75)' }

const SIX_STATS: { key: string; label: string }[] = [
  { key: 'strength', label: 'СИЛ' },
  { key: 'endurance', label: 'ВЫН' },
  { key: 'agility', label: 'ЛОВ' },
  { key: 'on_ice_skating', label: 'ЛЁД' },
  { key: 'intellect', label: 'ИНТ' },
  { key: 'puck_handling', label: 'ШАЙ' },
]

export function slotLabel(player: TeamEventLineupPlayerRead): string {
  if (player.slot != null) {
    return LINEUP_SLOT_LABELS[player.slot as LineupSlot]
  }
  return player.position !== null ? POSITION_LABELS[player.position].slice(0, 3).toUpperCase() : '—'
}

function surname(player: TeamEventLineupPlayerRead): string {
  return player.last_name || player.first_name
}

export function MiniPlayerCard({ player, isMe }: { player: TeamEventLineupPlayerRead; isMe: boolean }) {
  const look = getPlayerCardLook(cardStyleFor(player.level ?? 1, null))
  return (
    <div className="relative rounded-xl p-[2px]" style={{ background: look.frame }}>
      <div className="flex h-[118px] flex-col items-center justify-between rounded-[10px] bg-[#0E1524] px-1.5 py-2">
        <div className="flex w-full items-start justify-between">
          <span className="font-display text-xl font-bold leading-none" style={{ color: look.accent }}>
            {player.rating ?? '—'}
          </span>
          <span className="font-display text-[11px] font-semibold tracking-wider text-[#C9D2DE]">{slotLabel(player)}</span>
        </div>
        <span className="font-display text-2xl font-bold leading-none text-[#F5F7FA]">
          {player.jersey_number != null ? `#${player.jersey_number}` : ''}
        </span>
        <span className="w-full truncate text-center font-display text-[12px] font-semibold uppercase tracking-wide text-[#F5F7FA]">
          {surname(player)}
        </span>
      </div>
      {isMe && (
        <span className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-full bg-accent-persimmon px-1.5 py-px font-display text-[10px] font-bold text-dark-bg">
          ТЫ
        </span>
      )}
    </div>
  )
}

function averageStats(players: TeamEventLineupPlayerRead[]): { label: string; value: number | null }[] {
  return SIX_STATS.map(({ key, label }) => {
    const values = players.map((p) => p.stats?.[key]).filter((v): v is number => v !== undefined)
    return { label, value: values.length > 0 ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : null }
  })
}

// The line card: the line's rating, the game, its three players large, the
// average of their six stats and the defense pair "behind" it.
export function LineCard({
  line,
  pair,
  gameLine,
}: {
  line: TeamEventLineupGroupRead
  pair: TeamEventLineupGroupRead | null
  gameLine: string
}) {
  const look = getPlayerCardLook(teamCardStyle(line.rating ?? null))
  const accent: CSSProperties = { color: look.accent, ...TEXT_SHADOW }
  const stats = averageStats(line.players)

  return (
    <div data-card="frame" className="relative overflow-hidden rounded-2xl p-[3px]" style={{ background: look.frame, boxShadow: look.glow }}>
      <div data-card="inner" className="relative h-[470px] overflow-hidden rounded-[13px] bg-[#0E1524]">
        <img
          data-card="arena"
          src="/images/arena-bg.webp"
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-[70%_40%] opacity-90"
        />
        <div
          className="absolute inset-0"
          style={{
            background: `radial-gradient(ellipse at 75% -5%, ${look.tint}, transparent 60%), linear-gradient(180deg, rgba(14,21,36,0.10) 0%, rgba(14,21,36,0.55) 40%, #0E1524 75%)`,
          }}
        />

        <div className="absolute left-5 top-5 z-[2] flex flex-col items-start gap-1">
          <span data-card-text className="font-display text-[56px] font-bold leading-[0.9]" style={accent}>
            {line.rating ?? '—'}
          </span>
          <span data-card-text className="font-display text-[11px] tracking-[1.2px] text-text-secondary">РЕЙТИНГ ЗВЕНА</span>
        </div>
        <div className="absolute right-5 top-6 z-[2] flex max-w-[55%] flex-col items-end gap-0.5 text-right">
          <span data-card-text className="truncate font-display text-[13px] font-semibold tracking-wider text-text-primary">
            {gameLine}
          </span>
        </div>

        <div className="absolute inset-x-4 top-[100px] z-[2] flex items-center gap-2.5" style={TEXT_SHADOW}>
          <span data-card="stripe-line" className="h-px flex-1" style={{ background: look.stripe }} />
          <span data-card-text className="max-w-[240px] truncate font-display text-[26px] font-bold uppercase tracking-[2px] text-text-primary">
            {line.name ?? 'Звено'}
          </span>
          <span data-card="stripe-line" className="h-px flex-1" style={{ background: look.stripe }} />
        </div>

        <div className="absolute inset-x-4 top-[150px] z-[2] grid grid-cols-3 gap-2">
          {line.players.slice(0, 3).map((player) => (
            <div
              key={player.user_id}
              data-card-box
              className="flex flex-col items-center gap-1 rounded-[12px] border border-white/10 bg-white/5 px-1 py-2.5"
            >
              <span data-card-text className="font-display text-[11px] font-semibold tracking-wider text-[#C9D2DE]">
                {slotLabel(player)}
              </span>
              <span data-card-text className="font-display text-[30px] font-bold leading-none text-text-primary">
                {player.jersey_number != null ? `#${player.jersey_number}` : '—'}
              </span>
              <span data-card-text className="max-w-full truncate font-display text-[13px] font-semibold uppercase tracking-wide text-text-primary">
                {surname(player)}
              </span>
              <span data-card-text className="font-display text-lg font-bold" style={{ color: look.accent }}>
                {player.rating ?? '—'}
              </span>
            </div>
          ))}
        </div>

        <div className="absolute inset-x-[22px] top-[300px] z-[2] grid grid-cols-2 gap-y-0.5">
          {stats.map((stat, index) => (
            <div
              key={stat.label}
              data-card={index % 2 === 0 ? 'stat-left' : undefined}
              className={`flex min-h-[28px] items-baseline gap-2.5 ${index % 2 === 0 ? 'border-r border-white/15 pr-3.5' : 'pl-[18px]'}`}
            >
              <span data-card-text="right" className="w-[30px] text-right font-display text-xl font-bold" style={accent}>
                {stat.value ?? '—'}
              </span>
              <span data-card-text className="font-display text-[14px] tracking-wider text-[#C9D2DE]">{stat.label}</span>
            </div>
          ))}
        </div>

        {pair !== null && pair.players.length > 0 && (
          <div className="absolute inset-x-[22px] bottom-4 z-[2] flex items-center gap-2 border-t border-white/10 pt-2.5">
            <span data-card-text className="font-display text-[11px] tracking-[1.2px] text-text-secondary">ЗА СПИНОЙ</span>
            <span data-card-text className="min-w-0 flex-1 truncate text-right font-display text-[13px] font-semibold uppercase tracking-wide text-text-primary">
              {pair.players.map((p) => `${slotLabel(p)} ${surname(p)}`).join(' · ')}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
