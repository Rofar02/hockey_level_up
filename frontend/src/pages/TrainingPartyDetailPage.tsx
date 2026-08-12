import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { ProgressBar } from '../components/ui/ProgressBar'
import * as scheduleApi from '../api/schedule'
import * as trainingPartiesApi from '../api/trainingParties'
import { API_BASE_URL, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { TrainingPartyDetailRead, TrainingPartyMemberRead } from '../types/trainingParty'
import { formatShortDate, parseIsoDate } from '../utils/date'
import { getDisplayName } from '../utils/displayName'

// Same icy top-border card convention as Friends/Teams/Profile.
const CARD_CLASS = 'rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-card'

// Refresh while the party is still open -- everyone's training on their own
// schedule, so this is the only way to see live progress without websockets.
const POLL_INTERVAL_MS = 8000

export function TrainingPartyDetailPage() {
  const { partyId } = useParams<{ partyId: string }>()
  const navigate = useNavigate()
  const { user, accessToken } = useAuth()

  const [party, setParty] = useState<TrainingPartyDetailRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyUserId, setBusyUserId] = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const [isLeaving, setIsLeaving] = useState(false)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function refresh() {
    if (accessToken === null || partyId === undefined) {
      return
    }
    const result = await trainingPartiesApi.getTrainingParty(partyId, accessToken)
    setParty(result)
    return result
  }

  useEffect(() => {
    if (accessToken === null || partyId === undefined) {
      return
    }
    let cancelled = false
    refresh().catch((err: unknown) => {
      if (!cancelled) {
        setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить тренировку.')
      }
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, partyId])

  useEffect(() => {
    if (party?.status !== 'pending') {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      return
    }
    pollRef.current = setInterval(() => {
      refresh().catch(() => {
        // Best-effort background refresh -- a transient failure just tries
        // again on the next tick, no need to surface a banner for it.
      })
    }, POLL_INTERVAL_MS)
    return () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [party?.status])

  async function handleDecide(accept: boolean) {
    if (accessToken === null || partyId === undefined || user === null) {
      return
    }
    setActionError(null)
    setBusyUserId(user.id)
    try {
      if (accept) {
        await trainingPartiesApi.acceptTrainingPartyInvite(partyId, accessToken)
      } else {
        await trainingPartiesApi.declineTrainingPartyInvite(partyId, accessToken)
      }
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось обработать приглашение.')
    } finally {
      setBusyUserId(null)
    }
  }

  async function handleSwapRestToTraining() {
    if (accessToken === null || party === null) {
      return
    }
    if (
      !window.confirm(
        'Отдых — часть вашего восстановления по плану. Точно заменить его на тренировку, чтобы присоединиться?',
      )
    ) {
      return
    }
    setActionError(null)
    setBusyUserId(user?.id ?? null)
    try {
      const result = await scheduleApi.patchCurrentWeeklyPlan(
        { days: [{ date: party.target_date, session_type: 'off_ice' }] },
        accessToken,
      )
      if (result.conflicts.length > 0) {
        setActionError(result.conflicts[0].detail)
      } else {
        await refresh()
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // The exact case we designed for: no WeeklyPlan covers this date at
        // all yet -- point at the fix instead of surfacing a raw 404.
        setActionError('Сначала сформируйте план на эту неделю (Расписание → Новая неделя), затем попробуйте ещё раз.')
      } else {
        setActionError(err instanceof ApiError ? err.message : 'Не удалось заменить отдых на тренировку.')
      }
    } finally {
      setBusyUserId(null)
    }
  }

  async function handleCancel() {
    if (accessToken === null || partyId === undefined || party === null) {
      return
    }
    if (!window.confirm('Отменить эту совместную тренировку?')) {
      return
    }
    setActionError(null)
    setIsCancelling(true)
    try {
      await trainingPartiesApi.cancelTrainingParty(partyId, accessToken)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось отменить тренировку.')
    } finally {
      setIsCancelling(false)
    }
  }

  async function handleLeave() {
    if (accessToken === null || partyId === undefined) {
      return
    }
    if (!window.confirm('Выйти из совместной тренировки?')) {
      return
    }
    setActionError(null)
    setIsLeaving(true)
    try {
      await trainingPartiesApi.leaveTrainingParty(partyId, accessToken)
      navigate('/training-parties', { replace: true })
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось выйти из тренировки.')
    } finally {
      setIsLeaving(false)
    }
  }

  const isLoading = party === null
  const isCreator = party !== null && user !== null && party.created_by === user.id
  const myMember = party?.members.find((member) => member.user_id === user?.id) ?? null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <BackLink to="/training-parties" />

        <FormError message={loadError} />
        {isLoading && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {party !== null && (
          <>
            <StatusBanner party={party} />

            <div className="flex flex-col gap-2">
              {party.members.map((member) => (
                <MemberCard
                  key={member.user_id}
                  member={member}
                  isSelf={member.user_id === user?.id}
                  isBusy={busyUserId === member.user_id}
                  showActions={party.status === 'pending'}
                  onAccept={() => handleDecide(true)}
                  onDecline={() => handleDecide(false)}
                  onSwapRestToTraining={handleSwapRestToTraining}
                  onGoToTraining={() => navigate(`/training/${member.day_plan_id}`)}
                  onGeneratePlan={() => navigate('/schedule/new')}
                />
              ))}
            </div>

            <FormError message={actionError} />

            {party.status === 'pending' && (
              <div className="flex flex-col gap-2">
                {isCreator ? (
                  <Button
                    type="button"
                    variant="neutral"
                    isLoading={isCancelling}
                    onClick={handleCancel}
                    className="self-start"
                  >
                    Отменить тренировку
                  </Button>
                ) : myMember?.membership_status === 'joined' ? (
                  <Button
                    type="button"
                    variant="neutral"
                    isLoading={isLeaving}
                    onClick={handleLeave}
                    className="self-start"
                  >
                    Выйти
                  </Button>
                ) : null}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function StatusBanner({ party }: { party: TrainingPartyDetailRead }) {
  const dateLabel = formatShortDate(parseIsoDate(party.target_date))

  if (party.status === 'completed') {
    return (
      <div className={`flex items-center gap-3 p-4 ${CARD_CLASS} border-accent-ice/40`}>
        <i className="ti ti-confetti text-2xl text-accent-ice" aria-hidden="true" />
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-[#F5F7FA]">Все потренировались вместе!</span>
          <span className="text-xs text-[#8A94A6]">{dateLabel}</span>
        </div>
      </div>
    )
  }

  const labels: Record<string, string> = {
    pending: 'Совместная тренировка',
    cancelled: 'Тренировка отменена',
    expired: 'Тренировка не состоялась',
  }

  return (
    <div className="flex flex-col gap-1">
      <h1 className="text-xl font-semibold">{labels[party.status] ?? 'Совместная тренировка'}</h1>
      <p className="text-sm text-[#8A94A6]">{dateLabel}</p>
    </div>
  )
}

function MemberCard({
  member,
  isSelf,
  isBusy,
  showActions,
  onAccept,
  onDecline,
  onSwapRestToTraining,
  onGoToTraining,
  onGeneratePlan,
}: {
  member: TrainingPartyMemberRead
  isSelf: boolean
  isBusy: boolean
  // False once the party is no longer pending (completed/cancelled/expired)
  // -- accept/decline, swap-rest, and start/continue all stop being
  // meaningful actions at that point, even though the member's own
  // training_status value (e.g. "not_started") wouldn't otherwise hide them.
  showActions: boolean
  onAccept: () => void
  onDecline: () => void
  onSwapRestToTraining: () => void
  onGoToTraining: () => void
  onGeneratePlan: () => void
}) {
  const dimmed = member.membership_status === 'declined'

  return (
    <div className={`flex items-center gap-3 p-3 ${CARD_CLASS} ${dimmed ? 'opacity-50' : ''}`}>
      <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/10 bg-dark-bg">
        {member.avatar_url !== null ? (
          <img src={`${API_BASE_URL}${member.avatar_url}`} alt="" className="h-full w-full object-cover" />
        ) : (
          <i className="ti ti-user text-lg text-[#8A94A6]" aria-hidden="true" />
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="truncate text-sm font-medium text-[#F5F7FA]">
          {getDisplayName(member)}
          {isSelf ? ' (вы)' : ''}
        </span>
        <MemberStatusRow member={member} />
      </div>

      {showActions && (
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {isSelf && member.membership_status === 'invited' && (
            <div className="flex gap-2">
              <Button type="button" isLoading={isBusy} onClick={onAccept} className="!px-3 !py-1.5 !text-xs">
                Принять
              </Button>
              <Button
                type="button"
                variant="neutral"
                disabled={isBusy}
                onClick={onDecline}
                className="!px-3 !py-1.5 !text-xs"
              >
                Отклонить
              </Button>
            </div>
          )}
          {isSelf && member.training_status === 'resting' && (
            <Button
              type="button"
              variant="neutral"
              isLoading={isBusy}
              onClick={onSwapRestToTraining}
              className="!px-3 !py-1.5 !text-xs"
            >
              Заменить на тренировку
            </Button>
          )}
          {isSelf && member.training_status === 'no_plan_for_date' && (
            <Button type="button" variant="neutral" onClick={onGeneratePlan} className="!px-3 !py-1.5 !text-xs">
              Сформировать план
            </Button>
          )}
          {isSelf &&
            (member.training_status === 'not_started' || member.training_status === 'in_progress') && (
              <Button type="button" onClick={onGoToTraining} className="!px-3 !py-1.5 !text-xs">
                {member.training_status === 'not_started' ? 'Начать' : 'Продолжить'}
              </Button>
            )}
        </div>
      )}
    </div>
  )
}

function MemberStatusRow({ member }: { member: TrainingPartyMemberRead }) {
  if (member.membership_status === 'invited') {
    return <span className="text-xs text-[#8A94A6]">Ещё не ответил(а)</span>
  }
  if (member.membership_status === 'declined') {
    return <span className="text-xs text-[#8A94A6]">Отклонил(а) приглашение</span>
  }

  switch (member.training_status) {
    case 'no_plan_for_date':
      return <span className="text-xs text-[#8A94A6]">План на эту неделю ещё не сформирован</span>
    case 'resting':
      return (
        <span className="flex items-center gap-1 text-xs text-[#8A94A6]">
          <i className="ti ti-moon" aria-hidden="true" />
          Отдыхает сегодня
        </span>
      )
    case 'game_day':
      return (
        <span className="flex items-center gap-1 text-xs text-[#8A94A6]">
          <i className="ti ti-shirt-sport" aria-hidden="true" />
          Игровой день
        </span>
      )
    case 'not_started':
      return <span className="text-xs text-[#8A94A6]">Ещё не начал(а)</span>
    case 'in_progress':
      return (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-accent-ice">
            {member.completed_blocks}/{member.total_blocks} блоков
          </span>
          <div className="w-32">
            <ProgressBar value={member.completed_blocks ?? 0} max={member.total_blocks ?? 1} />
          </div>
        </div>
      )
    case 'completed':
      return (
        <span className="flex items-center gap-1 text-xs font-medium text-accent-ice">
          <i className="ti ti-circle-check-filled" aria-hidden="true" />
          Завершил(а) тренировку
        </span>
      )
    default:
      return null
  }
}
