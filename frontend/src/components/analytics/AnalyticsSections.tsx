import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CARD_BORDER } from '../ui/cardStyle'
import { FormError } from '../ui/FormError'
import { StatIcon } from '../ui/StatIcon'
import * as progressApi from '../../api/progress'
import { ApiError } from '../../api/client'
import { TARGET_STAT_LABELS } from '../../types/exercise'
import type { TargetStat } from '../../types/exercise'
import type {
  AnalyticsDayStatus,
  AnalyticsInsightRead,
  AnalyticsMuscleGroup,
  AnalyticsOverviewRead,
  AnalyticsRecordRead,
  AnalyticsStatRead,
} from '../../types/analytics'
import type { StatHistoryPointRead } from '../../types/progress'

const ICE = '#D7EFFF'
// Something to look at: a drop, a skipped block, a load that climbs too
// fast. Kept apart from the persimmon accent, which means "act" elsewhere.
const WARN = '#F2B84B'
const TEAM = '#3E8EC4'
const MONTHS = ['янв', 'фев', 'мар', 'апр', 'мая', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

const CARD = `rounded-md ${CARD_BORDER} bg-dark-card`

function formatNumber(value: number): string {
  return (Math.round(value * 10) / 10).toString().replace('.', ',')
}

function formatSigned(value: number): string {
  const rounded = Math.round(value * 10) / 10
  if (rounded === 0) {
    return '0'
  }
  return `${rounded > 0 ? '+' : '−'}${formatNumber(Math.abs(rounded))}`
}

function formatRecord(value: number, unit: AnalyticsRecordRead['unit']): string {
  if (unit === 'kg') {
    return `${formatNumber(value)} кг`
  }
  if (unit === 'seconds') {
    const total = Math.round(value)
    return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
  }
  return String(Math.round(value))
}

// "YYYY-MM-DD" split, not parsed through Date -- no UTC-midnight shift.
function formatDay(iso: string): string {
  const [, month, day] = iso.split('-')
  return `${Number(day)} ${MONTHS[Number(month) - 1]}`
}

function dayTime(iso: string): number {
  const [year, month, day] = iso.split('-').map(Number)
  return Date.UTC(year, month - 1, day)
}

function Eyebrow({ children }: { children: ReactNode }) {
  return <h2 className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#8A94A6]">{children}</h2>
}

// -- Главное за период --

export function InsightList({
  insights,
  days,
  onShowRecords,
}: {
  insights: AnalyticsInsightRead[]
  days: number
  onShowRecords: () => void
}) {
  const navigate = useNavigate()
  return (
    <section className="flex flex-col gap-2" aria-label="Главное за период">
      <Eyebrow>Главное за {days} дней</Eyebrow>
      {insights.length === 0 ? (
        <p className={`${CARD} p-4 text-sm text-[#8A94A6]`}>
          Пока мало данных для выводов. Потренируйся по плану пару недель — здесь появится, что растёт и что просело.
        </p>
      ) : (
        insights.map((insight) => (
          <div
            key={insight.kind}
            className={`${CARD} flex gap-3 p-3.5`}
            style={insight.tone === 'warning' ? { borderTopColor: 'rgba(242,184,75,0.6)' } : undefined}
          >
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
              style={{ background: insight.tone === 'warning' ? 'rgba(242,184,75,0.14)' : 'rgba(215,239,255,0.12)' }}
            >
              <i
                className={`ti ${
                  insight.kind === 'decline'
                    ? 'ti-trending-down'
                    : insight.kind === 'records'
                      ? 'ti-trophy'
                      : insight.kind === 'milestone'
                        ? 'ti-target'
                        : 'ti-calendar-check'
                }`}
                style={{ color: insight.tone === 'warning' ? WARN : ICE }}
                aria-hidden="true"
              />
            </span>
            <div className="flex min-w-0 flex-col gap-1.5">
              <p className="text-sm font-semibold leading-snug text-[#F5F7FA]">{insight.title}</p>
              <p className="text-xs leading-relaxed text-[#AEB7C6]">{insight.detail}</p>
              {insight.action === 'ask_coach' && insight.coach_prompt !== null && (
                <button
                  type="button"
                  onClick={() => navigate('/coach', { state: { draft: insight.coach_prompt } })}
                  className="flex items-center gap-1 self-start text-xs font-semibold text-accent-ice"
                >
                  Спросить тренера
                  <i className="ti ti-chevron-right" aria-hidden="true" />
                </button>
              )}
              {insight.action === 'records' && (
                <button type="button" onClick={onShowRecords} className="flex items-center gap-1 self-start text-xs font-semibold text-accent-ice">
                  Все рекорды
                  <i className="ti ti-chevron-right" aria-hidden="true" />
                </button>
              )}
            </div>
          </div>
        ))
      )}
    </section>
  )
}

// -- Характеристики --

export function StatSection({
  stats,
  days,
  accessToken,
  selected,
  onSelect,
}: {
  stats: AnalyticsStatRead[]
  days: number
  accessToken: string
  selected: TargetStat
  onSelect: (stat: TargetStat) => void
}) {
  const current = stats.find((stat) => stat.stat === selected) ?? stats[0]
  return (
    <section className="flex flex-col gap-2" aria-label="Характеристики">
      <Eyebrow>Характеристики</Eyebrow>
      <div className="grid grid-cols-3 gap-2">
        {stats.map((stat) => {
          const isSelected = stat.stat === selected
          const falling = stat.delta <= -1
          const tone = falling ? WARN : stat.delta >= 0.05 ? ICE : '#8A94A6'
          return (
            <button
              key={stat.stat}
              type="button"
              onClick={() => onSelect(stat.stat)}
              aria-pressed={isSelected}
              aria-label={`${TARGET_STAT_LABELS[stat.stat]}: ${formatNumber(stat.current_value)}, ${formatSigned(stat.delta)}`}
              className="flex flex-col items-center gap-1 rounded-md px-1 py-2.5 transition-colors"
              style={{
                background: isSelected ? (falling ? 'rgba(242,184,75,0.07)' : 'rgba(215,239,255,0.08)') : '#171F30',
                border: isSelected ? `2px solid ${falling ? WARN : ICE}` : '2px solid transparent',
                borderTop: isSelected ? undefined : '2px solid rgba(215,239,255,0.25)',
              }}
            >
              <span className="flex h-5 items-center justify-center" style={{ color: falling ? WARN : ICE }}>
                <StatIcon stat={stat.stat} size={16} />
              </span>
              <span className="w-full truncate px-1 text-center text-[10px] leading-4 text-[#8A94A6]">
                {TARGET_STAT_LABELS[stat.stat]}
              </span>
              <span className="font-mono text-[17px] font-bold tabular-nums text-[#F5F7FA]">{Math.round(stat.current_value)}</span>
              <span className="font-mono text-[11px] font-semibold tabular-nums" style={{ color: tone }}>
                {formatSigned(stat.delta)}
              </span>
            </button>
          )
        })}
      </div>
      {current !== undefined && <StatChart stat={current} days={days} accessToken={accessToken} />}
    </section>
  )
}

function StatChart({ stat, days, accessToken }: { stat: AnalyticsStatRead; days: number; accessToken: string }) {
  const [points, setPoints] = useState<StatHistoryPointRead[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setPoints(null)
    progressApi
      .getStatsHistory(stat.stat, days, accessToken)
      .then((result) => {
        if (!cancelled) {
          setPoints(result)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Не удалось загрузить историю.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [stat.stat, days, accessToken])

  const falling = stat.delta <= -1
  const data = (points ?? []).map((point) => ({ t: dayTime(point.date), value: point.value }))
  const values = data.map((point) => point.value)
  const low = values.length > 0 ? Math.floor(Math.min(...values) - 1) : 0
  const high = values.length > 0 ? Math.ceil(Math.max(...values) + 1) : 1
  const last = data[data.length - 1]
  const skipped = stat.skipped_dates.map(dayTime)
  const start = data.length > 0 ? Math.min(data[0].t, ...skipped) : 0
  const end = data.length > 0 ? Math.max(last.t, ...skipped) : 1

  return (
    <div className={`${CARD} flex flex-col gap-2 p-4`}>
      <div className="flex items-baseline justify-between">
        <div>
          <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[#8A94A6]">
            {TARGET_STAT_LABELS[stat.stat]} · {days} дней
          </span>
          <div className="font-mono text-[26px] font-extrabold leading-tight tabular-nums text-[#F5F7FA]">
            {formatNumber(stat.current_value)}
          </div>
        </div>
        <span className="font-mono text-sm font-bold tabular-nums" style={{ color: falling ? WARN : ICE }}>
          {formatSigned(stat.delta)}
        </span>
      </div>
      <FormError message={error} />
      {points === null && error === null && <p className="py-12 text-center text-sm text-[#8A94A6]">Загрузка...</p>}
      {points !== null && data.length === 0 && (
        <p className="py-12 text-center text-sm text-[#8A94A6]">За этот период характеристика не менялась.</p>
      )}
      {data.length > 0 && (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
              <defs>
                <linearGradient id="analyticsAreaFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={ICE} stopOpacity={0.1} />
                  <stop offset="95%" stopColor={ICE} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.08)" vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={[start, end]}
                tickFormatter={(value: number) => formatDay(new Date(value).toISOString().slice(0, 10))}
                stroke="#8A94A6"
                tick={{ fill: '#8A94A6', fontSize: 11 }}
                tickCount={4}
              />
              <YAxis domain={[low, high]} allowDecimals={false} stroke="#8A94A6" tick={{ fill: '#8A94A6', fontSize: 11 }} />
              <Tooltip
                labelFormatter={(label) => (typeof label === 'number' ? formatDay(new Date(label).toISOString().slice(0, 10)) : label)}
                formatter={(value) => (typeof value === 'number' ? formatNumber(value) : value)}
                contentStyle={{ background: '#0D1420', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6 }}
                labelStyle={{ color: '#8A94A6' }}
                itemStyle={{ color: ICE }}
              />
              <Area
                type="monotone"
                dataKey="value"
                name={TARGET_STAT_LABELS[stat.stat]}
                stroke={ICE}
                strokeWidth={2}
                fill="url(#analyticsAreaFill)"
                dot={false}
                activeDot={{ r: 5, fill: ICE, stroke: '#171F30', strokeWidth: 2 }}
              />
              {skipped.map((t, index) => (
                <ReferenceDot key={`${t}-${index}`} x={t} y={low} r={4} fill={WARN} stroke="#171F30" strokeWidth={1.5} />
              ))}
              <ReferenceDot x={last.t} y={last.value} r={5} fill={ICE} stroke="#171F30" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
      {stat.skipped_dates.length > 0 && (
        <p className="flex items-center gap-1.5 text-[11px] text-[#8A94A6]">
          <span className="h-2 w-2 rounded-full" style={{ background: WARN }} aria-hidden="true" />
          пропущено {stat.skipped_dates.length} из {stat.planned_blocks} блоков на эту характеристику
        </p>
      )}
    </div>
  )
}

// -- Рекорды --

export function RecordsSection({ records, days }: { records: AnalyticsRecordRead[]; days: number }) {
  return (
    <section id="records" className="flex scroll-mt-4 flex-col gap-2" aria-label="Рекорды">
      <Eyebrow>Рекорды за {days} дней</Eyebrow>
      {records.length === 0 ? (
        <p className={`${CARD} p-4 text-sm text-[#8A94A6]`}>
          Новых рекордов пока нет. Рекорд засчитывается, когда подход лучше твоего прошлого лучшего в этом упражнении.
        </p>
      ) : (
        <ul className={`${CARD} px-3.5 py-1`}>
          {records.map((record) => (
            <li
              key={`${record.exercise_name}-${record.unit}`}
              className="flex items-center gap-2.5 border-b border-white/5 py-2.5 last:border-b-0"
            >
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[13px] text-[#F5F7FA]">{record.exercise_name}</span>
                <span className="text-[10.5px] text-[#5B6472]">{formatDay(record.achieved_on)}</span>
              </span>
              <span className="font-mono text-xs tabular-nums text-[#8A94A6]">{formatRecord(record.before, record.unit)}</span>
              <i className="ti ti-arrow-right text-xs text-[#5B6472]" aria-hidden="true" />
              <span className="min-w-[64px] text-right font-mono text-sm font-bold tabular-nums text-[#F5F7FA]">
                {formatRecord(record.after, record.unit)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

// -- Регулярность --

const DAY_STYLE: Record<AnalyticsDayStatus, { background?: string; border?: string; label: string }> = {
  done: { background: ICE, label: 'сделано' },
  team: { background: TEAM, label: 'командный лёд' },
  skipped: { border: `1.5px solid ${WARN}`, label: 'пропущено' },
  rest: { background: 'rgba(255,255,255,0.06)', label: 'отдых' },
  future: { background: 'transparent', border: '1px dashed rgba(255,255,255,0.08)', label: 'впереди' },
  none: { background: 'rgba(255,255,255,0.03)', label: 'нет плана' },
}
const LEGEND: AnalyticsDayStatus[] = ['done', 'team', 'skipped', 'rest']

export function RegularitySection({ regularity }: { regularity: AnalyticsOverviewRead['regularity'] }) {
  return (
    <section className="flex flex-col gap-2" aria-label="Регулярность">
      <Eyebrow>Регулярность</Eyebrow>
      <div className={`${CARD} flex flex-col gap-3.5 p-4`}>
        <div className="grid grid-cols-3 gap-2">
          <Figure value={regularity.completed_sessions} of={regularity.planned_sessions} label="тренировок по плану" />
          <Figure value={regularity.streak_days} label="дней серия" />
          {regularity.team_total !== null ? (
            <Figure value={regularity.team_going ?? 0} of={regularity.team_total} label="командный лёд" />
          ) : (
            <span />
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="grid grid-cols-7 gap-1.5 text-center text-[9px] text-[#5B6472]" aria-hidden="true">
            {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((day) => (
              <span key={day}>{day}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1.5" role="list" aria-label="Последние 4 недели">
            {regularity.calendar.map((day) => {
              const style = DAY_STYLE[day.status]
              return (
                <span
                  key={day.date}
                  role="listitem"
                  aria-label={`${formatDay(day.date)}: ${style.label}`}
                  title={`${formatDay(day.date)}: ${style.label}`}
                  className="h-6 rounded"
                  style={{ background: style.background, border: style.border }}
                />
              )
            })}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[10.5px] text-[#8A94A6]">
            {LEGEND.map((status) => (
              <span key={status} className="flex items-center gap-1.5">
                <span
                  className="h-2.5 w-2.5 rounded-[3px]"
                  style={{ background: DAY_STYLE[status].background, border: DAY_STYLE[status].border }}
                  aria-hidden="true"
                />
                {DAY_STYLE[status].label}
              </span>
            ))}
          </div>
        </div>

        {regularity.most_skipped.length > 0 && (
          <p className="border-t border-white/5 pt-3 text-xs leading-relaxed text-[#AEB7C6]">
            Чаще всего пропускаешь{' '}
            {regularity.most_skipped.map((item, index) => (
              <span key={item.exercise_name}>
                {index > 0 && ' и '}
                <span className="font-semibold text-[#F5F7FA]">{item.exercise_name.toLowerCase()}</span>
              </span>
            ))}{' '}
            — {regularity.most_skipped.map((item) => item.count).join(' и ')} раза.
          </p>
        )}
      </div>
    </section>
  )
}

function Figure({ value, of, label }: { value: number; of?: number; label: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-xl font-extrabold tabular-nums text-[#F5F7FA]">
        {value}
        {of !== undefined && <span className="text-sm text-[#5B6472]"> / {of}</span>}
      </span>
      <span className="text-[10.5px] leading-tight text-[#8A94A6]">{label}</span>
    </div>
  )
}

// -- Нагрузка и самочувствие --

export function LoadSection({ load }: { load: AnalyticsOverviewRead['load'] }) {
  const byTonnage = load.weeks.some((week) => week.tonnage_kg > 0)
  const amounts = load.weeks.map((week) => (byTonnage ? week.tonnage_kg : week.sets))
  const max = Math.max(...amounts, 1)
  const empty = amounts.every((amount) => amount === 0)
  return (
    <section className="flex flex-col gap-2" aria-label="Нагрузка и самочувствие">
      <Eyebrow>Нагрузка и самочувствие</Eyebrow>
      <div className={`${CARD} flex flex-col gap-3 p-4`}>
        {empty ? (
          <p className="text-sm text-[#8A94A6]">Отмечай подходы на тренировке — здесь появится нагрузка по неделям.</p>
        ) : (
          <>
            <div className="grid grid-cols-4 items-end gap-3" role="list" aria-label="Нагрузка по неделям">
              {load.weeks.map((week, index) => {
                const amount = amounts[index]
                const isCurrent = index === load.weeks.length - 1
                const hard = week.hard_share
                const label = byTonnage ? `${formatNumber(amount / 1000)} т` : `${amount} подх.`
                return (
                  <div key={week.week_start} role="listitem" className="flex flex-col items-center gap-1">
                    <span className={`font-mono text-[10.5px] tabular-nums ${isCurrent ? 'font-bold text-[#F5F7FA]' : 'text-[#AEB7C6]'}`}>
                      {label}
                    </span>
                    <span className="flex h-24 w-full items-end">
                      <span
                        className="w-full rounded-t"
                        style={{ height: `${Math.max(4, (amount / max) * 100)}%`, background: isCurrent ? ICE : 'rgba(215,239,255,0.35)' }}
                      />
                    </span>
                    <span className="text-[10px] text-[#5B6472]">{isCurrent ? 'эта' : formatDay(week.week_start)}</span>
                    <span
                      className="font-mono text-[10.5px] tabular-nums"
                      style={{ color: hard !== null && hard >= 0.35 ? WARN : '#8A94A6', fontWeight: hard !== null && hard >= 0.35 ? 700 : 400 }}
                    >
                      {hard !== null ? `${Math.round(hard * 100)}%` : '—'}
                    </span>
                  </div>
                )
              })}
            </div>
            <p className="text-[10.5px] leading-relaxed text-[#5B6472]">
              {byTonnage ? 'Столбцы — поднятый вес за неделю.' : 'Столбцы — подходы за неделю.'} Проценты — доля подходов, отмеченных «тяжело» и
              «максимум».
            </p>
          </>
        )}
        {load.warning !== null && (
          <div className="flex items-start gap-2.5 rounded-md px-3 py-2.5" style={{ background: 'rgba(242,184,75,0.08)' }}>
            <i className="ti ti-alert-triangle mt-0.5" style={{ color: WARN }} aria-hidden="true" />
            <p className="text-xs leading-relaxed text-[#F5F7FA]">{load.warning}</p>
          </div>
        )}
      </div>
    </section>
  )
}

// -- Баланс нагрузки --

const GROUP_LABELS: Record<AnalyticsMuscleGroup, string> = {
  legs: 'Ноги',
  core: 'Корпус',
  back: 'Спина',
  chest_shoulders: 'Грудь, плечи',
  arms: 'Предплечья',
}

export function BalanceSection({ balance }: { balance: AnalyticsOverviewRead['balance'] }) {
  const max = Math.max(...balance.groups.map((group) => group.share), 0.0001)
  return (
    <section className="flex flex-col gap-2" aria-label="Баланс нагрузки">
      <Eyebrow>Баланс нагрузки</Eyebrow>
      <div className={`${CARD} flex flex-col gap-2.5 p-4`}>
        {balance.groups.length === 0 ? (
          <p className="text-sm text-[#8A94A6]">Выполни несколько тренировок — покажем, какие группы мышц нагружаются больше, а какие отстают.</p>
        ) : (
          <div className="grid grid-cols-[92px_1fr_36px] items-center gap-x-2.5 gap-y-2.5 text-xs">
            {balance.groups.map((group) => (
              <div key={group.group} className="contents">
                <span className="text-[#F5F7FA]">{GROUP_LABELS[group.group]}</span>
                <span className="h-2 rounded bg-white/5">
                  <span className="block h-2 rounded" style={{ width: `${(group.share / max) * 100}%`, background: ICE }} />
                </span>
                <span className="text-right font-mono tabular-nums text-[#AEB7C6]">{Math.round(group.share * 100)}%</span>
              </div>
            ))}
          </div>
        )}
        {balance.note !== null && (
          <p className="mt-1 border-t border-white/5 pt-2.5 text-xs leading-relaxed text-[#AEB7C6]">{balance.note}</p>
        )}
      </div>
    </section>
  )
}
