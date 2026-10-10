import type { CSSProperties } from 'react'
import { useAuth } from '../hooks/useAuth'
import type { SeasonSummaryRead } from '../types/gameStats'
import { cardStyleFor, getPlayerCardLook } from './playerCardLook'

// «Мой сезон» (2026-10-09, release plan step 10): the season as a card in
// the player-card style, in the player's own card colour. Same data-card
// markup, so utils/cardImage paints it as a PNG.

const TEXT_SHADOW: CSSProperties = { textShadow: '0 2px 12px rgba(0,0,0,0.75)' }

const STAT_SHORT: Record<string, string> = {
  strength: 'СИЛ',
  endurance: 'ВЫН',
  agility: 'ЛОВ',
  on_ice_skating: 'ЛЁД',
  intellect: 'ИНТ',
  puck_handling: 'ШАЙ',
}
const STAT_ORDER = ['strength', 'endurance', 'agility', 'on_ice_skating', 'intellect', 'puck_handling']

export function seasonCardStyle(level: number, ringAccent: Parameters<typeof cardStyleFor>[1]) {
  return cardStyleFor(level, ringAccent)
}

export function SeasonSummaryCard({ summary, name }: { summary: SeasonSummaryRead; name: string }) {
  const { user } = useAuth()
  const look = getPlayerCardLook(seasonCardStyle(summary.level, user?.avatar_ring_accent))
  const accent: CSSProperties = { color: look.accent, ...TEXT_SHADOW }
  const stats = [...summary.stats].sort((a, b) => STAT_ORDER.indexOf(a.stat) - STAT_ORDER.indexOf(b.stat))
  const counters: [string, string][] = [
    ['ЛЬДОВ', String(summary.ice_days)],
    ['ИГР', String(summary.games)],
    ['ЗАЛ', String(summary.gym_sessions)],
    ['КОМАНДА', summary.team_attendance_percent !== null ? `${summary.team_attendance_percent}%` : '—'],
  ]
  const teamLine = summary.team
    ? [summary.team.name, summary.team.league_name?.replace(/ хоккейная/i, '')].filter(Boolean).join(' · ')
    : null

  return (
    <div data-card="frame" className="relative overflow-hidden rounded-2xl p-[3px]" style={{ background: look.frame, boxShadow: look.glow }}>
      <div data-card="inner" className="relative h-[540px] overflow-hidden rounded-[13px] bg-[#0E1524]">
        <img
          data-card="arena"
          src="/images/arena-bg.webp"
          alt=""
          className="absolute inset-0 h-full w-full object-cover object-[70%_40%] opacity-90"
        />
        <div
          className="absolute inset-0"
          style={{
            background: `radial-gradient(ellipse at 75% -5%, ${look.tint}, transparent 60%), linear-gradient(180deg, rgba(14,21,36,0.10) 0%, rgba(14,21,36,0.55) 40%, #0E1524 72%)`,
          }}
        />

        <div className="absolute left-5 top-5 z-[2] flex flex-col items-start gap-1">
          <span data-card-text className="font-display text-[13px] font-semibold tracking-[1.6px] text-text-secondary">
            МОЙ СЕЗОН {summary.season_label}
          </span>
          <span data-card-text className="font-display text-[56px] font-bold leading-[0.95]" style={accent}>
            {summary.overall_after ?? '—'}
          </span>
          <span data-card-text className="font-display text-[11px] tracking-[1.2px] text-text-secondary">
            ОБЩИЙ{summary.overall_before !== null ? `, БЫЛО ${summary.overall_before}` : ''}
          </span>
        </div>
        <div className="absolute right-5 top-6 z-[2] flex flex-col items-end gap-1 text-right">
          <span data-card-text className="font-display text-xl font-semibold text-text-primary">УР. {summary.level}</span>
          <span data-card-text className="font-display text-[11px] tracking-[1.2px] text-text-secondary">
            СЕРИЯ {summary.best_streak} ДН.
          </span>
        </div>

        <div className="absolute inset-x-4 top-[132px] z-[2] flex items-center gap-2.5" style={TEXT_SHADOW}>
          <span data-card="stripe-line" className="h-px flex-1" style={{ background: look.stripe }} />
          <span data-card-text className="max-w-[250px] truncate font-display text-[28px] font-bold uppercase tracking-[2px] text-text-primary">
            {name}
          </span>
          <span data-card="stripe-line" className="h-px flex-1" style={{ background: look.stripe }} />
        </div>
        {teamLine !== null && (
          <span data-card-text className="absolute inset-x-4 top-[176px] z-[2] truncate text-center text-[11px] uppercase tracking-[1.2px] text-text-secondary">
            {teamLine}
          </span>
        )}

        <div className="absolute inset-x-4 top-[206px] z-[2] grid grid-cols-4 gap-2">
          {counters.map(([label, value]) => (
            <div key={label} data-card-box className="flex flex-col items-center gap-0.5 rounded-[10px] border border-white/10 bg-white/5 py-2">
              <span data-card-text className="font-display text-2xl font-bold text-text-primary">{value}</span>
              <span data-card-text className="text-[9px] tracking-wider text-text-secondary">{label}</span>
            </div>
          ))}
        </div>

        <div className="absolute inset-x-[22px] top-[290px] z-[2] grid grid-cols-2 gap-y-0.5">
          {stats.map((stat, index) => (
            <div
              key={stat.stat}
              data-card={index % 2 === 0 ? 'stat-left' : undefined}
              className={`flex min-h-[32px] items-baseline gap-2 ${index % 2 === 0 ? 'border-r border-white/15 pr-3' : 'pl-4'}`}
            >
              <span data-card-text className="w-[34px] font-display text-[14px] tracking-wider text-[#C9D2DE]">
                {STAT_SHORT[stat.stat] ?? stat.stat}
              </span>
              <span data-card-text className="font-display text-[13px] text-text-secondary">{Math.round(stat.before)} →</span>
              <span data-card-text className="font-display text-xl font-bold" style={accent}>
                {Math.round(stat.after)}
              </span>
            </div>
          ))}
        </div>

        {summary.frequent_linemate !== null && (
          <div className="absolute inset-x-[22px] bottom-4 z-[2] flex items-center gap-2 border-t border-white/10 pt-2.5">
            <span data-card-text className="font-display text-[11px] tracking-[1.2px] text-text-secondary">ЧАЩЕ ВСЕГО В ЗВЕНЕ С</span>
            <span data-card-text className="min-w-0 flex-1 truncate text-right font-display text-[14px] font-semibold uppercase tracking-wide text-text-primary">
              {summary.frequent_linemate}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
