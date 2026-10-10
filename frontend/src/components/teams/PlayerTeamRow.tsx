import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as teamsApi from '../../api/teams'
import { API_BASE_URL } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { TeamCardRead } from '../../types/team'

// Under the player card in a profile (2026-10-09): the player's team --
// emblem, name, league, division and place -- leading to the team card.
export function PlayerTeamRow({ teamId }: { teamId: string }) {
  const { accessToken } = useAuth()
  const [card, setCard] = useState<TeamCardRead | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamsApi
      .getTeamCard(teamId, accessToken)
      .then((result) => {
        if (!cancelled) {
          setCard(result)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId])

  if (card === null) {
    return null
  }
  const details = [
    card.league_name?.replace(/ хоккейная/i, '') ?? null,
    card.division_name,
    card.league_place !== null ? `#${card.league_place} в городе` : card.city,
  ].filter((part): part is string => !!part)

  return (
    <Link
      to={`/teams/${card.id}/card`}
      className="flex min-h-14 items-center gap-3 rounded-[14px] border border-white/5 bg-dark-card px-3.5 py-2 transition-colors hover:border-white/15"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full border border-accent-ice/30 bg-[#22304A] text-accent-ice">
        {card.logo_url !== null ? (
          <img src={`${API_BASE_URL}${card.logo_url}`} alt="" className="h-full w-full object-cover" />
        ) : (
          <i className="ti ti-shield text-lg" aria-hidden="true" />
        )}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-[15px] font-semibold text-[#F5F7FA]">{card.name}</span>
        {details.length > 0 && <span className="truncate text-xs text-[#8A94A6]">{details.join(' · ')}</span>}
      </span>
      <i className="ti ti-chevron-right text-lg text-[#8A94A6]" aria-hidden="true" />
    </Link>
  )
}
