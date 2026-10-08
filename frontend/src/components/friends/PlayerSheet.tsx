import { useEffect, useState } from 'react'
import * as friendsApi from '../../api/friends'
import * as usersApi from '../../api/users'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { FriendRelation, PlayerSuggestionRead } from '../../types/friend'
import type { UserPublicRead } from '../../types/user'
import { mutualLine } from '../../utils/friendSearch'
import { PublicPlayerCard } from '../PublicPlayerCard'
import { Button } from '../ui/Button'
import { FormError } from '../ui/FormError'
import { Modal } from '../ui/Modal'

export function FriendAction({
  relation,
  isSending,
  onAdd,
  wide = false,
}: {
  relation: FriendRelation
  isSending: boolean
  onAdd: () => void
  wide?: boolean
}) {
  if (relation === 'friend') {
    return (
      <span className="flex min-h-9 shrink-0 items-center justify-center gap-1 px-1.5 text-xs font-medium text-accent-ice">
        <i className="ti ti-check" aria-hidden="true" />В друзьях
      </span>
    )
  }
  if (relation === 'outgoing') {
    return (
      <span className="flex min-h-9 shrink-0 items-center justify-center rounded-full border border-white/15 px-3 text-xs text-text-secondary">
        Заявка отправлена
      </span>
    )
  }
  return (
    <Button
      type="button"
      onClick={onAdd}
      isLoading={isSending}
      className={wide ? 'w-full' : '!min-h-9 shrink-0 !rounded-full !px-3.5 !py-1.5 !text-xs'}
    >
      {relation === 'incoming' ? 'Принять заявку' : wide ? 'Добавить в друзья' : '+ В друзья'}
    </Button>
  )
}

// A player's card with the friend button (2026-10-08) -- from the friend
// search, the teammate/suggestion lists and the leaderboard. Loads who they
// are to me (GET /friends/players/{id}); a player hidden from strangers
// shows only their name and how else to reach them.
export function PlayerSheet({
  userId,
  title,
  onClose,
  onChanged,
}: {
  userId: string
  title: string
  onClose: () => void
  onChanged?: (relation: FriendRelation) => void
}) {
  const { accessToken } = useAuth()
  const [player, setPlayer] = useState<PlayerSuggestionRead | null>(null)
  const [profile, setProfile] = useState<UserPublicRead | null>(null)
  const [isHidden, setIsHidden] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isSending, setIsSending] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([friendsApi.getPlayer(userId, accessToken), usersApi.getUserPublicProfile(userId, accessToken)])
      .then(([found, card]) => {
        if (!cancelled) {
          setPlayer(found)
          setProfile(card)
        }
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return
        }
        if (err instanceof ApiError && err.status === 403) {
          setIsHidden(true)
        } else {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить карточку.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, userId])

  async function add() {
    if (accessToken === null || player === null) {
      return
    }
    setSendError(null)
    setIsSending(true)
    try {
      const sent = await friendsApi.sendFriendRequest({ user_id: player.id }, accessToken)
      const relation: FriendRelation = sent.status === 'accepted' ? 'friend' : 'outgoing'
      setPlayer({ ...player, relation })
      onChanged?.(relation)
    } catch (err) {
      setSendError(err instanceof ApiError ? err.message : 'Не удалось отправить заявку.')
    } finally {
      setIsSending(false)
    }
  }

  const mutual = player !== null ? mutualLine(player.mutual_friends) : null

  return (
    <Modal title={title} onClose={onClose}>
      <div className="flex flex-col items-center gap-4">
        <FormError message={loadError} />
        {isHidden && (
          <div className="flex flex-col items-center gap-2 py-4 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-dark-bg text-text-secondary">
              <i className="ti ti-lock text-2xl" aria-hidden="true" />
            </span>
            <p className="text-[15px] font-semibold">Игрок скрыл профиль</p>
            <p className="max-w-[280px] text-[13px] leading-relaxed text-text-secondary">
              Его карточку видят только друзья и сокомандники. Добавить его можно по ссылке или коду, которые он сам
              тебе отправит.
            </p>
          </div>
        )}
        {!isHidden && profile === null && loadError === null && (
          <p className="text-sm text-text-secondary">Загрузка...</p>
        )}
        {profile !== null && (
          <div className="w-full max-w-[340px]">
            <PublicPlayerCard profile={profile} />
          </div>
        )}
        {player !== null && (player.team_name !== null || mutual !== null) && (
          <p className="text-center text-[13px] text-text-secondary">
            {[player.team_name, mutual].filter(Boolean).join(' · ')}
          </p>
        )}
        {player !== null && (
          <div className="flex w-full justify-center">
            <FriendAction relation={player.relation} isSending={isSending} onAdd={() => void add()} wide />
          </div>
        )}
        <FormError message={sendError} />
        {player !== null && player.relation !== 'friend' && (
          <p className="text-center text-xs leading-relaxed text-text-secondary">
            Это заявка в друзья. Возраст и лента тренировок откроются, когда вы станете друзьями.
          </p>
        )}
      </div>
    </Modal>
  )
}
