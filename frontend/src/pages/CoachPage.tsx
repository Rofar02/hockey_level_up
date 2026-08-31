import { useEffect, useRef, useState } from 'react'
import { CoachPersonalityIntroModal } from '../components/CoachPersonalityIntroModal'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { PremiumGate } from '../components/ui/PremiumGate'
import { ShieldIcon } from '../components/ui/ShieldIcon'
import * as coachChatApi from '../api/coachChat'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { CoachChatMessageRead } from '../types/coachChat'

const COACH_PREMIUM_GATE_DESCRIPTION =
  'С премиум-подпиской откроется персональный AI-тренер: задавайте вопросы о своих тренировках и ' +
  'получайте советы с учётом ваших реальных характеристик и прогресса.'

export function CoachPage() {
  const { user, accessToken } = useAuth()
  const hasPremium = user?.has_premium === true
  // Shown regardless of premium status -- coach_personality drives every
  // player's reminder/check-in notifications, not just this premium chat,
  // so the explainer belongs to whoever taps into "Тренер" first, not only
  // premium users.
  const [showPersonalityIntro, setShowPersonalityIntro] = useState(false)

  useEffect(() => {
    if (user !== null && !user.has_seen_coach_personality_intro) {
      setShowPersonalityIntro(true)
    }
  }, [user])

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

      {showPersonalityIntro && (
        <CoachPersonalityIntroModal onClose={() => setShowPersonalityIntro(false)} />
      )}
    </div>
  )
}

// Shown once a real 503 comes back from the backend (see CoachChatContent
// below) -- the feature is technically off (no OpenRouter key configured
// yet), a different state from "no premium access" above. Reuses the same
// shared EmptyState every other blank-list screen in the app uses, instead
// of hand-rolling its own near-identical icon-circle+text markup.
function ComingSoonCard() {
  return (
    <EmptyState
      icon="ti-message-chatbot"
      title="Скоро"
      hint="Персональный AI-тренер уже почти готов — совсем скоро сможете задавать ему вопросы о своих тренировках."
    />
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
    <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <FormError message={loadError} />
      <div className="flex max-h-[60vh] min-h-[240px] flex-col gap-4 overflow-y-auto">
        {messages === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}
        {messages !== null && messages.length === 0 && (
          // Same icon-in-a-circle language as the shared EmptyState, but
          // without its own CARD_CLASS wrapper -- this already sits inside
          // one (the chat card itself), and nesting two would double up
          // the "blue line" border.
          <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-ice/10">
              <ShieldIcon size={26} />
            </span>
            <p className="text-sm text-[#8A94A6]">
              Задайте тренеру вопрос о своих тренировках, чтобы начать разговор.
            </p>
          </div>
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
        className="flex items-end gap-2 border-t border-white/5 pt-3"
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
          className="flex-1 resize-none rounded-md border border-white/10 bg-dark-bg px-3 py-2 text-sm text-text-primary placeholder:text-text-secondary/60 focus:border-accent-ice focus:outline-none"
        />
        <Button type="submit" isLoading={isSending} disabled={input.trim() === ''}>
          Отправить
        </Button>
      </form>
    </div>
  )
}

// Two voices, two accents -- the coach speaks in the app's calm/
// informational ice tint (same one its own header badge and shield avatar
// use), the player's own messages in persimmon (the app's one "this is you
// acting" accent, e.g. Button's primary variant, XP numbers). Card-shaped
// with a thin top hairline echoing CARD_CLASS's "blue line" convention,
// not a generic messaging-app pill -- so a chat bubble still reads as part
// of this app rather than a bolted-on widget.
function ChatBubble({ message }: { message: CoachChatMessageRead }) {
  const isUser = message.role === 'user'
  const time = new Date(message.created_at).toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  })
  return (
    <div className={`flex items-end gap-2 ${isUser ? 'justify-end' : 'justify-start'}`}>
      {!isUser && (
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-accent-ice/30 bg-accent-ice/10">
          <ShieldIcon size={18} />
        </span>
      )}
      <div className={`flex max-w-[85%] flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`whitespace-pre-wrap rounded-md border-t px-3 py-2 text-sm text-[#F5F7FA] ${
            isUser
              ? 'border-accent-persimmon/30 bg-accent-persimmon/[0.08]'
              : 'border-accent-ice/25 bg-accent-ice/[0.06]'
          }`}
        >
          {message.content}
        </div>
        <span className="px-1 text-[10px] text-[#8A94A6]">{time}</span>
      </div>
    </div>
  )
}
