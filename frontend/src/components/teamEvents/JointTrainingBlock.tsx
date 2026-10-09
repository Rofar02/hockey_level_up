import { useEffect, useState } from 'react'
import * as teamEventsApi from '../../api/teamEvents'
import { API_BASE_URL, ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { GuestTeamRead, TeamEventRead, TeamSearchHitRead } from '../../types/teamEvent'
import { Button } from '../ui/Button'
import { CARD_CLASS } from '../ui/cardStyle'
import { FormError } from '../ui/FormError'
import { Modal } from '../ui/Modal'
import { TextField } from '../ui/TextField'

const STATUS_LABELS: Record<string, string> = {
  host: 'хозяева',
  invited: 'приглашены',
  accepted: 'идут вместе',
  declined: 'отказались',
}

function Emblem({ url }: { url: string | null }) {
  return (
    <span className="flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/15 bg-dark-bg text-[#8A94A6]">
      {url !== null ? <img src={`${API_BASE_URL}${url}`} alt="" className="h-full w-full object-cover" /> : <i className="ti ti-shield text-sm" aria-hidden="true" />}
    </span>
  )
}

// A joint training (release plan step 3.5, 2026-10-09): who trains here
// together; the host captain invites another team, a guest captain can
// take their team out.
export function JointTrainingBlock({
  teamId,
  event,
  isCaptain,
}: {
  teamId: string
  event: TeamEventRead
  isCaptain: boolean
}) {
  const { accessToken } = useAuth()
  const [guests, setGuests] = useState<GuestTeamRead[] | null>(null)
  const [isSearchOpen, setIsSearchOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isHost = event.team_id === teamId

  async function reload() {
    if (accessToken === null) {
      return
    }
    try {
      setGuests(await teamEventsApi.listEventGuests(teamId, event.id, accessToken))
    } catch {
      setGuests([])
    }
  }

  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, teamId, event.id])

  if (event.event_type !== 'training' || guests === null) {
    return null
  }
  const others = guests.filter((g) => g.status !== 'host')
  if (others.length === 0 && !(isHost && isCaptain)) {
    return null
  }

  async function handleLeave() {
    if (accessToken === null) {
      return
    }
    setError(null)
    try {
      await teamEventsApi.leaveJointEvent(teamId, event.id, accessToken)
      window.location.assign(`/teams/${teamId}/events`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось выйти из совместной тренировки.')
    }
  }

  return (
    <div className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
      <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">
        {others.length > 0 ? 'Совместная тренировка' : 'Тренироваться вместе с другой командой'}
      </span>
      {guests
        .filter((g) => others.length > 0 || g.status !== 'host')
        .map((guest) => (
          <div key={guest.team_id} className="flex items-center gap-2 text-sm">
            <Emblem url={guest.logo_url} />
            <span className="min-w-0 flex-1 truncate text-[#F5F7FA]">{guest.name}</span>
            <span className="shrink-0 text-xs text-[#8A94A6]">{STATUS_LABELS[guest.status] ?? guest.status}</span>
          </div>
        ))}
      {isHost && isCaptain && (
        <Button type="button" variant="neutral" className="!py-1.5 !text-xs" onClick={() => setIsSearchOpen(true)}>
          Пригласить команду
        </Button>
      )}
      {!isHost && isCaptain && (
        <Button type="button" variant="neutral" className="!py-1.5 !text-xs" onClick={handleLeave}>
          Выйти из совместной
        </Button>
      )}
      <FormError message={error} />
      {isSearchOpen && (
        <InviteTeamModal
          title="Пригласить команду"
          teamId={teamId}
          onInvite={async (guestTeamId) => {
            if (accessToken !== null) {
              await teamEventsApi.inviteTeamToEvent(teamId, event.id, guestTeamId, accessToken)
              await reload()
            }
          }}
          onClose={() => setIsSearchOpen(false)}
        />
      )}
    </div>
  )
}

// Search by name or city, then "Позвать" -- shared by a single training and
// a recurring slot.
export function InviteTeamModal({
  title,
  teamId,
  onInvite,
  onClose,
}: {
  title: string
  teamId: string
  onInvite: (guestTeamId: string) => Promise<void>
  onClose: () => void
}) {
  const { accessToken } = useAuth()
  const [query, setQuery] = useState('')
  const [hits, setHits] = useState<TeamSearchHitRead[]>([])
  // The query the shown hits belong to -- "nothing found" only after it answered.
  const [answeredQuery, setAnsweredQuery] = useState<string | null>(null)
  const [invited, setInvited] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null || query.trim().length < 2) {
      setHits([])
      return
    }
    const timer = window.setTimeout(() => {
      teamEventsApi
        .searchTeamsToInvite(teamId, query.trim(), accessToken)
        .then((result) => {
          setHits(result)
          setAnsweredQuery(query.trim())
        })
        .catch(() => setHits([]))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [accessToken, teamId, query])

  return (
    <Modal title={title} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <TextField label="Название или город" value={query} onChange={(e) => setQuery(e.target.value)} autoFocus />
        {hits.map((hit) => (
          <div key={hit.id} className="flex items-center gap-2">
            <Emblem url={hit.logo_url} />
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-sm text-[#F5F7FA]">{hit.name}</span>
              <span className="truncate text-xs text-[#8A94A6]">
                {[hit.city, hit.league_name, hit.division_name].filter(Boolean).join(' · ')}
              </span>
            </span>
            <Button
              type="button"
              className="shrink-0 !px-3 !py-1.5 !text-xs"
              disabled={invited.has(hit.id)}
              onClick={async () => {
                setError(null)
                try {
                  await onInvite(hit.id)
                  setInvited((prev) => new Set(prev).add(hit.id))
                } catch (err) {
                  setError(err instanceof ApiError ? err.message : 'Не удалось пригласить.')
                }
              }}
            >
              {invited.has(hit.id) ? 'Позвали' : 'Позвать'}
            </Button>
          </div>
        ))}
        {answeredQuery === query.trim() && query.trim().length >= 2 && hits.length === 0 && <p className="text-sm text-[#8A94A6]">Ничего не нашлось.</p>}
        <FormError message={error} />
      </div>
    </Modal>
  )
}
