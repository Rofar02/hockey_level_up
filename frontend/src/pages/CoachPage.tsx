import { useEffect, useRef, useState } from 'react'
import { CoachPersonalityIntroModal } from '../components/CoachPersonalityIntroModal'
import { MarkdownContent } from '../components/MarkdownContent'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_BORDER, CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { ShieldIcon } from '../components/ui/ShieldIcon'
import * as authApi from '../api/auth'
import * as coachChatApi from '../api/coachChat'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { CoachChatMessageRead, ProposedActionRead } from '../types/coachChat'
import type { CoachPersonality } from '../types/user'

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

        {/* 2026-09-17 (audit item #7): the backend no longer walls chat
            access behind premium at all -- CoachChatService.send_message
            applies a small free-trial monthly cap for has_premium=False
            instead of a flat 403 (see FREE_TRIAL_MESSAGE_LIMIT). The one
            non-premium-only bit left here is the upsell banner below the
            history -- reaching the cap surfaces the backend's own 429
            detail message through the existing send-error banner, no
            special handling needed for that. */}
        {accessToken !== null && (
          <CoachChatContent
            accessToken={accessToken}
            hasPremium={hasPremium}
            coachPersonality={user?.coach_personality ?? 'calm'}
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
// below) -- the feature is technically off (no z.ai key configured
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

function CoachChatContent({
  accessToken,
  hasPremium,
  coachPersonality,
}: {
  accessToken: string
  hasPremium: boolean
  coachPersonality: CoachPersonality
}) {
  const { updateUser } = useAuth()
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
  const [decidingActionId, setDecidingActionId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  function applyActionResult(actionId: string, updated: ProposedActionRead) {
    setMessages((prev) =>
      (prev ?? []).map((message) =>
        message.proposed_action?.id === actionId
          ? { ...message, proposed_action: updated }
          : message,
      ),
    )
  }

  async function handleConfirmAction(actionId: string) {
    setDecidingActionId(actionId)
    setActionError(null)
    try {
      const result = await coachChatApi.confirmProposedAction(actionId, accessToken)
      applyActionResult(actionId, result)
      // The confirmed action may have changed a User field (e.g.
      // tournament_date) that other screens read from auth state -- refetch
      // rather than guess which fields changed for which action_type.
      const refreshedUser = await authApi.getCurrentUser(accessToken)
      updateUser(refreshedUser)
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось подтвердить предложение.')
    } finally {
      setDecidingActionId(null)
    }
  }

  async function handleDismissAction(actionId: string) {
    setDecidingActionId(actionId)
    setActionError(null)
    try {
      const result = await coachChatApi.dismissProposedAction(actionId, accessToken)
      applyActionResult(actionId, result)
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось отклонить предложение.')
    } finally {
      setDecidingActionId(null)
    }
  }

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
  }, [messages, isSending])

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
      proposed_action: null,
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
        {messages?.map((message) => (
          <ChatBubble
            key={message.id}
            message={message}
            decidingActionId={decidingActionId}
            onConfirmAction={handleConfirmAction}
            onDismissAction={handleDismissAction}
          />
        ))}
        {isSending && <TypingIndicator personality={coachPersonality} />}
        <div ref={bottomRef} />
      </div>

      <FormError message={actionError} />
      <FormError message={sendError} />

      {!hasPremium && (
        <p className="text-xs text-[#8A94A6]">
          Бесплатная проба AI-тренера. С премиум-подпиской — без ограничения по числу сообщений.
        </p>
      )}

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
          // text-base (16px), not text-sm (14px) -- a smaller font size on
          // a focused input makes iOS Safari (and some Android browsers)
          // auto-zoom the whole page in, since they assume anything under
          // 16px is too small to read/tap comfortably. Found live-testing,
          // 2026-08-31: "когда пишу тренеру приближается".
          className="flex-1 resize-none rounded-md border border-white/10 bg-dark-bg px-3 py-2 text-base text-text-primary placeholder:text-text-secondary/60 focus:border-accent-ice focus:outline-none"
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
function ChatBubble({
  message,
  decidingActionId,
  onConfirmAction,
  onDismissAction,
}: {
  message: CoachChatMessageRead
  decidingActionId: string | null
  onConfirmAction: (actionId: string) => void
  onDismissAction: (actionId: string) => void
}) {
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
          className={`rounded-md border-t px-3 py-2 text-sm text-[#F5F7FA] ${
            isUser
              ? 'whitespace-pre-wrap border-accent-persimmon/30 bg-accent-persimmon/[0.08]'
              : 'border-accent-ice/25 bg-accent-ice/[0.06]'
          }`}
        >
          {isUser ? message.content : <MarkdownContent content={message.content} />}
        </div>
        <span className="px-1 text-[10px] text-[#8A94A6]">{time}</span>
        {message.proposed_action !== null && (
          <ProposedActionCard
            action={message.proposed_action}
            isDeciding={decidingActionId === message.proposed_action.id}
            onConfirm={() => message.proposed_action !== null && onConfirmAction(message.proposed_action.id)}
            onDismiss={() => message.proposed_action !== null && onDismissAction(message.proposed_action.id)}
          />
        )}
      </div>
    </div>
  )
}

// Inline card, not a Modal -- sits right under the coach's bubble that
// proposed it (same "accept/dismiss row" shape as FriendsPage's incoming
// friend-request cards). Only PENDING actions get the button pair; a
// decided one becomes a small status line instead, so scrolling back
// through history still shows what happened without offering a stale
// re-confirm.
function ProposedActionCard({
  action,
  isDeciding,
  onConfirm,
  onDismiss,
}: {
  action: ProposedActionRead
  isDeciding: boolean
  onConfirm: () => void
  onDismiss: () => void
}) {
  if (action.status !== 'pending') {
    return (
      <div className={`flex items-center gap-2 px-3 py-2 text-xs text-[#8A94A6] ${CARD_BORDER} rounded-md bg-dark-card/60`}>
        <i
          className={`ti ${action.status === 'confirmed' ? 'ti-circle-check text-accent-ice' : 'ti-circle-x'}`}
          aria-hidden="true"
        />
        {action.summary}
      </div>
    )
  }

  return (
    <div className={`flex flex-col gap-2 p-3 ${CARD_BORDER} rounded-md bg-dark-card`}>
      <p className="text-sm text-[#F5F7FA]">{action.summary}</p>
      <div className="flex gap-2">
        <Button
          type="button"
          isLoading={isDeciding}
          onClick={onConfirm}
          className="!px-3 !py-1.5 !text-xs"
        >
          Подтвердить
        </Button>
        <Button
          type="button"
          variant="neutral"
          disabled={isDeciding}
          onClick={onDismiss}
          className="!px-3 !py-1.5 !text-xs"
        >
          Не сейчас
        </Button>
      </div>
    </div>
  )
}

// Same 4-way split as coach_personality_prompts.py's PERSONALITY_SYSTEM_PROMPTS
// and app/services/coach_personality_phrases.py's REST_DONE/CHECKIN/REMINDER
// pools -- purely decorative here (no LLM call, no server round-trip), just
// keeping the loading state in the same voice as the personality the player
// picked instead of a generic "Загрузка...".
const THINKING_PHRASES: Record<CoachPersonality, string[]> = {
  calm: [
    'Думаю над ответом...',
    'Собираю мысли...',
    'Читаю твою сводку...',
    'Подбираю слова...',
    'Минутку, соображаю...',
    'Взвешиваю варианты...',
    'Смотрю на твой прогресс...',
  ],
  strict: [
    'Анализирую...',
    'Формулирую...',
    'Сверяюсь с твоими данными...',
    'Собираюсь с мыслями...',
    'Просчитываю...',
    'Готовлю ответ по делу...',
    'Без спешки, но думаю...',
  ],
  humor: [
    'Разгоняюсь на подступах к ответу...',
    'Ищу шайбу в своих мыслях...',
    'Делаю вбрасывание идей...',
    'Форчекинг собственных мыслей...',
    'Считаю до буллита...',
    'Затачиваю коньки для ответа...',
    'Ищу подходящую фразу в раздевалке...',
  ],
  vibe: [
    'Думаю, бро...',
    'Секунду, чел...',
    'Го, собираю ответ...',
    'Кручу мысли...',
    'Момент, соображаю...',
    'Погнали, почти готово...',
    'Секу фишку, отвечаю...',
  ],
}

// Shown in the thread itself (not just the send button's own "Загрузка..."
// text) while waiting on the reply -- found live-testing, 2026-08-31: a
// player looking at the message log during the several-second wait for a
// real LLM reply saw nothing at all change there, which read as the app
// having silently hung rather than actually working. Same coach-side
// avatar/bubble shape as ChatBubble's own assistant bubble so it reads as
// "the coach is about to say something" rather than a generic spinner.
function TypingIndicator({ personality }: { personality: CoachPersonality }) {
  const phrases = THINKING_PHRASES[personality]
  const [phraseIndex, setPhraseIndex] = useState(() => Math.floor(Math.random() * phrases.length))

  useEffect(() => {
    if (phrases.length <= 1) {
      return
    }
    const interval = setInterval(() => {
      setPhraseIndex((prev) => {
        let next = Math.floor(Math.random() * phrases.length)
        while (next === prev) {
          next = Math.floor(Math.random() * phrases.length)
        }
        return next
      })
    }, 1700)
    return () => clearInterval(interval)
  }, [phrases])

  return (
    <div className="flex items-end gap-2 justify-start">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-accent-ice/30 bg-accent-ice/10">
        <ShieldIcon size={18} />
      </span>
      <div className="flex items-center gap-2 rounded-md border-t border-accent-ice/25 bg-accent-ice/[0.06] px-3 py-2.5">
        <span className="text-xs text-[#8A94A6]">{phrases[phraseIndex]}</span>
        <div className="flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-accent-ice/70"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
