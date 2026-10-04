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

interface NavPlacement {
  // The on-screen keyboard is up: the bar steps aside so it doesn't ride
  // up over the field being typed into (Android) or float mid-screen (iOS).
  hidden: boolean
  // Shift that keeps the bar on the visible bottom edge when the visual
  // viewport no longer ends where the layout viewport does.
  offsetY: number
}

const RESTING: NavPlacement = { hidden: false, offsetY: 0 }

// 2026-10-04 fix for "капсула то уезжает в середину, то пропадает, помогает
// только перезапуск" (iOS home-screen app). The old hook hid the bar while
// innerHeight - visualViewport.height > 150 and recomputed that ONLY on a
// visualViewport resize: if the keyboard went away without one (app sent to
// the background, tab switch) the bar stayed hidden until a reload, and a
// pinch zoom also read as "keyboard". And a fixed bar is pinned to the
// layout viewport, which iOS can leave offset after the keyboard closes, so
// the bar showed up in the middle of the screen. Now the keyboard counts
// only while a text field has focus, the state is recomputed on focus
// changes, viewport scroll/resize, rotation and return to the foreground,
// and the bar is shifted onto the visible bottom edge.
function useNavPlacement(): NavPlacement {
  const [placement, setPlacement] = useState<NavPlacement>(RESTING)
  useEffect(() => {
    const viewport = window.visualViewport
    if (viewport == null) {
      return
    }
    const update = () => {
      const zoomed = viewport.scale > 1.01
      const hidden = !zoomed && window.innerHeight - viewport.height > 150 && isTextField(document.activeElement)
      const gap = viewport.offsetTop + viewport.height - window.innerHeight
      const offsetY = hidden || zoomed || Math.abs(gap) < 2 ? 0 : Math.round(gap)
      setPlacement((current) =>
        current.hidden === hidden && current.offsetY === offsetY ? current : { hidden, offsetY },
      )
    }
    // The keyboard animates away after blur -- check again once it's gone.
    let settleTimer: number | undefined
    const updateSoon = () => {
      update()
      window.clearTimeout(settleTimer)
      settleTimer = window.setTimeout(update, 350)
    }
    viewport.addEventListener('resize', update)
    viewport.addEventListener('scroll', update)
    window.addEventListener('resize', update)
    window.addEventListener('orientationchange', updateSoon)
    window.addEventListener('focusin', updateSoon)
    window.addEventListener('focusout', updateSoon)
    window.addEventListener('pageshow', updateSoon)
    document.addEventListener('visibilitychange', updateSoon)
    update()
    return () => {
      window.clearTimeout(settleTimer)
      viewport.removeEventListener('resize', update)
      viewport.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
      window.removeEventListener('orientationchange', updateSoon)
      window.removeEventListener('focusin', updateSoon)
      window.removeEventListener('focusout', updateSoon)
      window.removeEventListener('pageshow', updateSoon)
      document.removeEventListener('visibilitychange', updateSoon)
    }
  }, [])
  return placement
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
  const { hidden: isKeyboardOpen, offsetY } = useNavPlacement()
  const teamAttention = useTeamAttention()

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
        transform: isKeyboardOpen ? undefined : `translate3d(0, ${offsetY}px, 0)`,
        willChange: 'transform',
      }}
    >
      <div className="pointer-events-auto mx-auto flex h-16 max-w-md items-center rounded-full border border-white/15 bg-[#121820]/55 px-1.5 shadow-[0_12px_32px_-8px_rgba(0,0,0,0.65)] backdrop-blur-3xl backdrop-saturate-150">
        {LEFT_TABS.map((tab) => (
          <TabLink key={tab.to} tab={tab} />
        ))}
        <CoachButton />
        {RIGHT_TABS.map((tab) => (
          <TabLink key={tab.to} tab={tab} hasAttention={tab.attention === 'team' && teamAttention} />
        ))}
      </div>
    </nav>
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
