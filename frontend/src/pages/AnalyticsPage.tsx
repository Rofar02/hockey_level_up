import { useEffect, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { PremiumGate } from '../components/ui/PremiumGate'
import { SelectField } from '../components/ui/SelectField'
import * as analyticsApi from '../api/analytics'
import { ApiError } from '../api/client'
import * as progressApi from '../api/progress'
import * as skillsApi from '../api/skills'
import { useAuth } from '../hooks/useAuth'
import type { AnalyticsSummaryRead } from '../types/analytics'
import { TARGET_STATS, TARGET_STAT_LABELS } from '../types/exercise'
import type { StatHistoryPointRead } from '../types/progress'
import type { SkillSummaryRead } from '../types/skill'
import { buildAnalyticsSummaryText } from '../utils/analyticsSummary'

const PERIOD_OPTIONS = [
  { value: '30', label: '30 дней' },
  { value: '90', label: '90 дней' },
  { value: '180', label: '180 дней' },
]

type Days = 30 | 90 | 180

type SeriesSelection =
  | { kind: 'stat'; statType: (typeof TARGET_STATS)[number] }
  | { kind: 'skill'; skillId: string }

function encodeSelection(selection: SeriesSelection): string {
  return selection.kind === 'stat' ? `stat:${selection.statType}` : `skill:${selection.skillId}`
}

function decodeSelection(value: string): SeriesSelection | null {
  const [kind, id] = value.split(':')
  if (kind === 'stat' && (TARGET_STATS as readonly string[]).includes(id)) {
    return { kind: 'stat', statType: id as (typeof TARGET_STATS)[number] }
  }
  if (kind === 'skill' && id !== undefined && id !== '') {
    return { kind: 'skill', skillId: id }
  }
  return null
}

// Point.date is a plain "YYYY-MM-DD" (Python's `date`, serialized as-is) --
// split rather than parsed through `Date` so this never trips over the
// UTC-midnight timezone shift `new Date(iso)` can cause (same reasoning as
// utils/date.ts's parseIsoDate).
function formatPointDate(iso: string): string {
  const [, month, day] = iso.split('-')
  return `${day}.${month}`
}

// First-to-last change over the shown period, as a percentage when the
// starting value is non-zero (most stats/skills), otherwise as a plain
// signed difference (a percentage of zero is meaningless). null when
// there's nothing to compare (fewer than 2 points, or literally no change).
function formatDelta(points: StatHistoryPointRead[]): string | null {
  if (points.length < 2) {
    return null
  }
  const diff = points[points.length - 1].value - points[0].value
  if (diff === 0) {
    return null
  }
  const sign = diff > 0 ? '+' : ''
  const first = points[0].value
  return first !== 0 ? `${sign}${((diff / Math.abs(first)) * 100).toFixed(0)}%` : `${sign}${diff.toFixed(1)}`
}

const CARD_BORDER = 'border-t border-[rgba(215,239,255,0.35)]'
const ICE = '#D7EFFF'

const ANALYTICS_PREMIUM_GATE_DESCRIPTION =
  'С премиум-подпиской откроются графики роста характеристик и навыков, текстовые инсайты о вашем прогрессе, а скоро — персональный AI-тренер.'

export function AnalyticsPage() {
  const { user, accessToken } = useAuth()
  const hasPremium = user?.has_premium === true

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Аналитика</h1>
        </div>

        {hasPremium && accessToken !== null ? (
          <AnalyticsContent accessToken={accessToken} />
        ) : (
          <PremiumGate
            title="Аналитика — часть премиум-подписки"
            description={ANALYTICS_PREMIUM_GATE_DESCRIPTION}
          />
        )}
      </div>
    </div>
  )
}

function AnalyticsContent({ accessToken }: { accessToken: string }) {
  const [skills, setSkills] = useState<SkillSummaryRead[] | null>(null)
  const [skillsLoadError, setSkillsLoadError] = useState<string | null>(null)

  const [selection, setSelection] = useState<SeriesSelection>({
    kind: 'stat',
    statType: 'strength',
  })
  const [days, setDays] = useState<Days>(90)

  const [points, setPoints] = useState<StatHistoryPointRead[] | null>(null)
  const [isLoadingPoints, setIsLoadingPoints] = useState(true)
  const [pointsError, setPointsError] = useState<string | null>(null)

  const [summary, setSummary] = useState<AnalyticsSummaryRead | null>(null)
  const [summaryError, setSummaryError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    skillsApi
      .listSkills(accessToken)
      .then((result) => {
        if (!cancelled) {
          setSkills(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSkillsLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить навыки.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  // Primitive fields pulled out of `selection` (a plain object recreated
  // every render) so the effect below can list real dependencies instead of
  // the whole object or a derived expression.
  const selectedStatType = selection.kind === 'stat' ? selection.statType : null
  const selectedSkillId = selection.kind === 'skill' ? selection.skillId : null

  useEffect(() => {
    let cancelled = false
    setIsLoadingPoints(true)
    const request =
      selectedStatType !== null
        ? progressApi.getStatsHistory(selectedStatType, days, accessToken)
        : selectedSkillId !== null
          ? skillsApi.getSkillsHistory(selectedSkillId, days, accessToken)
          : null
    if (request === null) {
      setIsLoadingPoints(false)
      return
    }
    request
      .then((result) => {
        if (!cancelled) {
          setPoints(result)
          setPointsError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setPointsError(err instanceof ApiError ? err.message : 'Не удалось загрузить историю.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingPoints(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, selectedStatType, selectedSkillId, days])

  useEffect(() => {
    let cancelled = false
    analyticsApi
      .getAnalyticsSummary(days, accessToken)
      .then((result) => {
        if (!cancelled) {
          setSummary(result)
          setSummaryError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSummaryError(err instanceof ApiError ? err.message : 'Не удалось загрузить сводку.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, days])

  const selectedLabel =
    selection.kind === 'stat'
      ? TARGET_STAT_LABELS[selection.statType]
      : (skills?.find((skill) => skill.id === selection.skillId)?.name ?? '')

  const seriesOptions = [
    ...TARGET_STATS.map((statType) => ({
      value: encodeSelection({ kind: 'stat', statType }),
      label: `Характеристика: ${TARGET_STAT_LABELS[statType]}`,
    })),
    ...(skills ?? []).map((skill) => ({
      value: encodeSelection({ kind: 'skill', skillId: skill.id }),
      label: `Навык: ${skill.name}`,
    })),
  ]

  return (
    <>
      <FormError message={summaryError} />
      {summary !== null && (
        <div className={`rounded-md ${CARD_BORDER} bg-dark-card p-4`}>
          <p className="text-sm leading-relaxed text-[#F5F7FA]">
            {buildAnalyticsSummaryText(summary)}
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <SelectField
          label="Показатель"
          options={seriesOptions}
          value={encodeSelection(selection)}
          onChange={(event) => {
            const decoded = decodeSelection(event.target.value)
            if (decoded !== null) {
              setSelection(decoded)
            }
          }}
        />
        <SelectField
          label="Период"
          options={PERIOD_OPTIONS}
          value={String(days)}
          onChange={(event) => setDays(Number(event.target.value) as Days)}
        />
      </div>
      <FormError message={skillsLoadError} />

      <div className={`flex flex-col gap-3 rounded-md ${CARD_BORDER} bg-dark-card p-4`}>
        <FormError message={pointsError} />
        {isLoadingPoints && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {!isLoadingPoints && points !== null && points.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-12 text-center">
            <i className="ti ti-chart-line text-3xl text-[#8A94A6]" aria-hidden="true" />
            <p className="text-sm text-[#8A94A6]">Пока нет истории за этот период.</p>
          </div>
        )}

        {!isLoadingPoints && points !== null && points.length > 0 && (
          <>
            <div className="flex items-baseline justify-between">
              <div>
                <span className="text-[10px] uppercase tracking-wide text-[#8A94A6]">{selectedLabel}</span>
                <div className="font-mono text-[26px] font-extrabold leading-tight text-[#F5F7FA]">
                  {points[points.length - 1].value}
                </div>
              </div>
              {formatDelta(points) !== null && (
                <span className="font-mono text-sm font-bold text-accent-ice">{formatDelta(points)}</span>
              )}
            </div>
            <div className="h-56">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                  <defs>
                    <linearGradient id="analyticsAreaFill" x1="0" y1="0" x2="0" y2="1">
                      {/* Area fill is a wash (~10% opacity), not a saturated block --
                          dataviz skill's mark spec. Was 35% before this pass. */}
                      <stop offset="5%" stopColor={ICE} stopOpacity={0.1} />
                      <stop offset="95%" stopColor={ICE} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  {/* Solid hairline grid, one step off the surface -- dashed
                      gridlines are a flagged anti-pattern (reads as a
                      threshold/projection line, not a grid). */}
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={formatPointDate}
                    stroke="#8A94A6"
                    tick={{ fill: '#8A94A6', fontSize: 12 }}
                  />
                  <YAxis stroke="#8A94A6" tick={{ fill: '#8A94A6', fontSize: 12 }} />
                  <Tooltip
                    labelFormatter={(label) =>
                      typeof label === 'string' ? formatPointDate(label) : label
                    }
                    contentStyle={{
                      background: '#0D1420',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: 6,
                    }}
                    labelStyle={{ color: '#8A94A6' }}
                    itemStyle={{ color: ICE }}
                  />
                  <Area
                    type="monotone"
                    dataKey="value"
                    stroke={ICE}
                    strokeWidth={2}
                    fill="url(#analyticsAreaFill)"
                    dot={false}
                    activeDot={{ r: 5, fill: ICE, stroke: '#171F30', strokeWidth: 2 }}
                  />
                  {/* The one persistent marker -- "now" -- sized and ringed
                      per the mark spec (>=8px / r>=4, 2px surface ring) so it
                      stays legible where it meets the line; every other point
                      only shows on hover (activeDot above) rather than
                      cluttering the line with a dot per day. */}
                  <ReferenceDot
                    x={points[points.length - 1].date}
                    y={points[points.length - 1].value}
                    r={5}
                    fill={ICE}
                    stroke="#171F30"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </>
        )}
      </div>
    </>
  )
}
