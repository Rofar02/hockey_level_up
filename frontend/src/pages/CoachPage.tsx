import { useEffect, useRef, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { PremiumGate } from '../components/ui/PremiumGate'
import { ShieldIcon } from '../components/ui/ShieldIcon'
import * as coachChatApi from '../api/coachChat'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { CoachChatMessageRead } from '../types/coachChat'

const CARD_BORDER = 'border-t border-[rgba(215,239,255,0.35)]'

const COACH_PREMIUM_GATE_DESCRIPTION =
  'С премиум-подпиской откроется персональный AI-тренер: задавайте вопросы о своих тренировках и ' +
  'получайте советы с учётом ваших реальных характеристик и прогресса.'

export function CoachPage() {
  const { user, accessToken } = useAuth()
  const hasPremium = user?.has_premium === true

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            Тренер
            <span className="rounded-full border border-accent-ice/30 bg-accent-ice/10 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-accent-ice">
              AI
            </span>
          </h1>
        </div>

        {hasPremium && accessToken !== null ? (
          <CoachChatContent accessToken={accessToken} />
        ) : (
          <PremiumGate
            title="Персональный AI-тренер — часть премиум-подписки"
            description={COACH_PREMIUM_GATE_DESCRIPTION}
          />
        )}
      </div>
    </div>
  )
}

// Shown once a real 503 comes back from the backend (see CoachChatContent
// below) -- the feature is technically off (no Anthropic key configured
// yet), a different state from "no premium access" above.
function ComingSoonCard() {
  return (
    <div
      className={`flex flex-col items-center gap-4 rounded-md ${CARD_BORDER} bg-dark-card p-8 text-center`}
    >
      <i className="ti ti-message-chatbot text-4xl text-accent-ice" aria-hidden="true" />
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold text-[#F5F7FA]">Скоро</h2>
        <p className="text-sm text-[#8A94A6]">
          Персональный AI-тренер уже почти готов — совсем скоро сможете задавать ему вопросы о своих
          тренировках.
        </p>
      </div>
    </div>
  )
}

function CoachChatContent({ accessToken }: { accessToken: string }) {
  const [messages, setMessages] = useState<CoachChatMessageRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  // Optimistic by default: we only learn the feature is switched off (503)
  // from an actual failed send attempt, since GET history has no reason to
  // reflect that -- old conversations should stay readable even if the key
  // is later unset. Once we learn it, the input disappears for the rest of
  // this page visit.
  const [unavailable, setUnavailable] = useState(false)
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    coachChatApi
      .getCoachChatHistory(accessToken)
      .then((result) => {
        if (!cancelled) {
          setMessages(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(
            err instanceof ApiError ? err.message : 'Не удалось загрузить историю переписки.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [messages])

  if (unavailable) {
    return <ComingSoonCard />
  }

  async function submitMessage() {
    const trimmed = input.trim()
    if (trimmed === '' || isSending) {
      return
    }

    const pendingUserMessage: CoachChatMessageRead = {
      id: `pending-${Date.now()}`,
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...(prev ?? []), pendingUserMessage])
    setInput('')
    setIsSending(true)
    setSendError(null)

    try {
      const result = await coachChatApi.sendCoachChatMessage(trimmed, accessToken)
      setMessages((prev) => [...(prev ?? []), result.reply])
    } catch (err) {
      // The optimistic user bubble was never actually saved -- drop it.
      setMessages((prev) => (prev ?? []).filter((message) => message.id !== pendingUserMessage.id))
      if (err instanceof ApiError && err.status === 503) {
        setUnavailable(true)
      } else {
        setSendError(err instanceof ApiError ? err.message : 'Не удалось отправить сообщение.')
        setInput(trimmed)
      }
    } finally {
      setIsSending(false)
    }
  }

  return (
    <div className={`flex flex-col gap-3 rounded-md ${CARD_BORDER} bg-dark-card p-4`}>
      <FormError message={loadError} />
      <div className="flex max-h-[60vh] min-h-[240px] flex-col gap-3 overflow-y-auto">
        {messages === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}
        {messages !== null && messages.length === 0 && (
          <p className="py-12 text-center text-sm text-[#8A94A6]">
            Задайте тренеру вопрос о своих тренировках, чтобы начать разговор.
          </p>
        )}
        {messages?.map((message) => <ChatBubble key={message.id} message={message} />)}
        <div ref={bottomRef} />
      </div>

      <FormError message={sendError} />

      <form
        onSubmit={(event) => {
          event.preventDefault()
          void submitMessage()
        }}
        className="flex items-end gap-2"
      >
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              void submitMessage()
            }
          }}
          placeholder="Спросите тренера о тренировках..."
          rows={2}
          maxLength={4000}
          disabled={isSending}
          className="flex-1 resize-none rounded border border-white/10 bg-dark-bg px-3 py-2 text-sm text-text-primary placeholder:text-text-secondary/60 focus:border-accent-ice focus:outline-none"
        />
        <Button type="submit" isLoading={isSending} disabled={input.trim() === ''}>
          Отправить
        </Button>
      </form>
    </div>
  )
}

function ChatBubble({ message }: { message: CoachChatMessageRead }) {
  const isUser = message.role === 'user'
  return (
    <div className={`flex items-end gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <div className="flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full border border-accent-ice/30 bg-accent-ice/10">
          <ShieldIcon size={14} />
        </div>
      )}
      <div
        className={`max-w-[85%] whitespace-pre-wrap rounded-md px-3 py-2 text-sm text-[#F5F7FA] ${
          isUser ? 'bg-accent-ice/10' : 'bg-white/5'
        }`}
      >
        {message.content}
      </div>
    </div>
  )
}
