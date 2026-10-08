import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as authApi from '../api/auth'
import { apiPostAuth } from '../api/client'
import { useAuth } from '../hooks/useAuth'

interface OnboardingTask {
  id: string
  title: string
  hint: string
  xp: number
  to: string
  done: boolean
}

interface OnboardingRead {
  visible: boolean
  tasks: OnboardingTask[]
  newly_done: string[]
  xp_awarded: number
  finish_bonus_xp: number
}

// "Путь новичка" (2026-10-08): the one main loop as a short checklist on the
// home screen -- plan, workout, report, coach, team -- each step paid in XP
// the first time it's actually done (the server reads it off what the
// player did; see app/services/onboarding_service.py). The next undone step
// is highlighted and opens where it's done. Gone once everything is done
// or the player hides it.
export function OnboardingCard() {
  const { accessToken, updateUser } = useAuth()
  const navigate = useNavigate()
  const [state, setState] = useState<OnboardingRead | null>(null)
  const [justEarned, setJustEarned] = useState(0)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    apiPostAuth<OnboardingRead>('/users/me/onboarding/sync', {}, accessToken)
      .then(async (result) => {
        if (cancelled) {
          return
        }
        setState(result)
        if (result.xp_awarded > 0) {
          setJustEarned(result.xp_awarded)
          // The XP bar above reads the user -- refresh it.
          updateUser(await authApi.getCurrentUser(accessToken))
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken, updateUser])

  if (state === null || !state.visible) {
    return null
  }

  const doneCount = state.tasks.filter((task) => task.done).length
  const next = state.tasks.find((task) => !task.done)

  function hide() {
    if (accessToken !== null) {
      void apiPostAuth('/users/me/onboarding/dismiss', {}, accessToken).catch(() => {})
    }
    setState((current) => (current !== null ? { ...current, visible: false } : current))
  }

  return (
    <section className="rounded-2xl border border-accent-ice/20 bg-gradient-to-b from-[#1B2438] to-dark-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-persimmon">Путь новичка</p>
          <h2 className="mt-1 text-lg font-semibold leading-snug">Освойте IceLevel за неделю</h2>
        </div>
        <span className="font-display text-2xl font-semibold text-accent-ice">
          {doneCount}
          <span className="text-base text-text-secondary"> / {state.tasks.length}</span>
        </span>
      </div>
      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-accent-ice transition-[width] duration-500"
          style={{ width: `${(doneCount / state.tasks.length) * 100}%` }}
        />
      </div>
      {justEarned > 0 && (
        <p className="mt-3 rounded-lg bg-accent-persimmon/10 px-3 py-2 text-sm text-accent-persimmon">
          Засчитано: +{justEarned} XP
        </p>
      )}

      <ul className="mt-2 flex flex-col">
        {state.tasks.map((task) => {
          const isNext = next?.id === task.id
          return (
            <li key={task.id}>
              <button
                type="button"
                onClick={() => !task.done && navigate(task.to)}
                disabled={task.done}
                className={`flex min-h-12 w-full items-center gap-3 rounded-xl px-2.5 py-1.5 text-left transition-colors ${
                  isNext ? 'border border-accent-persimmon/35 bg-accent-persimmon/10' : 'hover:bg-white/[0.03]'
                } ${task.done ? 'opacity-55' : ''}`}
              >
                {task.done ? (
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-ice text-dark-bg">
                    <i className="ti ti-check text-sm" aria-hidden="true" />
                  </span>
                ) : (
                  <span
                    className={`h-6 w-6 shrink-0 rounded-full border-2 ${isNext ? 'border-accent-persimmon' : 'border-white/20'}`}
                  />
                )}
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className={`text-sm ${isNext ? 'font-semibold' : ''} ${task.done ? 'line-through' : ''}`}>
                    {task.title}
                  </span>
                  {isNext && <span className="text-xs text-text-secondary">{task.hint}</span>}
                </span>
                {!task.done && (
                  <span
                    className={`whitespace-nowrap text-xs font-semibold ${isNext ? 'text-accent-persimmon' : 'text-text-secondary'}`}
                  >
                    +{task.xp} XP
                  </span>
                )}
              </button>
            </li>
          )
        })}
      </ul>

      <div className="mt-1 flex items-center justify-between">
        <span className="text-xs text-text-secondary">Пройдёте все — ещё +{state.finish_bonus_xp} XP</span>
        <button
          type="button"
          onClick={hide}
          className="min-h-11 px-1 text-xs text-text-secondary transition-colors hover:text-text-primary"
        >
          Скрыть
        </button>
      </div>
    </section>
  )
}
