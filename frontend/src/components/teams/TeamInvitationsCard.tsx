import { useEffect, useState } from 'react'
import * as teamsApi from '../../api/teams'
import { API_BASE_URL, ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { TeamInvitationRead } from '../../types/team'
import { Button } from '../ui/Button'
import { FormError } from '../ui/FormError'

// A captain's invitations to the player (2026-10-08), at the top of the
// team hub: accept -- straight into the team -- or decline.
export function TeamInvitationsCard({ onJoined }: { onJoined: (teamId: string) => void }) {
  const { accessToken } = useAuth()
  const [invitations, setInvitations] = useState<TeamInvitationRead[]>([])
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamsApi
      .listMyTeamInvitations(accessToken)
      .then((result) => !cancelled && setInvitations(result))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function respond(invitation: TeamInvitationRead, accept: boolean) {
    if (accessToken === null) {
      return
    }
    setError(null)
    setBusyId(invitation.id)
    try {
      if (accept) {
        await teamsApi.acceptTeamInvitation(invitation.id, accessToken)
      } else {
        await teamsApi.declineTeamInvitation(invitation.id, accessToken)
      }
      setInvitations((prev) => prev.filter((item) => item.id !== invitation.id))
      if (accept) {
        onJoined(invitation.team_id)
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось ответить на приглашение.')
    } finally {
      setBusyId(null)
    }
  }

  if (invitations.length === 0) {
    return null
  }
  return (
    <div className="flex flex-col gap-2">
      {invitations.map((invitation) => (
        <section
          key={invitation.id}
          className="flex flex-col gap-3 rounded-2xl border border-accent-persimmon/35 bg-accent-persimmon/[0.06] p-4"
        >
          <div className="flex items-center gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/15 bg-dark-card text-text-secondary">
              {invitation.team_logo_url !== null ? (
                <img src={`${API_BASE_URL}${invitation.team_logo_url}`} alt="" className="h-full w-full object-cover" />
              ) : (
                <i className="ti ti-shield text-2xl" aria-hidden="true" />
              )}
            </span>
            <span className="flex min-w-0 flex-col gap-0.5">
              <span className="text-[15px] font-semibold">
                {invitation.invited_by_first_name} {invitation.invited_by_last_name} зовёт тебя в «{invitation.team_name}»
              </span>
              <span className="text-xs text-text-secondary">{invitation.member_count} участн.</span>
            </span>
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              onClick={() => void respond(invitation, true)}
              isLoading={busyId === invitation.id}
              className="flex-1"
            >
              Вступить
            </Button>
            <Button
              type="button"
              variant="neutral"
              onClick={() => void respond(invitation, false)}
              disabled={busyId === invitation.id}
              className="flex-1"
            >
              Отклонить
            </Button>
          </div>
        </section>
      ))}
      <FormError message={error} />
    </div>
  )
}
