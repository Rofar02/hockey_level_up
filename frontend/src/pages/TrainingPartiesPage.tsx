import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { Checkbox } from '../components/ui/Checkbox'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { TabButton } from '../components/ui/TabButton'
import { TextField } from '../components/ui/TextField'
import * as friendsApi from '../api/friends'
import * as trainingPartiesApi from '../api/trainingParties'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { FriendRead } from '../types/friend'
import type {
  TrainingPartyInviteRead,
  TrainingPartyStatus,
  TrainingPartySummaryRead,
} from '../types/trainingParty'
import { formatShortDate, parseIsoDate, toIsoDate } from '../utils/date'
import { getDisplayName } from '../utils/displayName'

// Same icy top-border card convention as Friends/Teams/Leaderboard.
const CARD_CLASS = 'rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-card'

type PartiesTab = 'mine' | 'invites' | 'create'

const STATUS_LABELS: Record<TrainingPartyStatus, string> = {
  pending: 'Скоро',
  completed: 'Завершена',
  cancelled: 'Отменена',
  expired: 'Не состоялась',
}

const STATUS_DOT_CLASS: Record<TrainingPartyStatus, string> = {
  pending: 'bg-accent-ice',
  completed: 'bg-accent-ice',
  cancelled: 'bg-[#8A94A6]',
  expired: 'bg-[#8A94A6]',
}

export function TrainingPartiesPage() {
  const navigate = useNavigate()
  const { accessToken } = useAuth()

  const [activeTab, setActiveTab] = useState<PartiesTab>('mine')

  const [parties, setParties] = useState<TrainingPartySummaryRead[] | null>(null)
  const [invites, setInvites] = useState<TrainingPartyInviteRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [decidingIds, setDecidingIds] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)

  const [friends, setFriends] = useState<FriendRead[] | null>(null)
  const [targetDate, setTargetDate] = useState(toIsoDate(new Date()))
  const [selectedFriendIds, setSelectedFriendIds] = useState<Set<string>>(new Set())
  const [isCreating, setIsCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  async function refresh() {
    if (accessToken === null) {
      return
    }
    const [partiesResult, invitesResult] = await Promise.all([
      trainingPartiesApi.listMyTrainingParties(accessToken),
      trainingPartiesApi.listIncomingTrainingPartyInvites(accessToken),
    ])
    setParties(partiesResult)
    setInvites(invitesResult)
  }

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    refresh().catch((err: unknown) => {
      if (!cancelled) {
        setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить тренировки.')
      }
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken])

  useEffect(() => {
    if (accessToken === null || activeTab !== 'create' || friends !== null) {
      return
    }
    let cancelled = false
    friendsApi
      .listFriends(accessToken)
      .then((result) => {
        if (!cancelled) {
          setFriends(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить друзей.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, activeTab, friends])

  async function handleDecide(invite: TrainingPartyInviteRead, accept: boolean) {
    if (accessToken === null || decidingIds.has(invite.party_id)) {
      return
    }
    setActionError(null)
    setDecidingIds((previous) => new Set(previous).add(invite.party_id))
    try {
      if (accept) {
        await trainingPartiesApi.acceptTrainingPartyInvite(invite.party_id, accessToken)
      } else {
        await trainingPartiesApi.declineTrainingPartyInvite(invite.party_id, accessToken)
      }
      await refresh()
      if (accept) {
        navigate(`/training-parties/${invite.party_id}`)
      }
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось обработать приглашение.')
    } finally {
      setDecidingIds((previous) => {
        const next = new Set(previous)
        next.delete(invite.party_id)
        return next
      })
    }
  }

  function toggleFriend(friendId: string) {
    setSelectedFriendIds((previous) => {
      const next = new Set(previous)
      if (next.has(friendId)) {
        next.delete(friendId)
      } else {
        next.add(friendId)
      }
      return next
    })
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null || selectedFriendIds.size === 0) {
      return
    }
    setCreateError(null)
    setIsCreating(true)
    try {
      const created = await trainingPartiesApi.createTrainingParty(
        { target_date: targetDate, friend_ids: [...selectedFriendIds] },
        accessToken,
      )
      navigate(`/training-parties/${created.id}`)
    } catch (err) {
      setCreateError(err instanceof ApiError ? err.message : 'Не удалось создать тренировку.')
    } finally {
      setIsCreating(false)
    }
  }

  const isLoading = parties === null || invites === null
  const todayIso = toIsoDate(new Date())

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Совместные тренировки</h1>
        </div>

        <FormError message={loadError} />
        {isLoading && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {!isLoading && (
          <>
            <div className="flex border-b border-white/10">
              <TabButton active={activeTab === 'mine'} onClick={() => setActiveTab('mine')}>
                Мои
              </TabButton>
              <TabButton
                active={activeTab === 'invites'}
                onClick={() => setActiveTab('invites')}
                badge={invites.length}
              >
                Приглашения
              </TabButton>
              <TabButton active={activeTab === 'create'} onClick={() => setActiveTab('create')}>
                Позвать
              </TabButton>
            </div>

            {activeTab === 'mine' && (
              <div className="flex flex-col gap-2">
                {parties.length === 0 && (
                  <p className="text-sm text-[#8A94A6]">
                    Пока нет совместных тренировок — позовите друга во вкладке «Позвать».
                  </p>
                )}
                {parties.map((party) => (
                  <button
                    key={party.id}
                    type="button"
                    onClick={() => navigate(`/training-parties/${party.id}`)}
                    className={`flex w-full items-center gap-3 p-4 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
                  >
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/10 bg-dark-bg">
                      <i className="ti ti-users text-lg text-[#8A94A6]" aria-hidden="true" />
                    </div>
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate text-sm font-medium text-[#F5F7FA]">
                        {formatShortDate(parseIsoDate(party.target_date))} ·{' '}
                        {party.member_count}{' '}
                        {party.member_count === 1 ? 'участник' : 'участника'}
                      </span>
                      <span className="flex items-center gap-1.5 text-xs text-[#8A94A6]">
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT_CLASS[party.status]}`}
                          aria-hidden="true"
                        />
                        {STATUS_LABELS[party.status]}
                        {party.is_creator ? ' · вы позвали' : ''}
                      </span>
                    </div>
                    <i className="ti ti-chevron-right shrink-0 text-[#8A94A6]" aria-hidden="true" />
                  </button>
                ))}
              </div>
            )}

            {activeTab === 'invites' && (
              <div className="flex flex-col gap-2">
                {invites.length === 0 && (
                  <p className="text-sm text-[#8A94A6]">Нет входящих приглашений.</p>
                )}
                {invites.map((invite) => (
                  <div
                    key={invite.party_id}
                    className={`flex items-center justify-between gap-4 p-4 ${CARD_CLASS}`}
                  >
                    <div className="flex min-w-0 flex-col gap-0.5">
                      <span className="truncate text-sm text-[#F5F7FA]">
                        <span className="font-medium">
                          {getDisplayName({
                            first_name: invite.created_by_first_name,
                            last_name: invite.created_by_last_name,
                          })}
                        </span>{' '}
                        зовёт на тренировку
                      </span>
                      <span className="text-xs text-[#8A94A6]">
                        {formatShortDate(parseIsoDate(invite.target_date))} · {invite.member_count}{' '}
                        {invite.member_count === 1 ? 'участник' : 'участника'}
                      </span>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        type="button"
                        isLoading={decidingIds.has(invite.party_id)}
                        onClick={() => handleDecide(invite, true)}
                        className="!px-3 !py-1.5 !text-xs"
                      >
                        Принять
                      </Button>
                      <Button
                        type="button"
                        variant="neutral"
                        disabled={decidingIds.has(invite.party_id)}
                        onClick={() => handleDecide(invite, false)}
                        className="!px-3 !py-1.5 !text-xs"
                      >
                        Отклонить
                      </Button>
                    </div>
                  </div>
                ))}
                <FormError message={actionError} />
              </div>
            )}

            {activeTab === 'create' && (
              <form onSubmit={handleCreate} className="flex flex-col gap-4">
                <TextField
                  label="Дата"
                  type="date"
                  min={todayIso}
                  value={targetDate}
                  onChange={(event) => setTargetDate(event.target.value)}
                />

                <div className="flex flex-col gap-2">
                  <span className="text-sm text-text-secondary">Кого позвать</span>
                  {friends === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}
                  {friends !== null && friends.length === 0 && (
                    <p className="text-sm text-[#8A94A6]">
                      Сначала добавьте друзей — без них звать некого.
                    </p>
                  )}
                  {friends !== null &&
                    friends.map((friend) => (
                      <button
                        key={friend.id}
                        type="button"
                        onClick={() => toggleFriend(friend.id)}
                        className={`flex items-center gap-3 p-3 text-left ${CARD_CLASS}`}
                      >
                        {/* Presentational only -- the row's own onClick above
                            already toggles selection; giving Checkbox its own
                            onClick too would double-fire (click bubbles from
                            it to the row) and cancel itself out. */}
                        <Checkbox checked={selectedFriendIds.has(friend.id)} />
                        <span className="min-w-0 flex-1 truncate text-sm text-[#F5F7FA]">
                          {getDisplayName(friend)}
                        </span>
                      </button>
                    ))}
                </div>

                <Button
                  type="submit"
                  isLoading={isCreating}
                  disabled={selectedFriendIds.size === 0}
                  className="self-start"
                >
                  Позвать
                </Button>
                <FormError message={createError} />
              </form>
            )}
          </>
        )}
      </div>
    </div>
  )
}
