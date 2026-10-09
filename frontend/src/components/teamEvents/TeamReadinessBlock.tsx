import { useEffect, useState } from 'react'
import * as teamEventsApi from '../../api/teamEvents'
import { useAuth } from '../../hooks/useAuth'
import type { TeamReadinessRead } from '../../types/teamEvent'
import { CARD_CLASS } from '../ui/cardStyle'

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
  fresh: { label: 'свежий', className: 'text-accent-ice' },
  tired: { label: 'устал', className: 'text-[#F5C26B]' },
  overloaded: { label: 'перегружен', className: 'text-accent-persimmon' },
  no_data: { label: 'нет данных', className: 'text-[#8A94A6]' },
}

// Release plan step 9 (2026-10-09), captain only: who of the "going"
// players is fresh, tired or overloaded -- legs and back from their gym
// and ice load; players who don't train in the app show as "нет данных".
export function TeamReadinessBlock({ teamId, eventId, goingCount }: { teamId: string; eventId: string; goingCount: number }) {
  const { accessToken } = useAuth()
  const [readiness, setReadiness] = useState<TeamReadinessRead | null>(null)
  const [isOpen, setIsOpen] = useState(false)

  useEffect(() => {
    if (accessToken === null || goingCount === 0) {
      return
    }
    let cancelled = false
    teamEventsApi
      .getEventReadiness(teamId, eventId, accessToken)
      .then((result) => {
        if (!cancelled) {
          setReadiness(result)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId, eventId, goingCount])

  if (readiness === null || readiness.going === 0) {
    return null
  }
  return (
    <div className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
      <button type="button" onClick={() => setIsOpen((open) => !open)} className="flex items-center justify-between gap-2 text-left">
        <span className="text-sm text-[#F5F7FA]">
          Готовность: идут {readiness.going} — <span className="text-accent-ice">{readiness.fresh} свежие</span>
          {readiness.tired > 0 && <span className="text-[#F5C26B]">, {readiness.tired} устали</span>}
          {readiness.overloaded > 0 && <span className="text-accent-persimmon">, {readiness.overloaded} перегружены</span>}
          {readiness.no_data > 0 && <span className="text-[#8A94A6]">, {readiness.no_data} без данных</span>}
        </span>
        <i className={`ti ti-chevron-down text-xs text-[#8A94A6] transition-transform ${isOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {isOpen && (
        <div className="flex flex-col">
          {readiness.players.map((player) => (
            <div key={player.user_id} className="flex min-h-9 items-center justify-between gap-2 border-t border-white/5 text-sm">
              <span className="truncate text-[#F5F7FA]">
                {player.jersey_number != null && <span className="mr-1.5 text-[#8A94A6]">#{player.jersey_number}</span>}
                {player.last_name || player.first_name}
              </span>
              <span className={`shrink-0 text-xs ${STATUS_LABELS[player.status]?.className ?? ''}`}>
                {STATUS_LABELS[player.status]?.label ?? player.status}
              </span>
            </div>
          ))}
          <p className="pt-2 text-xs text-[#8A94A6]">По нагрузке ног и спины за последние дни — зал и лёд.</p>
        </div>
      )}
    </div>
  )
}
