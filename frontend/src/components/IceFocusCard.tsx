import { useEffect, useState } from 'react'
import * as trainingDiaryApi from '../api/trainingDiary'
import { useAuth } from '../hooks/useAuth'
import type { IceFocusRead } from '../types/trainingDiary'

// The focus of the day on an ice day's home card (2026-10-08): one thing to
// pay attention to during a practice the team coach runs, not the app. The
// report afterwards asks whether it worked. Renders nothing for a game day
// or while/if the focus doesn't load -- it's a hint, never a blocker.
export function IceFocusCard({ trainingSessionId }: { trainingSessionId: string }) {
  const { accessToken } = useAuth()
  const [focus, setFocus] = useState<IceFocusRead | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    trainingDiaryApi
      .getIceFocus(trainingSessionId, accessToken)
      .then((result) => {
        if (!cancelled) {
          setFocus(result)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken, trainingSessionId])

  if (focus === null) {
    return null
  }
  return (
    <div className="rounded-2xl border border-accent-persimmon/40 bg-gradient-to-br from-[#22304A] to-dark-card p-4">
      <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-accent-persimmon">Фокус дня</p>
      <p className="mt-1.5 text-lg font-semibold leading-snug text-text-primary">{focus.title}</p>
      <ul className="mt-2 flex flex-col gap-1">
        {focus.cues.map((cue) => (
          <li key={cue} className="flex gap-2 text-sm leading-snug text-[#B7C2D4]">
            <span className="text-accent-persimmon" aria-hidden="true">
              —
            </span>
            {cue}
          </li>
        ))}
      </ul>
      <p className="mt-2.5 text-xs text-text-secondary">{focus.reason}</p>
    </div>
  )
}
