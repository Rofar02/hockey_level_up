import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ReportRewardScreen } from '../components/ReportRewardScreen'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import * as scheduleApi from '../api/schedule'
import * as trainingDiaryApi from '../api/trainingDiary'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { TargetStat } from '../types/exercise'
import { DAY_SESSION_TYPE_LABELS, SESSION_TYPE_COLORS, SESSION_TYPE_ICONS } from '../types/schedule'
import type { DayPlanRead } from '../types/schedule'
import {
  FOCUS_RESULT_LABELS,
  GAME_RESULT_LABELS,
  GAME_WORK_ON_LABELS,
  ICE_DURATIONS,
  ICE_EFFORT_LABELS,
  ICE_HIGHLIGHT_LABELS,
  REPORT_REWARD_WINDOW_DAYS,
} from '../types/trainingDiary'
import type {
  DiaryReportIn,
  FocusResult,
  IceFocusRead,
  GameResult,
  GameWorkOn,
  IceEffort,
  IceHighlight,
  TrainingDiaryEntryRead,
} from '../types/trainingDiary'
import { parseIsoDate, toIsoDate } from '../utils/date'

const COUNTER_MAX = { goals: 30, assists: 30, shots: 100 } as const
type Counter = keyof typeof COUNTER_MAX

interface Earned {
  stats: Partial<Record<TargetStat, number>>
  xp: number
  focusDone: boolean
}

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value]
}

function daysBetween(fromIso: string, toIso: string): number {
  return Math.round((parseIsoDate(toIso).getTime() - parseIsoDate(fromIso).getTime()) / 86_400_000)
}

// The report after an ice day or a game (2026-10-08 redesign of the 09-21
// notebook) -- a few taps instead of free text, because after a practice
// nobody wants to write; the taps are what earns the day's stats, the note
// stays optional. Reached from TodayCard, SessionCompleteModal and the
// "Как прошёл лёд?" push. A goalie gets the game form without the
// goals/assists/shots counters (their own form comes later); a player not
// in a team never sees the team-coach lines. No numbers before saving: the
// reward is shown after, on ReportRewardScreen, like the end of an off-ice
// workout. BottomNav is hidden for this route (see ProtectedRoute).
export function TrainingDiaryPage() {
  const { dayPlanId } = useParams<{ dayPlanId: string }>()
  const { accessToken, user } = useAuth()
  const navigate = useNavigate()

  const [day, setDay] = useState<DayPlanRead | null>(null)
  const [trainingSessionId, setTrainingSessionId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saved, setSaved] = useState<TrainingDiaryEntryRead | null>(null)
  const [note, setNote] = useState('')
  const [duration, setDuration] = useState<number | null>(null)
  const [effort, setEffort] = useState<IceEffort | null>(null)
  const [highlights, setHighlights] = useState<IceHighlight[]>([])
  const [focus, setFocus] = useState<IceFocusRead | null>(null)
  const [focusResult, setFocusResult] = useState<FocusResult | null>(null)
  const [result, setResult] = useState<GameResult | null>(null)
  const [counters, setCounters] = useState<Record<Counter, number>>({ goals: 0, assists: 0, shots: 0 })
  const [selfRating, setSelfRating] = useState<number | null>(null)
  const [workOn, setWorkOn] = useState<GameWorkOn[]>([])
  const [shareWithCoach, setShareWithCoach] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [earned, setEarned] = useState<Earned | null>(null)
  // The level before saving, so the reward screen can tell a level-up.
  const levelBeforeRef = useRef<number | null>(null)
  // The note as last saved -- leaving with an unsaved edit saves it.
  const savedNoteRef = useRef('')

  useEffect(() => {
    if (accessToken === null || dayPlanId === undefined) {
      return
    }
    let cancelled = false
    // By id, same as TrainingSessionPage -- the day can be from any week.
    scheduleApi
      .getDayPlanById(dayPlanId, accessToken)
      .then(async (foundDay) => {
        const session = foundDay.training_session
        if (session == null || (foundDay.session_type !== 'on_ice' && foundDay.session_type !== 'game')) {
          if (!cancelled) {
            setLoadError('Отчёт для этого дня недоступен.')
          }
          return
        }
        // Best-effort -- worst case the form just starts empty / without
        // the focus question.
        const [entry, dayFocus] = await Promise.all([
          trainingDiaryApi.getDiaryEntry(session.id, accessToken).catch(() => null),
          foundDay.session_type === 'on_ice'
            ? trainingDiaryApi.getIceFocus(session.id, accessToken).catch(() => null)
            : Promise.resolve(null),
        ])
        if (cancelled) {
          return
        }
        setDay(foundDay)
        setTrainingSessionId(session.id)
        setFocus(dayFocus)
        if (entry !== null) {
          setSaved(entry)
          setNote(entry.note ?? '')
          savedNoteRef.current = entry.note ?? ''
          setDuration(entry.duration_minutes)
          setEffort(entry.effort)
          setHighlights(entry.highlights ?? [])
          setFocusResult(entry.focus_result)
          setResult(entry.game_result)
          setCounters({ goals: entry.goals ?? 0, assists: entry.assists ?? 0, shots: entry.shots ?? 0 })
          setSelfRating(entry.self_rating)
          setWorkOn(entry.work_on ?? [])
          setShareWithCoach(entry.share_rating_with_coach)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(
            err instanceof ApiError && err.status === 404
              ? 'Отчёт для этого дня недоступен.'
              : 'Не удалось загрузить отчёт. Попробуйте ещё раз.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, dayPlanId])

  const isGame = day?.session_type === 'game'
  const isGoalie = user?.position === 'goalie'
  const inTeam = day?.team_event_id != null
  const noteValue = note.trim() === '' ? null : note

  async function submit(report: DiaryReportIn) {
    if (accessToken === null || trainingSessionId === null) {
      return
    }
    setIsSaving(true)
    setSaveError(null)
    levelBeforeRef.current = user?.level ?? null
    try {
      const entry = await trainingDiaryApi.saveDiaryEntry(trainingSessionId, { note: noteValue, report }, accessToken)
      savedNoteRef.current = note
      setSaved(entry)
      if (Object.keys(entry.stat_rewards).length > 0) {
        setEarned({
          stats: entry.stat_rewards,
          xp: entry.xp_reward,
          focusDone: entry.focus_result === 'done' || entry.focus_result === 'partial',
        })
      } else {
        navigate('/', { replace: true })
      }
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить отчёт.')
    } finally {
      setIsSaving(false)
    }
  }

  function submitReport() {
    if (isGame) {
      void submit({
        skipped: false,
        game_result: result,
        ...(isGoalie ? {} : counters),
        self_rating: selfRating,
        work_on: workOn,
        share_rating_with_coach: inTeam && shareWithCoach,
      })
    } else {
      void submit({
        skipped: false,
        duration_minutes: duration,
        effort,
        highlights,
        // The focus stored with the report is the one answered about: the
        // saved one when editing, else today's.
        focus_id: focusResult !== null ? (saved?.focus_id ?? focus?.id ?? null) : null,
        focus_result: focusResult,
      })
    }
  }

  // Back: an edited note is kept (note-only save, the report stays as it
  // was); nothing else is saved without the button.
  async function leave() {
    if (accessToken !== null && trainingSessionId !== null && note !== savedNoteRef.current) {
      await trainingDiaryApi.saveDiaryEntry(trainingSessionId, { note: noteValue }, accessToken).catch(() => {})
    }
    navigate(-1)
  }

  if (earned !== null && accessToken !== null && day !== null) {
    return (
      <ReportRewardScreen
        kind={isGame ? 'game' : 'on_ice'}
        statRewards={earned.stats}
        xpReward={earned.xp}
        focusDone={earned.focusDone}
        levelBefore={levelBeforeRef.current}
        accessToken={accessToken}
      />
    )
  }

  if (loadError !== null) {
    return (
      <div className="relative flex min-h-svh flex-col items-center justify-center gap-4 overflow-hidden px-4">
        <IceGlowBackground />
        <div className="relative z-[1] flex flex-col items-center gap-4">
          <FormError message={loadError} />
          <Button variant="neutral" onClick={() => navigate('/', { replace: true })}>
            На главную
          </Button>
        </div>
      </div>
    )
  }

  if (day === null) {
    return (
      <div className="relative flex min-h-svh items-center justify-center overflow-hidden">
        <IceGlowBackground />
        <p className="relative z-[1] text-sm text-text-secondary">Загрузка...</p>
      </div>
    )
  }

  const dateLabel = parseIsoDate(day.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
  const ageDays = daysBetween(day.date, toIsoDate(new Date()))
  const isFuture = ageDays < 0
  const tooLate = ageDays > REPORT_REWARD_WINDOW_DAYS
  const complete = isGame ? result !== null && selfRating !== null : duration !== null && effort !== null

  return (
    <div className="relative flex min-h-svh flex-col overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex w-full max-w-2xl flex-1 flex-col px-5 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-[calc(1.25rem+env(safe-area-inset-top))]">
        <header className="flex items-center">
          <button
            type="button"
            onClick={() => void leave()}
            aria-label="Назад"
            className="-ml-2 flex h-11 w-11 items-center justify-center rounded-full text-text-secondary transition-colors hover:text-text-primary"
          >
            <i className="ti ti-chevron-left text-2xl" aria-hidden="true" />
          </button>
        </header>

        <div className="mt-1 flex flex-col gap-1">
          <span className={`flex items-center gap-1.5 text-sm ${SESSION_TYPE_COLORS[day.session_type]}`}>
            <i className={`ti ${SESSION_TYPE_ICONS[day.session_type]}`} aria-hidden="true" />
            {DAY_SESSION_TYPE_LABELS[day.session_type]}
            {inTeam ? ' с командой' : ''} · {dateLabel}
          </span>
          <h1 className="font-display text-2xl font-semibold text-text-primary">
            {isGame ? 'Как сыграли?' : 'Как прошёл лёд?'}
          </h1>
          {saved?.rewarded ? (
            <p className="text-xs text-text-secondary">
              <i className="ti ti-check text-accent-ice" aria-hidden="true" /> Очки за этот день уже начислены — можно
              поправить ответы
            </p>
          ) : isFuture ? (
            <p className="text-xs text-text-secondary">Этот день ещё впереди — отчёт можно будет заполнить после.</p>
          ) : tooLate ? (
            <p className="text-xs text-text-secondary">
              Очки начисляются за отчёт в течение {REPORT_REWARD_WINDOW_DAYS} дней — за этот день уже не начислятся,
              но отчёт сохранится.
            </p>
          ) : null}
        </div>

        {isGame ? (
          <>
            <Question title="Счёт">
              <ChipRow columns={3}>
                {(Object.keys(GAME_RESULT_LABELS) as GameResult[]).map((value) => (
                  <Chip key={value} selected={result === value} onClick={() => setResult(value)}>
                    {GAME_RESULT_LABELS[value]}
                  </Chip>
                ))}
              </ChipRow>
            </Question>

            {!isGoalie && (
              <Question title="Ваши моменты" aside={inTeam ? 'видно тренеру команды' : undefined}>
                <div className="flex flex-col gap-1.5">
                  {(['goals', 'assists', 'shots'] as Counter[]).map((key) => (
                    <CounterRow
                      key={key}
                      label={{ goals: 'Голы', assists: 'Передачи', shots: 'Броски в створ' }[key]}
                      value={counters[key]}
                      max={COUNTER_MAX[key]}
                      onChange={(value) => setCounters((current) => ({ ...current, [key]: value }))}
                    />
                  ))}
                </div>
              </Question>
            )}

            <Question
              title="Оцените свою игру"
              aside={
                <span className="flex items-center gap-1">
                  <i className="ti ti-lock" aria-hidden="true" />
                  только вам и ИИ-тренеру
                </span>
              }
            >
              <ChipRow columns={5}>
                {[1, 2, 3, 4, 5].map((value) => (
                  <Chip key={value} selected={selfRating === value} onClick={() => setSelfRating(value)}>
                    {value}
                  </Chip>
                ))}
              </ChipRow>
            </Question>

            <Question title="Над чем поработать" aside="можно несколько">
              <ChipRow columns={2}>
                {(Object.keys(GAME_WORK_ON_LABELS) as GameWorkOn[]).map((value) => (
                  <Chip key={value} selected={workOn.includes(value)} onClick={() => setWorkOn(toggle(workOn, value))}>
                    {GAME_WORK_ON_LABELS[value]}
                  </Chip>
                ))}
              </ChipRow>
            </Question>
          </>
        ) : (
          <>
            <Question title="Сколько были на льду">
              <ChipRow columns={4}>
                {ICE_DURATIONS.map((value, index) => (
                  <Chip key={value} selected={duration === value} onClick={() => setDuration(value)}>
                    {index === ICE_DURATIONS.length - 1 ? `${value}+` : `${value} мин`}
                  </Chip>
                ))}
              </ChipRow>
            </Question>

            <Question title="Насколько было тяжело">
              <ChipRow columns={3}>
                {(Object.keys(ICE_EFFORT_LABELS) as IceEffort[]).map((value) => (
                  <Chip key={value} selected={effort === value} onClick={() => setEffort(value)}>
                    {ICE_EFFORT_LABELS[value]}
                  </Chip>
                ))}
              </ChipRow>
            </Question>

            {focus !== null && (
              <Question title={`Фокус: ${focus.title.charAt(0).toLowerCase()}${focus.title.slice(1)}`}>
                <ChipRow columns={3}>
                  {(Object.keys(FOCUS_RESULT_LABELS) as FocusResult[]).map((value) => (
                    <Chip key={value} selected={focusResult === value} onClick={() => setFocusResult(value)}>
                      {FOCUS_RESULT_LABELS[value]}
                    </Chip>
                  ))}
                </ChipRow>
              </Question>
            )}

            <Question title="Что шло лучше всего" aside="можно несколько">
              <ChipRow columns={2}>
                {(Object.keys(ICE_HIGHLIGHT_LABELS) as IceHighlight[]).map((value) => (
                  <Chip
                    key={value}
                    selected={highlights.includes(value)}
                    onClick={() => setHighlights(toggle(highlights, value))}
                  >
                    {ICE_HIGHLIGHT_LABELS[value]}
                  </Chip>
                ))}
              </ChipRow>
            </Question>
          </>
        )}

        <label className="mt-5 flex flex-col gap-1.5">
          <span className="text-sm text-text-secondary">Заметка в дневник — по желанию</span>
          {/* text-base (16px), not text-sm: iOS zooms the page on focusing
              any input under 16px. */}
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={3}
            maxLength={2000}
            placeholder={isGame ? 'Что запомнилось в игре' : 'Что запомнилось, что сказал тренер'}
            className="w-full resize-none rounded-xl border border-white/10 bg-dark-card px-3 py-2.5 text-base text-text-primary outline-none placeholder:text-text-secondary/70 focus:border-accent-ice/50"
          />
        </label>

        {isGame && inTeam && (
          <label className="mt-2 flex min-h-11 items-center justify-between gap-3 text-sm text-text-secondary">
            Показывать оценку тренеру команды
            <input
              type="checkbox"
              checked={shareWithCoach}
              onChange={(event) => setShareWithCoach(event.target.checked)}
              className="h-5 w-5 accent-accent-ice"
            />
          </label>
        )}

        <div className="mt-auto flex flex-col gap-2 pt-6">
          <FormError message={saveError} />
          <Button onClick={submitReport} disabled={!complete || isSaving || isFuture} className="w-full">
            {isSaving ? 'Сохраняем...' : 'Сохранить'}
          </Button>
          <div className="flex items-center justify-between text-sm">
            <button
              type="button"
              onClick={() => void submit({ skipped: true })}
              disabled={isSaving || isFuture}
              className="min-h-11 text-text-secondary transition-colors hover:text-text-primary disabled:opacity-50"
            >
              {isGame ? 'Не играл' : 'Не был на льду'}
            </button>
            <button
              type="button"
              onClick={() => navigate('/diary')}
              className="min-h-11 text-accent-ice transition-colors hover:text-text-primary"
            >
              Все записи
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

function Question({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-5 flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
        {aside !== undefined && <span className="text-xs text-text-secondary">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

const GRID_COLUMNS: Record<2 | 3 | 4 | 5, string> = {
  2: 'grid-cols-2',
  3: 'grid-cols-3',
  4: 'grid-cols-4',
  5: 'grid-cols-5',
}

function ChipRow({ columns, children }: { columns: 2 | 3 | 4 | 5; children: ReactNode }) {
  return <div className={`grid gap-1.5 ${GRID_COLUMNS[columns]}`}>{children}</div>
}

function Chip({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`min-h-11 rounded-xl border px-2 text-sm transition-colors ${
        selected
          ? 'border-accent-ice bg-accent-ice font-semibold text-dark-bg'
          : 'border-white/10 bg-dark-card text-text-primary hover:border-white/25'
      }`}
    >
      {children}
    </button>
  )
}

function CounterRow({
  label,
  value,
  max,
  onChange,
}: {
  label: string
  value: number
  max: number
  onChange: (value: number) => void
}) {
  return (
    <div className="flex items-center justify-between rounded-xl bg-dark-card py-1.5 pl-4 pr-1.5">
      <span className="text-sm text-text-primary">{label}</span>
      <span className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={() => onChange(Math.max(0, value - 1))}
          disabled={value === 0}
          aria-label={`${label}: меньше`}
          className="flex h-11 w-11 items-center justify-center rounded-lg border border-white/10 text-lg text-text-primary disabled:opacity-40"
        >
          <i className="ti ti-minus" aria-hidden="true" />
        </button>
        <span className="w-8 text-center font-display text-xl font-semibold text-text-primary">{value}</span>
        <button
          type="button"
          onClick={() => onChange(Math.min(max, value + 1))}
          disabled={value === max}
          aria-label={`${label}: больше`}
          className="flex h-11 w-11 items-center justify-center rounded-lg border border-white/10 text-lg text-text-primary disabled:opacity-40"
        >
          <i className="ti ti-plus" aria-hidden="true" />
        </button>
      </span>
    </div>
  )
}
