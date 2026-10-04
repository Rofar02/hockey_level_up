import { useEffect, useRef, useState } from 'react'
import * as feedbackApi from '../api/feedback'
import { ApiError } from '../api/client'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { useAuth } from '../hooks/useAuth'
import { FEEDBACK_KIND_LABELS } from '../types/feedback'
import type { FeedbackKind } from '../types/feedback'
import { recentRoutes } from '../utils/routeHistory'

// "Обратная связь" (2026-10-04): a bug report, an idea or anything else for
// the developer, with an optional screenshot. The page trail, browser,
// screen size and home-screen flag go along by themselves -- a bug report
// is far more useful with them, and the player doesn't have to know.

const KINDS: { value: FeedbackKind; icon: string; hint: string }[] = [
  { value: 'bug', icon: 'ti-bug', hint: 'Что-то сломалось или работает не так' },
  { value: 'idea', icon: 'ti-bulb', hint: 'Чего не хватает, что улучшить' },
  { value: 'other', icon: 'ti-message', hint: 'Всё остальное' },
]

const MAX_CHARS = 2000

function isStandalone(): boolean {
  const iosStandalone = (navigator as Navigator & { standalone?: boolean }).standalone === true
  return iosStandalone || window.matchMedia('(display-mode: standalone)').matches
}

export function FeedbackPage() {
  const { accessToken } = useAuth()
  const [kind, setKind] = useState<FeedbackKind>('bug')
  const [text, setText] = useState('')
  const [screenshot, setScreenshot] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isSending, setIsSending] = useState(false)
  const [isSent, setIsSent] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (screenshot === null) {
      setPreview(null)
      return
    }
    const url = URL.createObjectURL(screenshot)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [screenshot])

  async function handleSubmit() {
    if (accessToken === null) {
      return
    }
    setError(null)
    setIsSending(true)
    try {
      await feedbackApi.sendFeedback(
        {
          kind,
          text,
          page: recentRoutes(),
          userAgent: navigator.userAgent,
          screen: `${window.innerWidth}x${window.innerHeight} @${window.devicePixelRatio}`,
          standalone: isStandalone(),
          screenshot,
        },
        accessToken,
      )
      setIsSent(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить. Попробуй ещё раз.')
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 pb-32 pt-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Обратная связь</h1>
          <p className="text-sm leading-relaxed text-text-secondary">
            Нашёл ошибку или есть идея? Напиши — сообщение придёт напрямую разработчику.
          </p>
        </div>

        {isSent ? (
          <div className={`flex flex-col items-center gap-3 p-6 text-center ${CARD_CLASS}`}>
            <i className="ti ti-circle-check text-4xl text-accent-ice" aria-hidden="true" />
            <p className="text-[15px] font-semibold">Спасибо! Сообщение отправлено.</p>
            <p className="text-sm text-text-secondary">Мы читаем каждое — это правда помогает сделать приложение лучше.</p>
            <Button
              type="button"
              variant="neutral"
              onClick={() => {
                setIsSent(false)
                setText('')
                setScreenshot(null)
              }}
            >
              Написать ещё
            </Button>
          </div>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Тип сообщения">
              {KINDS.map((option) => {
                const isSelected = kind === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    onClick={() => setKind(option.value)}
                    className={`flex flex-col items-center gap-1.5 rounded-md border p-3 text-center transition-colors ${
                      isSelected ? 'border-accent-ice bg-accent-ice/10' : 'border-white/10 hover:border-white/20'
                    }`}
                  >
                    <i className={`ti ${option.icon} text-xl text-accent-ice`} aria-hidden="true" />
                    <span className="text-sm font-medium">{FEEDBACK_KIND_LABELS[option.value]}</span>
                  </button>
                )
              })}
            </div>
            <p className="-mt-3 text-xs text-text-secondary">{KINDS.find((option) => option.value === kind)?.hint}</p>

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium">Сообщение</span>
              <textarea
                value={text}
                onChange={(event) => setText(event.target.value.slice(0, MAX_CHARS))}
                rows={6}
                placeholder={
                  kind === 'bug'
                    ? 'Что делал и что пошло не так? Например: «написал тренеру, свернул приложение — пропало нижнее меню»'
                    : 'Расскажи подробнее…'
                }
                // text-base: anything under 16px makes iOS zoom into the field.
                className="resize-none rounded-md border border-white/10 bg-dark-bg px-3 py-2 text-base text-text-primary placeholder:text-text-secondary/60 focus:border-accent-ice focus:outline-none"
              />
              <span className="self-end text-[11px] text-text-secondary">
                {text.length}/{MAX_CHARS}
              </span>
            </label>

            <div className="flex flex-col gap-2">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(event) => setScreenshot(event.target.files?.[0] ?? null)}
              />
              {preview !== null ? (
                <div className={`flex items-center gap-3 p-3 ${CARD_CLASS}`}>
                  <img src={preview} alt="Скриншот" className="h-16 w-16 rounded object-cover" />
                  <span className="flex-1 text-sm text-text-secondary">Скриншот прикреплён</span>
                  <button
                    type="button"
                    aria-label="Убрать скриншот"
                    onClick={() => {
                      setScreenshot(null)
                      if (fileInputRef.current !== null) {
                        fileInputRef.current.value = ''
                      }
                    }}
                    className="flex h-11 w-11 items-center justify-center rounded text-text-secondary hover:text-accent-persimmon"
                  >
                    <i className="ti ti-trash text-lg" aria-hidden="true" />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex min-h-11 items-center justify-center gap-2 rounded-md border border-dashed border-white/20 text-sm text-text-secondary transition-colors hover:border-accent-ice/50 hover:text-text-primary"
                >
                  <i className="ti ti-photo-plus text-lg" aria-hidden="true" />
                  Прикрепить скриншот (необязательно)
                </button>
              )}
            </div>

            <FormError message={error} />
            <Button
              type="button"
              className="h-12 text-base font-bold"
              isLoading={isSending}
              disabled={text.trim().length < 5}
              onClick={() => void handleSubmit()}
            >
              Отправить
            </Button>
            <p className="text-center text-xs text-text-secondary">
              Вместе с сообщением отправится, на каком экране ты был и с какого устройства — это помогает найти ошибку.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
