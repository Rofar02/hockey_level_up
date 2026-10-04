import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as coachChatApi from '../api/coachChat'
import { useAuth } from '../hooks/useAuth'
import { TARGET_STAT_LABELS } from '../types/exercise'
import type { TargetStat } from '../types/exercise'
import type { WeeklyReviewRead } from '../types/coachChat'
import { addDays, formatShortDate, parseIsoDate } from '../utils/date'
import { CARD_CLASS } from './ui/cardStyle'

function recordsLabel(count: number): string {
  const lastTwo = count % 100
  const last = count % 10
  if (lastTwo >= 11 && lastTwo <= 14) return 'рекордов'
  if (last === 1) return 'рекорд'
  if (last >= 2 && last <= 4) return 'рекорда'
  return 'рекордов'
}

// "Разбор недели" on Home (2026-10-04, premium): the coach's Monday review
// of last week (WeeklyReviewService). Shows until the player closes it;
// renders nothing when there's no review to show.
export function WeeklyReviewCard() {
  const { accessToken } = useAuth()
  const navigate = useNavigate()
  const [review, setReview] = useState<WeeklyReviewRead | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    coachChatApi
      .getWeeklyReview(accessToken)
      .then((result) => !cancelled && setReview(result))
      .catch(() => {
        // Best-effort -- the card just doesn't render.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  if (review === null) {
    return null
  }

  function close() {
    if (review === null || accessToken === null) {
      return
    }
    setReview(null)
    void coachChatApi.markWeeklyReviewRead(review.id, accessToken).catch(() => undefined)
  }

  const weekStart = parseIsoDate(review.week_start)
  const tiles: { value: string; label: string; accent?: boolean }[] = [
    { value: `${review.sessions_completed}/${review.sessions_planned}`, label: 'тренировки' },
    { value: String(review.records_count), label: recordsLabel(review.records_count), accent: review.records_count > 0 },
  ]
  if (review.top_stat !== null && review.top_stat_delta !== null) {
    const label = TARGET_STAT_LABELS[review.top_stat as TargetStat] ?? review.top_stat
    tiles.push({ value: `+${Math.round(review.top_stat_delta)}`, label: label.toLowerCase() })
  }

  return (
    <section className={`flex flex-col gap-3 border-t-2 border-t-accent-ice p-4 ${CARD_CLASS}`}>
      <div className="flex items-center gap-2.5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-ice/10">
          <i className="ti ti-calendar-stats text-lg text-accent-ice" aria-hidden="true" />
        </span>
        <div className="flex flex-1 flex-col">
          <span className="text-sm font-semibold">Разбор недели</span>
          <span className="text-xs text-text-secondary">
            {formatShortDate(weekStart)} – {formatShortDate(addDays(weekStart, 6))}
          </span>
        </div>
        <button
          type="button"
          aria-label="Закрыть разбор"
          onClick={close}
          className="-mr-2 flex h-11 w-11 items-center justify-center rounded text-text-secondary hover:text-text-primary"
        >
          <i className="ti ti-x text-lg" aria-hidden="true" />
        </button>
      </div>

      <p className="whitespace-pre-line text-sm leading-relaxed">{review.text}</p>

      <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${tiles.length}, minmax(0, 1fr))` }}>
        {tiles.map((tile) => (
          <div key={tile.label} className="flex flex-col items-center gap-0.5 rounded-md bg-dark-bg px-2 py-2.5">
            <span className={`font-display text-xl font-semibold ${tile.accent === true ? 'text-accent-ice' : ''}`}>
              {tile.value}
            </span>
            <span className="text-[11px] text-text-secondary">{tile.label}</span>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={() => navigate('/coach')}
        className="flex min-h-11 items-center justify-center gap-2 rounded border border-accent-ice/25 text-sm font-semibold text-accent-ice transition-colors hover:bg-accent-ice/5"
      >
        <i className="ti ti-message-chatbot" aria-hidden="true" />
        Обсудить с тренером
      </button>
    </section>
  )
}
