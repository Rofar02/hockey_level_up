import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import * as coachChatApi from '../api/coachChat'
import * as usersApi from '../api/users'
import { useAuth } from '../hooks/useAuth'
import { useCoachmarkStep } from '../hooks/useCoachmarkStep'
import type { CoachAttentionReason } from '../types/coachChat'

interface Tab {
  to: string
  icon: string
  label: string
  // Path prefixes that also light this tab up, so it stays active on the
  // screens reached from it (a team's events, a friend's profile...).
  match: string[]
  // Shows a dot -- something on that tab is waiting for the player.
  attention?: 'team'
}

const LEFT_TABS: Tab[] = [
  { to: '/', icon: 'ti-home', label: 'Сегодня', match: ['/quests'] },
  { to: '/schedule/new', icon: 'ti-calendar', label: 'План', match: ['/schedule'] },
]

const RIGHT_TABS: Tab[] = [
  {
    to: '/team',
    icon: 'ti-users',
    label: 'Команда',
    attention: 'team',
    // '/profile/' with the slash: someone else's profile, reached from here.
    match: ['/team', '/teams', '/friends', '/training-parties', '/leaderboard', '/profile/'],
  },
  {
    to: '/profile',
    icon: 'ti-user',
    label: 'Профиль',
    match: [
      '/settings',
      '/analytics',
      '/diary',
      '/restrictions',
      '/reference',
      '/exercise-catalog',
      '/inventory',
      '/skills',
      '/muscle-load',
    ],
  },
]

function isTabActive(tab: Tab, pathname: string): boolean {
  if (pathname === tab.to) {
    return true
  }
  return tab.match.some((prefix) =>
    prefix.endsWith('/') ? pathname.startsWith(prefix) : pathname === prefix || pathname.startsWith(`${prefix}/`),
  )
}

const NON_TEXT_INPUT_TYPES = new Set(['checkbox', 'radio', 'button', 'submit', 'reset', 'range', 'color', 'file', 'image'])

function isTextField(element: Element | null): boolean {
  if (!(element instanceof HTMLElement)) {
    return false
  }
  if (element.isContentEditable || element instanceof HTMLTextAreaElement) {
    return true
  }
  return element instanceof HTMLInputElement && !NON_TEXT_INPUT_TYPES.has(element.type)
}

const SETTLE_DELAYS_MS = [150, 400, 900, 2000]

// Hidden longer than this counts as "was in the background" for the
// capsule rebuild below.
const REBUILD_AFTER_HIDDEN_MS = 30_000

// 2026-10-08: WebKit can drop the compositor layer of a backdrop-filter
// element while a home-screen app sits in the background -- the capsule
// comes back invisible but still tappable. A fresh element gets a fresh
// layer, so the capsule is remounted (new key) after a long background stay
// and on a bfcache restore.
function useRebuildKey(): number {
  const [key, setKey] = useState(0)
  useEffect(() => {
    let hiddenAt: number | null = null
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        hiddenAt = Date.now()
        return
      }
      if (hiddenAt !== null && Date.now() - hiddenAt > REBUILD_AFTER_HIDDEN_MS) {
        setKey((current) => current + 1)
      }
      hiddenAt = null
    }
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        setKey((current) => current + 1)
      }
    }
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('pageshow', onPageShow)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pageshow', onPageShow)
    }
  }, [])
  return key
}

// The on-screen keyboard is up: the bar steps aside so it doesn't ride up
// over the field being typed into. Counts only while a text field has focus
// (a pinch zoom or a keyboard that left without a resize event once kept the
// bar hidden until a reload), recomputed on focus changes, viewport resize,
// rotation and return to the foreground -- several times, since the keyboard
// animates away after blur and iOS settles its sizes after a thaw.
//
// 2026-10-08: no more shifting the bar onto the visual viewport (the
// 10-04/10-08 offsetY): the document no longer scrolls (see index.css), so
// the layout viewport the bar is pinned to doesn't move and the bar sits on
// the bottom edge by CSS alone. Those offsets were what made it shake and
// jump around the app.
function useKeyboardOpen(): boolean {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const viewport = window.visualViewport
    if (viewport == null) {
      return
    }
    const update = () => {
      const zoomed = viewport.scale > 1.01
      setOpen(!zoomed && window.innerHeight - viewport.height > 150 && isTextField(document.activeElement))
    }
    let settleTimers: number[] = []
    const updateSoon = () => {
      update()
      settleTimers.forEach((timer) => window.clearTimeout(timer))
      settleTimers = SETTLE_DELAYS_MS.map((delay) => window.setTimeout(update, delay))
    }
    viewport.addEventListener('resize', update)
    window.addEventListener('resize', update)
    window.addEventListener('orientationchange', updateSoon)
    window.addEventListener('focusin', updateSoon)
    window.addEventListener('focusout', updateSoon)
    window.addEventListener('pageshow', updateSoon)
    window.addEventListener('focus', updateSoon)
    document.addEventListener('visibilitychange', updateSoon)
    update()
    return () => {
      settleTimers.forEach((timer) => window.clearTimeout(timer))
      viewport.removeEventListener('resize', update)
      window.removeEventListener('resize', update)
      window.removeEventListener('orientationchange', updateSoon)
      window.removeEventListener('focusin', updateSoon)
      window.removeEventListener('focusout', updateSoon)
      window.removeEventListener('pageshow', updateSoon)
      window.removeEventListener('focus', updateSoon)
      document.removeEventListener('visibilitychange', updateSoon)
    }
  }, [])
  return open
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
  const teamAttention = useTeamAttention()
  const rebuildKey = useRebuildKey()

  return (
    <nav
      data-app-bottom-nav
      data-nav-state={isKeyboardOpen ? 'hidden' : 'shown'}
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
        transform: isKeyboardOpen ? undefined : 'translate3d(0, 0, 0)',
        willChange: 'transform',
      }}
    >
      <NavCapsule key={rebuildKey} teamAttention={teamAttention} />
    </nav>
  )
}

function NavCapsule({ teamAttention }: { teamAttention: boolean }) {
  return (
    <div className="pointer-events-auto mx-auto flex h-16 max-w-md items-center rounded-full border border-white/15 bg-[#121820]/55 px-1.5 shadow-[0_12px_32px_-8px_rgba(0,0,0,0.65)] backdrop-blur-3xl backdrop-saturate-150">
      {LEFT_TABS.map((tab) => (
        <TabLink key={tab.to} tab={tab} />
      ))}
      <CoachButton />
      {RIGHT_TABS.map((tab) => (
        <TabLink key={tab.to} tab={tab} hasAttention={tab.attention === 'team' && teamAttention} />
      ))}
    </div>
  )
}

function TabLink({ tab, hasAttention = false }: { tab: Tab; hasAttention?: boolean }) {
  const { pathname } = useLocation()
  const isActive = isTabActive(tab, pathname)
  // One-time pointer for players who knew the old "Ещё" menu (and a fine
  // first hint for new ones): where its items went.
  const teamHintRef = useCoachmarkStep(
    'nav-team-tab',
    'Команда, друзья, совместные тренировки и рейтинги — здесь. Дневник, справочник и инвентарь — в профиле.',
    'ti-users',
  )
  return (
    <Link
      ref={tab.attention === 'team' ? teamHintRef : undefined}
      to={tab.to}
      aria-label={hasAttention ? `${tab.label}: есть новое` : undefined}
      aria-current={isActive ? 'page' : undefined}
      className={`group flex h-full min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors ${
        isActive ? 'text-accent-ice' : 'text-text-secondary hover:text-text-primary'
      }`}
    >
      <span
        className={`relative flex h-7 w-12 items-center justify-center rounded-full transition-colors ${
          isActive ? 'bg-accent-ice/15' : ''
        }`}
      >
        <i className={`ti ${tab.icon} text-xl`} aria-hidden="true" />
        {hasAttention && (
          <span className="absolute right-2.5 top-0.5 h-2 w-2 rounded-full border-2 border-[#121820] bg-accent-persimmon box-content" />
        )}
      </span>
      <span className="truncate">{tab.label}</span>
    </Link>
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

// Same re-check-on-navigation approach as the coach glow below: the dot
// goes out as soon as the player has dealt with whatever was waiting.
function useTeamAttention(): boolean {
  const { accessToken } = useAuth()
  const { pathname } = useLocation()
  const [hasAttention, setHasAttention] = useState(false)
  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    usersApi
      .getTeamAttention(accessToken)
      .then((result) => {
        if (!cancelled) {
          setHasAttention(result.friend_requests + result.party_invites + result.team_join_requests > 0)
        }
      })
      .catch(() => {
        // Best-effort: no dot is the safe default.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, pathname])
  return hasAttention
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
