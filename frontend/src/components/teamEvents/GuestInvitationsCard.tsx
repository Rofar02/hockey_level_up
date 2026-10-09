import { useEffect, useState } from 'react'
import * as teamEventsApi from '../../api/teamEvents'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { GuestInvitationRead } from '../../types/teamEvent'
import { Button } from '../ui/Button'
import { CARD_CLASS } from '../ui/cardStyle'
import { FormError } from '../ui/FormError'

function when(invitation: GuestInvitationRead): string {
  if (invitation.kind === 'slot') {
    return `каждую неделю: ${invitation.slot_label ?? ''}`
  }
  return invitation.starts_at !== null
    ? new Date(invitation.starts_at).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
    : ''
}

// The guest captain's invitations to joint trainings (release plan step
// 3.5). A training on a day the team already has its own: "Заменить ваш
// слот совместным?" -- accepting then cancels the own one, so nobody gets
// two ice sessions in a day.
export function GuestInvitationsCard({ teamId }: { teamId: string }) {
  const { accessToken } = useAuth()
  const [invitations, setInvitations] = useState<GuestInvitationRead[]>([])
  const [confirming, setConfirming] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    teamEventsApi.listGuestInvitations(teamId, accessToken).then(setInvitations).catch(() => {})
  }, [accessToken, teamId])

  if (invitations.length === 0) {
    return null
  }

  async function answer(invitation: GuestInvitationRead, accept: boolean, replaceOwn = false) {
    if (accessToken === null) {
      return
    }
    setError(null)
    if (accept && invitation.conflict && !replaceOwn) {
      setConfirming(invitation.id)
      return
    }
    try {
      await teamEventsApi.answerGuestInvitation(teamId, invitation.id, { accept, replace_own: replaceOwn }, accessToken)
      setInvitations((prev) => prev.filter((i) => i.id !== invitation.id))
      setConfirming(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось ответить.')
    }
  }

  return (
    <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">Зовут тренироваться вместе</span>
      {invitations.map((invitation) => (
        <div key={invitation.id} className="flex flex-col gap-2 border-t border-white/5 pt-2 first:border-t-0 first:pt-0">
          <span className="text-sm text-[#F5F7FA]">
            «{invitation.host_team_name}» — {when(invitation)}
          </span>
          {confirming === invitation.id ? (
            <div className="flex flex-col gap-2">
              <span className="text-xs text-accent-persimmon">
                В этот день у вас своя тренировка. Заменить её совместной? Ваша будет отменена.
              </span>
              <div className="flex gap-2">
                <Button type="button" className="!px-3 !py-1.5 !text-xs" onClick={() => answer(invitation, true, true)}>
                  Заменить
                </Button>
                <Button type="button" variant="neutral" className="!px-3 !py-1.5 !text-xs" onClick={() => setConfirming(null)}>
                  Отмена
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex gap-2">
              <Button type="button" className="!px-3 !py-1.5 !text-xs" onClick={() => answer(invitation, true)}>
                Принять
              </Button>
              <Button type="button" variant="neutral" className="!px-3 !py-1.5 !text-xs" onClick={() => answer(invitation, false)}>
                Отказаться
              </Button>
            </div>
          )}
        </div>
      ))}
      <FormError message={error} />
    </div>
  )
}
