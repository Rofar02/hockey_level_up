import type { TeamEventRead } from '../types/teamEvent'

// An event still counts as "ближайшее" for a couple of hours after its
// start -- it's usually still going on.
const STILL_CURRENT_MS = 2 * 60 * 60 * 1000

export function upcomingEvents(events: TeamEventRead[], now = Date.now()): TeamEventRead[] {
  return events
    .filter((event) => event.status === 'scheduled' && new Date(event.starts_at).getTime() > now - STILL_CURRENT_MS)
    .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())
}

export function isPastEvent(event: TeamEventRead, now = Date.now()): boolean {
  return new Date(event.starts_at).getTime() <= now - STILL_CURRENT_MS
}
