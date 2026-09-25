import { useEffect, useState } from 'react'
import * as teamEventsApi from '../api/teamEvents'
import * as teamsApi from '../api/teams'
import type { TeamEventRead } from '../types/teamEvent'
import { useAuth } from './useAuth'

export interface LoadedTeamEvent {
  teamId: string
  event: TeamEventRead
}

// A DayPlan only carries team_event_id -- the event itself lives under the
// user's team. One team per user in v2 (TeamMembership is unique on
// user_id), so the first team from /teams/me is the right one.
async function loadTeamEvent(eventId: string, token: string): Promise<LoadedTeamEvent | null> {
  const [team] = await teamsApi.listMyTeams(token)
  if (team === undefined) {
    return null
  }
  return { teamId: team.id, event: await teamEventsApi.getTeamEvent(team.id, eventId, token) }
}

// One request per event per page load: the week screen shows the same
// event in a row and again in its modal. Failed loads aren't cached.
const cache = new Map<string, Promise<LoadedTeamEvent | null>>()

function cachedTeamEvent(eventId: string, token: string): Promise<LoadedTeamEvent | null> {
  let pending = cache.get(eventId)
  if (pending === undefined) {
    pending = loadTeamEvent(eventId, token).catch(() => {
      cache.delete(eventId)
      return null
    })
    cache.set(eventId, pending)
  }
  return pending
}

// Drop cached events, e.g. after the page reloads its week.
export function clearTeamEventCache(): void {
  cache.clear()
}

// undefined = still loading, null = couldn't load (left the team, event
// gone) -- callers fall back to showing an ordinary day.
export function useTeamEvent(eventId: string | null): LoadedTeamEvent | null | undefined {
  const { accessToken } = useAuth()
  const [state, setState] = useState<{ eventId: string; result: LoadedTeamEvent | null } | null>(null)

  useEffect(() => {
    if (accessToken === null || eventId === null) {
      return
    }
    let cancelled = false
    cachedTeamEvent(eventId, accessToken).then((result) => {
      if (!cancelled) {
        setState({ eventId, result })
      }
    })
    return () => {
      cancelled = true
    }
  }, [accessToken, eventId])

  if (eventId === null) {
    return null
  }
  return state !== null && state.eventId === eventId ? state.result : undefined
}
