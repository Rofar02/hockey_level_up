import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { RankBadge } from '../components/ui/RankBadge'
import { PlayerSheet } from '../components/friends/PlayerSheet'
import { TabButton } from '../components/ui/TabButton'
import { AddFriendsTab } from '../components/friends/AddFriendsTab'
import * as friendsApi from '../api/friends'
import { API_BASE_URL, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { FriendRead, FriendRequestRead } from '../types/friend'
import type { ActivityFeedEntryRead } from '../types/friendActivity'
import type { LeaderboardEntryRead } from '../types/leaderboard'
import { DAY_SESSION_TYPE_LABELS } from '../types/schedule'
import { getDisplayName } from '../utils/displayName'

type FriendsTab = 'friends' | 'add' | 'feed' | 'leaderboard'

function formatRatingExcess(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}`
}

function formatActivityText(entry: ActivityFeedEntryRead): string {
  if (entry.event_type === 'level_up') {
    return `Достиг ${entry.level} уровня`
  }
  if (entry.event_type === 'party_completed') {
    const others = (entry.party_size ?? 2) - 1
    return `Потренировался вместе с ${others} ${others === 1 ? 'другом' : 'друзьями'}`
  }
  const label = entry.session_type !== null ? DAY_SESSION_TYPE_LABELS[entry.session_type] : 'тренировку'
  return `Завершил тренировку: ${label}`
}

function activityIcon(eventType: ActivityFeedEntryRead['event_type']): string {
  if (eventType === 'level_up') {
    return 'ti-trophy'
  }
  if (eventType === 'party_completed') {
    return 'ti-users'
  }
  return 'ti-check'
}

function formatActivityDate(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function FriendsPage() {
  const navigate = useNavigate()
  const { accessToken, user } = useAuth()
  // A tap on a leaderboard row opens the player's card (2026-10-08).
  const [openedPlayer, setOpenedPlayer] = useState<{ id: string; first_name: string; last_name: string } | null>(
    null,
  )

  const [activeTab, setActiveTab] = useState<FriendsTab>('friends')

  const [friends, setFriends] = useState<FriendRead[] | null>(null)
  const [incomingRequests, setIncomingRequests] = useState<FriendRequestRead[] | null>(null)
  const [feed, setFeed] = useState<ActivityFeedEntryRead[] | null>(null)
  const [rankings, setRankings] = useState<LeaderboardEntryRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [decidingIds, setDecidingIds] = useState<Set<string>>(new Set())
  const [actionError, setActionError] = useState<string | null>(null)

  async function refreshFriendsAndRequests() {
    if (accessToken === null) {
      return
    }
    const [friendsResult, requestsResult] = await Promise.all([
      friendsApi.listFriends(accessToken),
      friendsApi.listIncomingFriendRequests(accessToken),
    ])
    setFriends(friendsResult)
    setIncomingRequests(requestsResult)
  }

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    refreshFriendsAndRequests().catch((err: unknown) => {
      if (!cancelled) {
        setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить друзей.')
      }
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken])

  useEffect(() => {
    if (accessToken === null || activeTab !== 'feed' || feed !== null) {
      return
    }
    let cancelled = false
    friendsApi
      .getFriendActivityFeed(accessToken)
      .then((result) => {
        if (!cancelled) {
          setFeed(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить ленту.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, activeTab, feed])

  useEffect(() => {
    if (accessToken === null || activeTab !== 'leaderboard' || rankings !== null) {
      return
    }
    let cancelled = false
    friendsApi
      .getFriendLeaderboard(accessToken)
      .then((result) => {
        if (!cancelled) {
          setRankings(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить рейтинг.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, activeTab, rankings])

  async function handleDecide(request: FriendRequestRead, accept: boolean) {
    if (accessToken === null || decidingIds.has(request.id)) {
      return
    }
    setActionError(null)
    setDecidingIds((previous) => new Set(previous).add(request.id))
    try {
      if (accept) {
        await friendsApi.acceptFriendRequest(request.id, accessToken)
      } else {
        await friendsApi.declineFriendRequest(request.id, accessToken)
      }
      await refreshFriendsAndRequests()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось обработать заявку.')
    } finally {
      setDecidingIds((previous) => {
        const next = new Set(previous)
        next.delete(request.id)
        return next
      })
    }
  }

  async function handleRemoveFriend(friend: FriendRead) {
    if (accessToken === null) {
      return
    }
    if (!window.confirm(`Удалить ${getDisplayName(friend)} из друзей?`)) {
      return
    }
    setActionError(null)
    try {
      await friendsApi.removeFriend(friend.id, accessToken)
      await refreshFriendsAndRequests()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось удалить из друзей.')
    }
  }

  const isLoading = friends === null || incomingRequests === null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Друзья</h1>
        </div>

        <FormError message={loadError} />
        {isLoading && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {!isLoading && (
          <>
            <div className="flex border-b border-white/10">
              <TabButton active={activeTab === 'friends'} onClick={() => setActiveTab('friends')} badge={incomingRequests.length}>
                Друзья
              </TabButton>
              <TabButton active={activeTab === 'add'} onClick={() => setActiveTab('add')}>
                Добавить
              </TabButton>
              <TabButton active={activeTab === 'feed'} onClick={() => setActiveTab('feed')}>
                Лента
              </TabButton>
              <TabButton active={activeTab === 'leaderboard'} onClick={() => setActiveTab('leaderboard')}>
                Рейтинг
              </TabButton>
            </div>

            {activeTab === 'friends' && (
              <div className="flex flex-col gap-6">
                <div className="flex flex-col gap-2">
                  {friends.length === 0 && (
                    <EmptyState
                      icon="ti-users"
                      title="У вас пока нет друзей"
                      hint="Добавьте друзей во вкладке «Добавить» — так вы сможете сравнивать статы и звать на тренировки"
                    />
                  )}
                  {friends.map((friend) => (
                    <div key={friend.id} className={`flex items-center gap-3 p-3 ${CARD_CLASS}`}>
                      <button
                        type="button"
                        onClick={() => navigate(`/profile/${friend.id}`)}
                        className="flex min-w-0 flex-1 items-center gap-3 text-left"
                      >
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-accent-ice bg-dark-bg">
                          {friend.avatar_url !== null ? (
                            <img
                              src={`${API_BASE_URL}${friend.avatar_url}`}
                              alt=""
                              className="h-full w-full object-cover"
                            />
                          ) : (
                            <i className="ti ti-user text-lg text-[#8A94A6]" aria-hidden="true" />
                          )}
                        </div>
                        <div className="flex min-w-0 flex-col">
                          <span className="truncate text-sm font-medium text-[#F5F7FA]">
                            {getDisplayName(friend)}
                          </span>
                          <span className="text-xs text-[#8A94A6]">Уровень {friend.level}</span>
                        </div>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRemoveFriend(friend)}
                        aria-label={`Удалить из друзей: ${getDisplayName(friend)}`}
                        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[#8A94A6] transition-colors hover:bg-white/5 hover:text-accent-persimmon"
                      >
                        <i className="ti ti-user-x text-sm" aria-hidden="true" />
                      </button>
                    </div>
                  ))}
                </div>

                {incomingRequests.length > 0 && (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">
                      Заявки в друзья
                    </p>
                    {incomingRequests.map((request) => (
                      <div
                        key={request.id}
                        className={`flex items-center justify-between gap-4 p-4 ${CARD_CLASS}`}
                      >
                        <button
                          type="button"
                          onClick={() => navigate(`/profile/${request.sender_id}`)}
                          className="min-w-0 truncate text-left text-sm text-[#F5F7FA] hover:underline"
                        >
                          {getDisplayName({
                            first_name: request.sender_first_name,
                            last_name: request.sender_last_name,
                          })}
                        </button>
                        <div className="flex shrink-0 gap-2">
                          <Button
                            type="button"
                            isLoading={decidingIds.has(request.id)}
                            onClick={() => handleDecide(request, true)}
                            className="!px-3 !py-1.5 !text-xs"
                          >
                            Принять
                          </Button>
                          <Button
                            type="button"
                            variant="neutral"
                            disabled={decidingIds.has(request.id)}
                            onClick={() => handleDecide(request, false)}
                            className="!px-3 !py-1.5 !text-xs"
                          >
                            Отклонить
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <FormError message={actionError} />
              </div>
            )}

            {activeTab === 'add' && (
              <AddFriendsTab onFriendsChanged={() => refreshFriendsAndRequests().catch(() => undefined)} />
            )}

            {activeTab === 'feed' &&
              (feed === null ? (
                <p className="text-sm text-[#8A94A6]">Загрузка...</p>
              ) : feed.length === 0 ? (
                <EmptyState
                  icon="ti-activity"
                  title="Пока в ленте ничего нет"
                  hint="Здесь появятся тренировки и достижения ваших друзей"
                />
              ) : (
                <div className="flex flex-col gap-2">
                  {feed.map((entry) => (
                    <button
                      key={entry.id}
                      type="button"
                      onClick={() => navigate(`/profile/${entry.user_id}`)}
                      className={`flex w-full items-center gap-3 p-3 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
                    >
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/10 bg-dark-bg">
                        {entry.avatar_url !== null ? (
                          <img src={`${API_BASE_URL}${entry.avatar_url}`} alt="" className="h-full w-full object-cover" />
                        ) : (
                          <i className="ti ti-user text-base text-[#8A94A6]" aria-hidden="true" />
                        )}
                      </div>
                      <div className="flex min-w-0 flex-1 flex-col">
                        <span className="truncate text-sm text-[#F5F7FA]">
                          <span className="font-medium">{getDisplayName(entry)}</span> — {formatActivityText(entry)}
                        </span>
                        <span className="text-xs text-[#8A94A6]">{formatActivityDate(entry.created_at)}</span>
                      </div>
                      <i
                        className={`ti ${activityIcon(entry.event_type)} shrink-0 text-accent-ice`}
                        aria-hidden="true"
                      />
                    </button>
                  ))}
                </div>
              ))}

            {activeTab === 'leaderboard' &&
              (rankings === null ? (
                <p className="text-sm text-[#8A94A6]">Загрузка...</p>
              ) : rankings.length === 0 ? (
                <EmptyState
                  icon="ti-trophy"
                  title="Пока никто не попал в рейтинг"
                  hint="Рейтинг появится, как только у друзей накопится статистика"
                />
              ) : (
                <div className="flex flex-col gap-2">
                  {rankings.map((entry, index) => (
                    <button
                      key={entry.id}
                      type="button"
                      onClick={() => (entry.id === user?.id ? navigate('/profile') : setOpenedPlayer(entry))}
                      aria-label={`Открыть карточку: ${getDisplayName(entry)}`}
                      className={`flex w-full items-center gap-3 p-3 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
                    >
                      <RankBadge rank={index + 1} />
                      <span className="min-w-0 flex-1 truncate text-sm text-[#F5F7FA]">
                        {getDisplayName(entry)}
                      </span>
                      <span
                        className={`shrink-0 font-mono text-sm font-bold ${
                          entry.rating_excess > 0 ? 'text-accent-ice' : 'text-[#8A94A6]'
                        }`}
                      >
                        {formatRatingExcess(entry.rating_excess)}
                      </span>
                    </button>
                  ))}
                  {openedPlayer !== null && (
                    <PlayerSheet
                      userId={openedPlayer.id}
                      title={getDisplayName(openedPlayer)}
                      onClose={() => setOpenedPlayer(null)}
                    />
                  )}
                </div>
              ))}
          </>
        )}
      </div>
    </div>
  )
}
