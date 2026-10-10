import { useEffect, useState } from 'react'
import * as teamsApi from '../api/teams'
import { API_BASE_URL } from '../api/client'
import type { PlayerCardTeam } from '../components/PlayerCard'
import type { PlayerTeamBadgeRead } from '../types/user'
import { useAuth } from './useAuth'

// The signed-in player's team for their own card (2026-10-09) -- a player
// is in at most one team. Best-effort: null on any error, the card then
// shows the plain shield.
export function useMyTeam(): PlayerCardTeam | null {
  const { accessToken } = useAuth()
  const [team, setTeam] = useState<PlayerCardTeam | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamsApi
      .listMyTeams(accessToken)
      .then((teams) => {
        const first = teams[0]
        if (!cancelled && first !== undefined) {
          setTeam({
            id: first.id,
            name: first.name,
            logoUrl: first.logo_url !== null ? `${API_BASE_URL}${first.logo_url}` : null,
            city: first.city ?? null,
          })
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken])

  return team
}

// Someone else's team as UserPublicRead carries it.
export function cardTeamFrom(badge: PlayerTeamBadgeRead | null | undefined): PlayerCardTeam | null {
  if (badge == null) {
    return null
  }
  return {
    id: badge.id,
    name: badge.name,
    logoUrl: badge.logo_url !== null ? `${API_BASE_URL}${badge.logo_url}` : null,
    city: badge.city,
  }
}
