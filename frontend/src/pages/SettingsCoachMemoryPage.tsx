import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as coachChatApi from '../api/coachChat'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { useAuth } from '../hooks/useAuth'
import type { CoachMemoryFactRead } from '../types/coachChat'

// "Что помнит тренер" (2026-10-04): the coach's notes about the player,
// distilled from older chat messages (CoachMemoryService, premium). Seeing
// and deleting them is open to everyone -- it's the player's own data.

export function SettingsCoachMemoryPage() {
  const { user, accessToken } = useAuth()
  const hasPremium = user?.has_premium === true
  const [facts, setFacts] = useState<CoachMemoryFactRead[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [isConfirmingForget, setIsConfirmingForget] = useState(false)
  const [isForgetting, setIsForgetting] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    coachChatApi
      .getCoachMemory(accessToken)
      .then((result) => !cancelled && setFacts(result))
      .catch(() => {
        if (!cancelled) {
          setFacts([])
          setError('Не удалось загрузить заметки тренера.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function handleDelete(factId: string) {
    if (accessToken === null) {
      return
    }
    setBusyId(factId)
    setError(null)
    try {
      await coachChatApi.deleteCoachMemoryFact(factId, accessToken)
      setFacts((current) => (current ?? []).filter((fact) => fact.id !== factId))
    } catch {
      setError('Не удалось удалить заметку. Попробуй ещё раз.')
    } finally {
      setBusyId(null)
    }
  }

  async function handleForgetAll() {
    if (accessToken === null) {
      return
    }
    setIsForgetting(true)
    setError(null)
    try {
      await coachChatApi.forgetCoachMemory(accessToken)
      setFacts([])
      setIsConfirmingForget(false)
    } catch {
      setError('Не удалось очистить заметки. Попробуй ещё раз.')
    } finally {
      setIsForgetting(false)
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 pb-32 pt-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Что помнит тренер</h1>
          <p className="text-sm leading-relaxed text-text-secondary">
            Тренер ведёт короткие заметки о тебе из прошлых разговоров: цели, график, инвентарь, что нравится и что
            нет. Так ему не нужно переспрашивать. Удали всё, что не хочешь, чтобы он помнил.
          </p>
        </div>

        <FormError message={error} />

        {facts === null ? (
          <p className="text-sm text-text-secondary">Загрузка…</p>
        ) : facts.length === 0 ? (
          <div className={`flex flex-col items-center gap-3 p-6 text-center ${CARD_CLASS}`}>
            <i className="ti ti-brain text-3xl text-accent-ice" aria-hidden="true" />
            {hasPremium ? (
              <p className="text-sm text-text-secondary">
                Пока заметок нет. Они появятся после нескольких разговоров с тренером.
              </p>
            ) : (
              <>
                <p className="text-sm text-text-secondary">Заметки тренера — часть премиум-подписки.</p>
                <Link to="/premium" className="text-sm font-medium text-accent-ice hover:text-text-primary">
                  Узнать про премиум
                </Link>
              </>
            )}
          </div>
        ) : (
          <>
            {!hasPremium && (
              <p className="text-sm text-text-secondary">Без премиум-подписки тренер эти заметки не использует.</p>
            )}
            <ul className={`flex flex-col ${CARD_CLASS}`}>
              {facts.map((fact) => (
                <li
                  key={fact.id}
                  className="flex items-start gap-3 border-b border-white/5 px-4 py-3 last:border-b-0"
                >
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-ice" aria-hidden="true" />
                  <span className="flex-1 text-[15px] leading-snug">{fact.text}</span>
                  <button
                    type="button"
                    aria-label="Удалить заметку"
                    disabled={busyId === fact.id}
                    onClick={() => void handleDelete(fact.id)}
                    className="-mr-2 flex h-11 w-11 shrink-0 items-center justify-center rounded text-text-secondary transition-colors hover:text-accent-persimmon disabled:opacity-50"
                  >
                    <i className="ti ti-trash text-lg" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>

            {isConfirmingForget ? (
              <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
                <p className="text-sm">Тренер забудет всё, что знает о тебе из прошлых разговоров. Точно?</p>
                <div className="flex gap-2">
                  <Button type="button" className="flex-1" isLoading={isForgetting} onClick={() => void handleForgetAll()}>
                    Забыть всё
                  </Button>
                  <Button
                    type="button"
                    variant="neutral"
                    className="flex-1"
                    disabled={isForgetting}
                    onClick={() => setIsConfirmingForget(false)}
                  >
                    Отмена
                  </Button>
                </div>
              </div>
            ) : (
              <Button type="button" variant="neutral" onClick={() => setIsConfirmingForget(true)}>
                Забыть всё
              </Button>
            )}
          </>
        )}
      </div>
    </div>
  )
}
