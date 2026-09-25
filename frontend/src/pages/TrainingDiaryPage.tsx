import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import * as scheduleApi from '../api/schedule'
import * as trainingDiaryApi from '../api/trainingDiary'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { DAY_SESSION_TYPE_LABELS, SESSION_TYPE_COLORS, SESSION_TYPE_ICONS } from '../types/schedule'
import type { DayPlanRead } from '../types/schedule'
import { parseIsoDate } from '../utils/date'

const AUTOSAVE_DELAY_MS = 700
const SAVED_FADE_MS = 2200

// Full-screen notebook for an ON_ICE/GAME session's diary entry (2026-09-21
// redesign) -- reached from TodayCard's "Заполнить дневник" and from
// SessionCompleteModal's "Записать в дневник". Replaces the old
// TrainingDiaryCard that sat at the bottom of TrainingSessionPage, under the
// whole finished warmup list, which read as an afterthought stuck onto a
// workout history rather than a place to write. Deliberately shows nothing
// about the session's exercises: the diary is the player's own words about
// what happened, not a recap of what the app already knows. BottomNav is
// hidden for this route too (see ProtectedRoute) so the notebook really is
// the whole screen.
//
// Saving: autosave AUTOSAVE_DELAY_MS after the player stops typing (same
// idea as any note app), flushed immediately on "Готово"/back/unmount so the
// last few keystrokes are never lost to a still-pending debounce. A diary
// entry row existing at all -- even with note=null -- is what marks
// TodayCard's diary step done (see has_diary_entry's docstring in
// app/schemas/schedule.py), so "Готово"/"Не буду писать сегодня" always
// write a row, while plain back-navigation without typing anything doesn't.
export function TrainingDiaryPage() {
  const { dayPlanId } = useParams<{ dayPlanId: string }>()
  const { accessToken } = useAuth()
  const navigate = useNavigate()

  const [day, setDay] = useState<DayPlanRead | null>(null)
  const [trainingSessionId, setTrainingSessionId] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoaded, setIsLoaded] = useState(false)
  const [note, setNote] = useState('')
  const [phase, setPhase] = useState<'idle' | 'saving' | 'saved'>('idle')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isFinishing, setIsFinishing] = useState(false)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Latest value the debounce timer (or the unmount flush) would save --
  // a ref rather than reading `note` state, since the timer callback and the
  // unmount cleanup both close over stale renders.
  const pendingNoteRef = useRef<string | null>(null)

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
        if (
          session == null
          || (foundDay.session_type !== 'on_ice' && foundDay.session_type !== 'game')
        ) {
          if (!cancelled) {
            setLoadError('Дневник для этой тренировки недоступен.')
          }
          return
        }
        // Best-effort -- worst case the notebook just starts empty instead of
        // pre-filled with whatever was saved before.
        const entry = await trainingDiaryApi.getDiaryEntry(session.id, accessToken).catch(() => null)
        if (cancelled) {
          return
        }
        setDay(foundDay)
        setTrainingSessionId(session.id)
        setNote(entry?.note ?? '')
        setIsLoaded(true)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(
            err instanceof ApiError && err.status === 404
              ? 'Дневник для этой тренировки недоступен.'
              : 'Не удалось загрузить дневник. Попробуйте ещё раз.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, dayPlanId])

  // Only once the entry has loaded (not just the day): focusing earlier would
  // let the player start typing into a box that the load then overwrites.
  useEffect(() => {
    if (isLoaded) {
      textareaRef.current?.focus()
    }
  }, [isLoaded])

  // Leaving by any route (browser back, tab close aside) must not drop a
  // debounce that hasn't fired yet -- fire the save right now instead of
  // just clearing the timer.
  useEffect(() => {
    return () => {
      if (fadeTimerRef.current !== null) {
        clearTimeout(fadeTimerRef.current)
      }
      if (saveTimerRef.current !== null) {
        clearTimeout(saveTimerRef.current)
        saveTimerRef.current = null
        if (accessToken !== null && trainingSessionId !== null) {
          void trainingDiaryApi
            .saveDiaryEntry(trainingSessionId, { note: pendingNoteRef.current }, accessToken)
            .catch(() => {
              // Nowhere left to show it -- the page is already gone.
            })
        }
      }
    }
  }, [accessToken, trainingSessionId])

  async function persistNote(noteValue: string | null): Promise<boolean> {
    if (accessToken === null || trainingSessionId === null) {
      return false
    }
    setSaveError(null)
    try {
      await trainingDiaryApi.saveDiaryEntry(trainingSessionId, { note: noteValue }, accessToken)
      setPhase('saved')
      if (fadeTimerRef.current !== null) {
        clearTimeout(fadeTimerRef.current)
      }
      fadeTimerRef.current = setTimeout(() => setPhase('idle'), SAVED_FADE_MS)
      return true
    } catch (err) {
      setPhase('idle')
      setSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить запись.')
      return false
    }
  }

  function handleNoteChange(value: string) {
    setNote(value)
    setPhase('saving')
    const noteValue = value.trim() === '' ? null : value
    pendingNoteRef.current = noteValue
    if (saveTimerRef.current !== null) {
      clearTimeout(saveTimerRef.current)
    }
    if (fadeTimerRef.current !== null) {
      clearTimeout(fadeTimerRef.current)
    }
    saveTimerRef.current = setTimeout(() => {
      saveTimerRef.current = null
      void persistNote(noteValue)
    }, AUTOSAVE_DELAY_MS)
  }

  // Saves whatever is in the box right now and, only if that succeeded,
  // leaves -- a failed save keeps the player here with the error showing and
  // their text intact, rather than silently losing it on the way out.
  // `force` writes a row even with nothing typed (Готово / "Не буду писать").
  async function saveAndLeave(force: boolean, noteValue: string | null) {
    if (saveTimerRef.current === null && !force) {
      navigate('/', { replace: true })
      return
    }
    if (saveTimerRef.current !== null) {
      clearTimeout(saveTimerRef.current)
      saveTimerRef.current = null
    }
    setIsFinishing(true)
    setPhase('saving')
    const saved = await persistNote(noteValue)
    if (saved) {
      navigate('/', { replace: true })
    } else {
      setIsFinishing(false)
    }
  }

  const currentNoteValue = note.trim() === '' ? null : note
  const isEmpty = currentNoteValue === null

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

  if (!isLoaded || day === null) {
    return (
      <div className="relative flex min-h-svh items-center justify-center overflow-hidden">
        <IceGlowBackground />
        <p className="relative z-[1] text-sm text-text-secondary">Загрузка...</p>
      </div>
    )
  }

  const dateLabel = parseIsoDate(day.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })

  return (
    <div className="relative flex min-h-svh flex-col overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex w-full max-w-2xl flex-1 flex-col px-5 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-[calc(1.25rem+env(safe-area-inset-top))]">
        <header className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => void saveAndLeave(false, currentNoteValue)}
            disabled={isFinishing}
            aria-label="Назад"
            className="-ml-2 flex h-10 w-10 items-center justify-center rounded-full text-text-secondary transition-colors hover:text-text-primary disabled:opacity-50"
          >
            <i className="ti ti-chevron-left text-2xl" aria-hidden="true" />
          </button>
          <span
            className={`flex items-center gap-1.5 text-xs transition-opacity duration-500 ${
              phase === 'idle' ? 'opacity-0' : 'opacity-100'
            }`}
          >
            {phase === 'saving' && (
              <>
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-text-secondary" />
                <span className="text-text-secondary">Сохраняем...</span>
              </>
            )}
            {phase === 'saved' && (
              <>
                <i className="ti ti-check text-accent-ice" aria-hidden="true" />
                <span className="text-accent-ice">Сохранено</span>
              </>
            )}
          </span>
        </header>

        <div className="mt-2 flex flex-col gap-1">
          <span className={`flex items-center gap-1.5 text-sm ${SESSION_TYPE_COLORS[day.session_type]}`}>
            <i className={`ti ${SESSION_TYPE_ICONS[day.session_type]}`} aria-hidden="true" />
            {DAY_SESSION_TYPE_LABELS[day.session_type]} · {dateLabel}
          </span>
          <h1 className="font-display text-2xl font-semibold text-text-primary">Как прошло?</h1>
        </div>

        {/* Ruled notebook paper, tinted to the app's persimmon accent. The
            28px line pitch matches text-base + leading-7 exactly so text sits
            on the lines; bg-local keeps the rules scrolling with the text
            instead of staying pinned to the box. text-base (16px), not
            text-sm, on purpose: iOS Safari zooms the page on focusing any
            input under 16px, which would break this "full screen" feel. */}
        <textarea
          ref={textareaRef}
          value={note}
          onChange={(event) => handleNoteChange(event.target.value)}
          placeholder="Что получилось, а что нет? Как самочувствие, что запомнилось..."
          maxLength={2000}
          className="mt-4 min-h-64 w-full flex-1 resize-none border-none bg-transparent bg-[repeating-linear-gradient(to_bottom,transparent,transparent_27px,rgba(255,92,52,0.16)_28px)] bg-local text-base leading-7 text-text-primary outline-none placeholder:italic placeholder:text-text-secondary/70"
        />

        <div className="mt-4 flex flex-col gap-3">
          <FormError message={saveError} />
          <Button onClick={() => void saveAndLeave(true, currentNoteValue)} disabled={isFinishing} className="w-full">
            Готово
          </Button>
          <div className="flex items-center justify-between text-xs">
            {isEmpty ? (
              <button
                type="button"
                onClick={() => void saveAndLeave(true, null)}
                disabled={isFinishing}
                className="text-text-secondary underline decoration-dotted underline-offset-2 transition-colors hover:text-text-primary disabled:opacity-50"
              >
                Не буду писать сегодня
              </button>
            ) : (
              <span />
            )}
            <button
              type="button"
              onClick={() => navigate('/diary')}
              className="text-accent-ice underline decoration-dotted underline-offset-2 transition-colors hover:text-text-primary"
            >
              Все записи
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
