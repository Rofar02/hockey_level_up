// Which API answers are kept for offline use, whose they are, and how old
// the oldest one on screen is (Б1, 2026-10-13). client.ts asks here; the
// "Нет связи" banner reads the age ("данные от 10:42").
import { subscribeNetworkStatus, isOnline } from './networkStatus'

// Read-only screens a player needs at the rink: today and the week, the
// workout with its exercises (and what the player's history/suggestions
// say for them), ice prep, the profile/card, the team and its events.
// Sign-in state itself (/auth/me) has its own snapshot (tokenStorage.ts).
const OFFLINE_PATHS: RegExp[] = [
  /^\/schedule\/(weekly\/current|weekly\?week_start_date=|day-plan\?date=|day-plans\/[^/?]+$|features$)/,
  /^\/training-block\/current$/,
  /^\/training-sessions\/[^/]+\/(diary|exercises\/[^/]+\/sets)$/,
  /^\/exercises\/[^/]+\/(history|suggested-weight|suggested-reps|suggested-duration|target-stats|muscle-groups|equipment-items)/,
  /^\/users\/me\/(day-report\?|pending-reports$|stats$|streak$|season$|muscle-loads$|equipment-items$|restrictions$|skill-preferences$|coachmarks-seen$|rest-done-phrase$|weekly-review$|team-attention$|coach-attention$)/,
  /^\/users\/[^/]+\/profile$/,
  /^\/(quests\/status|quests\/coach-tasks|leaderboard\/me|skills)$/,
  /^\/teams\/me$/,
  /^\/teams\/[^/]+(\/card|\/events|\/events\/[^/]+(\/attendance|\/lineup|\/readiness)?|\/lineup\/current)?$/,
]

// Never kept even if a pattern above happens to match.
const NEVER = [/^\/teams\/(admin|leagues|invitations|join-requests|leaderboard)/]

export function isOfflinePath(path: string): boolean {
  return OFFLINE_PATHS.some((pattern) => pattern.test(path)) && !NEVER.some((pattern) => pattern.test(path))
}

let offlineUserId: string | null = null

// Set as soon as the player is known (a fresh /auth/me, or the saved
// snapshot on an offline start); null on sign-out.
export function setOfflineUser(userId: string | null): void {
  offlineUserId = userId
}

export function getOfflineUser(): string | null {
  return offlineUserId
}

// -- "данные от 10:42" --

type Listener = () => void
const listeners = new Set<Listener>()
let oldestShownAt: number | null = null

export function noteSavedDataShown(storedAt: number): void {
  if (oldestShownAt === null || storedAt < oldestShownAt) {
    oldestShownAt = storedAt
    for (const listener of listeners) {
      listener()
    }
  }
}

export function getOldestShownAt(): number | null {
  return oldestShownAt
}

export function subscribeSavedDataAge(listener: Listener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

// Back online: whatever loads next is fresh.
subscribeNetworkStatus(() => {
  if (isOnline() && oldestShownAt !== null) {
    oldestShownAt = null
    for (const listener of listeners) {
      listener()
    }
  }
})
