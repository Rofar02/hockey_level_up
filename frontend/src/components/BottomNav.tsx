import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import * as coachChatApi from '../api/coachChat'
import { useAuth } from '../hooks/useAuth'
import type { CoachAttentionReason } from '../types/coachChat'

interface Tab {
  to: string
  icon: string
  label: string
  end?: boolean
}

const LEFT_TABS: Tab[] = [
  { to: '/', icon: 'ti-home', label: 'Главная', end: true },
  { to: '/schedule/new', icon: 'ti-calendar', label: 'Неделя' },
]

const RIGHT_TABS: Tab[] = [
  { to: '/profile', icon: 'ti-user', label: 'Профиль' },
  // Its own route (/more, see MorePage) rather than a popup opened in place
  // -- a plain NavLink like the other tabs, so it's reachable by
  // back/forward and a direct link, not just a tap on this button.
  { to: '/more', icon: 'ti-dots', label: 'Ещё' },
]

// The on-screen keyboard shrinks the visual viewport; on Android a fixed
// bar then rides up above the keyboard and covers the field being typed
// into. While it's open the bar steps aside.
function useKeyboardOpen(): boolean {
  const [isOpen, setIsOpen] = useState(false)
  useEffect(() => {
    const viewport = window.visualViewport
    if (viewport == null) {
      return
    }
    const update = () => setIsOpen(window.innerHeight - viewport.height > 150)
    viewport.addEventListener('resize', update)
    return () => viewport.removeEventListener('resize', update)
  }, [])
  return isOpen
}

// A floating frosted-glass capsule with the AI coach in the middle, raised
// a little above the bar -- the coach used to be reachable only from a
// small icon on the profile page.
//
// The <nav> itself spans the whole reserved strip at the bottom (see
// --bottom-nav-space in index.css) but lets taps through; only the capsule
// catches them. CoachmarkOverlay measures this element to keep tooltips
// clear of it, so its box must be the full strip, raised button included.
export function BottomNav() {
  const isKeyboardOpen = useKeyboardOpen()

  return (
    <nav
      data-app-bottom-nav
      aria-label="Основная навигация"
      className={`pointer-events-none fixed inset-x-0 bottom-0 z-40 px-3 pt-7 transition-transform duration-200 ${
        isKeyboardOpen ? 'translate-y-[120%]' : ''
      }`}
      // 2026-09-18 fix: iOS Safari briefly hides/flickers a `position: fixed`
      // element while the page is actively scrolling -- it drops the element
      // from its own compositor layer mid-scroll and only repaints it once
      // scrolling settles. `translateZ(0)` (plus `will-change`) forces this
      // nav onto its own GPU layer up front -- the standard fix for this
      // WebKit quirk.
      style={{
        paddingBottom: 'calc(12px + env(safe-area-inset-bottom))',
        transform: isKeyboardOpen ? undefined : 'translateZ(0)',
        willChange: 'transform',
      }}
    >
      <div className="pointer-events-auto mx-auto flex h-16 max-w-md items-center rounded-full border border-white/15 bg-[#121820]/55 px-1.5 shadow-[0_12px_32px_-8px_rgba(0,0,0,0.65)] backdrop-blur-3xl backdrop-saturate-150">
        {LEFT_TABS.map((tab) => (
          <TabLink key={tab.to} tab={tab} />
        ))}
        <CoachButton />
        {RIGHT_TABS.map((tab) => (
          <TabLink key={tab.to} tab={tab} />
        ))}
      </div>
    </nav>
  )
}

function TabLink({ tab }: { tab: Tab }) {
  return (
    <NavLink
      to={tab.to}
      end={tab.end}
      className={({ isActive }) =>
        `group flex h-full min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors ${
          isActive ? 'text-accent-ice' : 'text-text-secondary hover:text-text-primary'
        }`
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={`flex h-7 w-12 items-center justify-center rounded-full transition-colors ${
              isActive ? 'bg-accent-ice/15' : ''
            }`}
          >
            <i className={`ti ${tab.icon} text-xl`} aria-hidden="true" />
          </span>
          <span className="truncate">{tab.label}</span>
        </>
      )}
    </NavLink>
  )
}

// Re-checked on every navigation (cheap: three COUNT queries) -- mainly so
// the glow goes out as soon as the player comes back from the chat.
function useCoachAttention(): CoachAttentionReason | null {
  const { accessToken } = useAuth()
  const { pathname } = useLocation()
  const [reason, setReason] = useState<CoachAttentionReason | null>(null)
  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    coachChatApi
      .getCoachAttention(accessToken)
      .then((result) => {
        if (!cancelled) {
          setReason(result.reason)
        }
      })
      .catch(() => {
        // Best-effort: no glow is the safe default.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, pathname])
  return reason
}

const ATTENTION_LABELS: Record<CoachAttentionReason, string> = {
  pending_action: 'ИИ-тренер: ждёт ответа на предложение',
  checkin: 'ИИ-тренер: спрашивает о самочувствии',
  first_visit: 'ИИ-тренер: познакомьтесь',
}

function CoachButton() {
  // Glows only when the coach actually has something for the player.
  const reason = useCoachAttention()
  return (
    <NavLink
      to="/coach"
      aria-label={reason !== null ? ATTENTION_LABELS[reason] : 'ИИ-тренер'}
      data-attention={reason ?? undefined}
      className="flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-0.5 pb-1.5 text-[10px] font-medium text-accent-ice"
    >
      <span className={`-mt-7 flex h-[52px] w-[52px] items-center justify-center rounded-full border-4 border-dark-bg ${reason !== null ? 'coach-glow' : ''} bg-accent-persimmon text-white shadow-[0_6px_18px_-4px_rgba(255,106,61,0.6)] transition-transform active:scale-95`}>
        <i className="ti ti-message-chatbot text-2xl" aria-hidden="true" />
      </span>
      <span aria-hidden="true">Тренер</span>
    </NavLink>
  )
}
