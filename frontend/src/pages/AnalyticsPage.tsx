import { useEffect, useState } from 'react'
import {
  BalanceSection,
  InsightList,
  LoadSection,
  RecordsSection,
  RegularitySection,
  StatSection,
} from '../components/analytics/AnalyticsSections'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { PremiumGate } from '../components/ui/PremiumGate'
import * as analyticsApi from '../api/analytics'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { AnalyticsOverviewRead } from '../types/analytics'
import type { TargetStat } from '../types/exercise'

const PERIODS = [7, 30, 90] as const
type Days = (typeof PERIODS)[number]

const ANALYTICS_PREMIUM_GATE_DESCRIPTION =
  'С премиум-подпиской откроются выводы о твоём прогрессе, рекорды, регулярность, нагрузка по неделям и баланс по группам мышц, а также персональный AI-тренер: задавай вопросы о своих тренировках и получай советы с учётом твоих реальных данных.'

export function AnalyticsPage() {
  const { user, accessToken } = useAuth()
  const hasPremium = user?.has_premium === true

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 pb-32 pt-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Аналитика</h1>
        </div>

        {hasPremium && accessToken !== null ? (
          <AnalyticsContent accessToken={accessToken} />
        ) : (
          <PremiumGate title="Аналитика — часть премиум-подписки" description={ANALYTICS_PREMIUM_GATE_DESCRIPTION} />
        )}
      </div>
    </div>
  )
}

function AnalyticsContent({ accessToken }: { accessToken: string }) {
  const [days, setDays] = useState<Days>(30)
  const [overview, setOverview] = useState<AnalyticsOverviewRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  // The stat the chart shows: the player's pick, else whatever dropped.
  const [picked, setPicked] = useState<TargetStat | null>(null)

  useEffect(() => {
    let cancelled = false
    setOverview(null)
    analyticsApi
      .getAnalyticsOverview(days, accessToken)
      .then((result) => {
        if (!cancelled) {
          setOverview(result)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Не удалось загрузить аналитику.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, days])

  const worst = overview !== null ? [...overview.stats].sort((a, b) => a.delta - b.delta)[0] : undefined
  const selected: TargetStat = picked ?? (worst !== undefined && worst.delta <= -1 ? worst.stat : 'strength')

  return (
    <>
      <div role="group" aria-label="Период" className="flex gap-1.5">
        {PERIODS.map((value) => (
          <button
            key={value}
            type="button"
            onClick={() => setDays(value)}
            aria-pressed={days === value}
            className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition-colors ${
              days === value ? 'bg-accent-ice text-[#0B0F14]' : 'bg-white/5 text-[#C9D1DC] hover:bg-white/10'
            }`}
          >
            {value} дней
          </button>
        ))}
      </div>

      <FormError message={error} />
      {overview === null && error === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

      {overview !== null && (
        <>
          <InsightList
            insights={overview.insights}
            days={overview.days}
            onShowRecords={() => document.getElementById('records')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
          />
          <StatSection stats={overview.stats} days={overview.days} accessToken={accessToken} selected={selected} onSelect={setPicked} />
          <RecordsSection records={overview.records} days={overview.days} />
          <RegularitySection regularity={overview.regularity} />
          <LoadSection load={overview.load} />
          <BalanceSection balance={overview.balance} />
        </>
      )}
    </>
  )
}
