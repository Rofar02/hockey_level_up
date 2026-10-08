import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as teamEventsApi from '../../api/teamEvents'
import { useAuth } from '../../hooks/useAuth'

function readFlag(key: string): boolean {
  try {
    return window.localStorage.getItem(key) !== null
  } catch {
    return false
  }
}

function writeFlag(key: string) {
  try {
    window.localStorage.setItem(key, '1')
  } catch {
    // Private mode etc. -- hidden for this visit only.
  }
}

const PLAYER_POINTS: { icon: string; title: string; text: string }[] = [
  { icon: 'ti-calendar', title: 'Расписание встаёт в ваш план', text: 'Отметьтесь «Иду» — командный лёд или игра заменят то, что было в этот день.' },
  { icon: 'ti-presentation', title: 'План тренировки — заранее', text: 'Упражнения и схемы на площадке от тренера. Схемы проигрываются по кадрам.' },
  { icon: 'ti-list-numbers', title: 'Ваше звено', text: 'Тренер публикует составы — вы видите, с кем играете.' },
  { icon: 'ti-trophy', title: 'Рейтинг и статистика', text: 'После игры отметьте голы и передачи — они попадут к тренеру.' },
]

// A player's first look at their team (2026-10-08): what now works by
// itself. Shown until closed, per team, on this device.
export function TeamPlayerIntroCard({ teamId }: { teamId: string }) {
  const key = `team-intro-player:${teamId}`
  const [hidden, setHidden] = useState(() => readFlag(key))
  if (hidden) {
    return null
  }
  return (
    <section className="rounded-2xl border border-accent-ice/20 bg-dark-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-persimmon">Вы в команде</p>
          <p className="mt-1 text-base font-semibold">Вот что теперь работает само</p>
        </div>
        <button
          type="button"
          onClick={() => {
            writeFlag(key)
            setHidden(true)
          }}
          aria-label="Скрыть"
          className="-mr-2 -mt-2 flex h-11 w-11 items-center justify-center text-text-secondary hover:text-text-primary"
        >
          <i className="ti ti-x" aria-hidden="true" />
        </button>
      </div>
      <ul className="mt-2 flex flex-col gap-3">
        {PLAYER_POINTS.map((point) => (
          <li key={point.title} className="flex gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-ice/10">
              <i className={`ti ${point.icon} text-lg text-accent-ice`} aria-hidden="true" />
            </span>
            <span className="flex flex-col">
              <span className="text-sm font-semibold">{point.title}</span>
              <span className="text-xs leading-relaxed text-text-secondary">{point.text}</span>
            </span>
          </li>
        ))}
      </ul>
      <Link to="/guide/team_player" className="mt-3 flex min-h-11 items-center gap-1.5 text-sm text-accent-ice">
        Подробнее о команде
        <i className="ti ti-arrow-right" aria-hidden="true" />
      </Link>
    </section>
  )
}

interface SetupStep {
  title: string
  hint: string
  done: boolean
  to: string | null
}

// The captain's setup in four steps (2026-10-08), each read off the team's
// real state, the next one highlighted. Gone once all four are done or the
// captain hides it (per team, on this device).
export function TeamCaptainSetupCard({ teamId, memberCount }: { teamId: string; memberCount: number }) {
  const { accessToken } = useAuth()
  const key = `team-setup-hidden:${teamId}`
  const [hidden, setHidden] = useState(() => readFlag(key))
  const [state, setState] = useState<{ templates: boolean; board: boolean; diagram: boolean } | null>(null)

  useEffect(() => {
    if (accessToken === null || hidden) {
      return
    }
    let cancelled = false
    Promise.all([
      teamEventsApi.listTeamEvents(teamId, accessToken),
      teamEventsApi.listIceScheduleTemplates(teamId, accessToken),
    ])
      .then(([events, templates]) => {
        if (cancelled) {
          return
        }
        const drills = events.flatMap((event) => event.sections ?? []).flatMap((section) => section.drills)
        setState({
          templates: templates.length > 0,
          board: events.some((event) => event.board_status === 'published'),
          diagram: drills.some((drill) => drill.diagram !== null),
        })
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId, hidden])

  if (hidden || state === null) {
    return null
  }
  const steps: SetupStep[] = [
    { title: 'Пригласите игроков', hint: 'Отправьте код команды выше в общий чат', done: memberCount > 1, to: null },
    { title: 'Задайте расписание льда', hint: 'Один раз — повторяется каждую неделю', done: state.templates, to: `/teams/${teamId}/ice-schedule-templates` },
    { title: 'Соберите план тренировки', hint: 'Разделы и минуты — и опубликуйте', done: state.board, to: `/teams/${teamId}/events` },
    { title: 'Нарисуйте схему упражнения', hint: 'Игроки, катание, пасы, броски — по кадрам', done: state.diagram, to: `/teams/${teamId}/events` },
  ]
  if (steps.every((step) => step.done)) {
    return null
  }
  const next = steps.find((step) => !step.done)

  return (
    <section className="rounded-2xl border border-accent-ice/20 bg-dark-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-persimmon">
            Вы тренер команды
          </p>
          <p className="mt-1 text-base font-semibold">Настройка — {steps.filter((s) => s.done).length} из 4</p>
        </div>
        <button
          type="button"
          onClick={() => {
            writeFlag(key)
            setHidden(true)
          }}
          aria-label="Скрыть"
          className="-mr-2 -mt-2 flex h-11 w-11 items-center justify-center text-text-secondary hover:text-text-primary"
        >
          <i className="ti ti-x" aria-hidden="true" />
        </button>
      </div>
      <ol className="mt-2 flex flex-col gap-1.5">
        {steps.map((step, index) => {
          const isNext = step === next
          const body = (
            <>
              <span
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full font-display text-sm font-semibold ${
                  step.done
                    ? 'bg-accent-ice text-dark-bg'
                    : isNext
                      ? 'border-2 border-accent-persimmon text-accent-persimmon'
                      : 'border-2 border-white/20 text-text-secondary'
                }`}
              >
                {step.done ? <i className="ti ti-check text-sm" aria-hidden="true" /> : index + 1}
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className={`text-sm font-semibold ${step.done ? 'text-text-secondary line-through' : ''}`}>
                  {step.title}
                </span>
                {!step.done && <span className="text-xs text-text-secondary">{step.hint}</span>}
              </span>
              {step.to !== null && !step.done && (
                <i className="ti ti-chevron-right text-text-secondary" aria-hidden="true" />
              )}
            </>
          )
          const className = `flex min-h-14 items-center gap-3 rounded-xl px-3 py-1.5 ${
            isNext ? 'border border-accent-persimmon/40 bg-accent-persimmon/10' : 'bg-white/[0.02]'
          }`
          return (
            <li key={step.title}>
              {step.to !== null && !step.done ? (
                <Link to={step.to} className={className}>
                  {body}
                </Link>
              ) : (
                <div className={className}>{body}</div>
              )}
            </li>
          )
        })}
      </ol>
      <Link to="/guide/team_coach" className="mt-3 flex min-h-11 items-center gap-1.5 text-sm text-accent-ice">
        Как пользоваться доской и схемами
        <i className="ti ti-arrow-right" aria-hidden="true" />
      </Link>
    </section>
  )
}
