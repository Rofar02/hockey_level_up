import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import * as friendsApi from '../../api/friends'
import * as usersApi from '../../api/users'
import { API_BASE_URL, ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { FriendRelation, PlayerSuggestionRead } from '../../types/friend'
import { POSITION_LABELS } from '../../types/user'
import type { UserPublicRead } from '../../types/user'
import { copyText } from '../../utils/clipboard'
import { PublicPlayerCard } from '../PublicPlayerCard'
import { Button } from '../ui/Button'
import { FormError } from '../ui/FormError'
import { Modal } from '../ui/Modal'

const SEARCH_DELAY_MS = 400
const TEAMMATES_SHOWN = 3

// Same rule as the server's search_tokens: a first and a last name, two
// letters each.
export function isSearchable(query: string): boolean {
  const words = query.trim().split(/\s+/)
  return words.length >= 2 && words.slice(0, 2).every((word) => word.length >= 2)
}

export function inviteLink(code: string): string {
  return `${window.location.origin}/f/${code}`
}

function metaLine(player: PlayerSuggestionRead, withTeam: boolean): string {
  return [
    withTeam ? (player.team_name ?? 'Без команды') : player.jersey_number !== null ? `#${player.jersey_number}` : null,
    player.position !== null ? POSITION_LABELS[player.position] : null,
    `ур. ${player.level}`,
  ]
    .filter(Boolean)
    .join(' · ')
}

function mutualLine(count: number): string | null {
  if (count === 0) {
    return null
  }
  const mod10 = count % 10
  const mod100 = count % 100
  const word = mod10 === 1 && mod100 !== 11 ? 'общий друг' : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? 'общих друга' : 'общих друзей'
  return `${count} ${word}`
}

// The "Добавить" tab (2026-10-08): find by name, teammates, friends of
// friends, and the invite link -- the code stays at the bottom. A tap on a
// player opens their card; the button sends the request right away.
export function AddFriendsTab({ onFriendsChanged }: { onFriendsChanged: () => Promise<void> | void }) {
  const { user, accessToken } = useAuth()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<PlayerSuggestionRead[] | null>(null)
  const [searchError, setSearchError] = useState<string | null>(null)
  const [teammates, setTeammates] = useState<PlayerSuggestionRead[] | null>(null)
  const [suggestions, setSuggestions] = useState<PlayerSuggestionRead[]>([])
  const [showAllTeammates, setShowAllTeammates] = useState(false)
  // Requests sent from this tab, so the button changes without a refetch.
  const [sentTo, setSentTo] = useState<Record<string, FriendRelation>>({})
  const [sendingId, setSendingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [opened, setOpened] = useState<PlayerSuggestionRead | null>(null)

  const [code, setCode] = useState('')
  const [isSendingCode, setIsSendingCode] = useState(false)
  const [codeError, setCodeError] = useState<string | null>(null)
  const [codeSuccess, setCodeSuccess] = useState<string | null>(null)
  const [linkState, setLinkState] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    void Promise.all([
      friendsApi.listTeammatesToAdd(accessToken).catch(() => []),
      friendsApi.listFriendSuggestions(accessToken).catch(() => []),
    ]).then(([mates, others]) => {
      if (!cancelled) {
        setTeammates(mates)
        setSuggestions(others)
      }
    })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const searching = query.trim() !== ''
  const searchable = isSearchable(query)

  useEffect(() => {
    if (accessToken === null || !searchable) {
      setResults(null)
      setSearchError(null)
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      friendsApi
        .searchPlayers(query.trim(), accessToken)
        .then((found) => {
          if (!cancelled) {
            setResults(found)
            setSearchError(null)
          }
        })
        .catch((err: unknown) => {
          if (!cancelled) {
            setResults(null)
            setSearchError(err instanceof ApiError ? err.message : 'Не удалось выполнить поиск.')
          }
        })
    }, SEARCH_DELAY_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [accessToken, query, searchable])

  function relationOf(player: PlayerSuggestionRead): FriendRelation {
    return sentTo[player.id] ?? player.relation
  }

  async function addPlayer(player: PlayerSuggestionRead) {
    if (accessToken === null) {
      return
    }
    setActionError(null)
    setSendingId(player.id)
    try {
      const sent = await friendsApi.sendFriendRequest({ user_id: player.id }, accessToken)
      setSentTo((prev) => ({ ...prev, [player.id]: sent.status === 'accepted' ? 'friend' : 'outgoing' }))
      await onFriendsChanged()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось отправить заявку.')
    } finally {
      setSendingId(null)
    }
  }

  async function shareLink() {
    if (user?.friend_code == null) {
      return
    }
    const url = inviteLink(user.friend_code)
    setLinkState(null)
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share({ title: 'IceLevel', text: 'Добавляйся в друзья в IceLevel', url })
        return
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return
        }
      }
    }
    setLinkState((await copyText(url)) ? 'Ссылка скопирована' : 'Не удалось скопировать — выделите ссылку вручную')
  }

  async function copyLink() {
    if (user?.friend_code == null) {
      return
    }
    setLinkState((await copyText(inviteLink(user.friend_code))) ? 'Ссылка скопирована' : 'Не удалось скопировать — выделите ссылку вручную')
  }

  async function sendByCode(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null || code.trim() === '') {
      return
    }
    setCodeError(null)
    setCodeSuccess(null)
    setIsSendingCode(true)
    try {
      const sent = await friendsApi.sendFriendRequest({ code: code.trim().toUpperCase() }, accessToken)
      setCode('')
      setCodeSuccess(
        sent.status === 'accepted'
          ? `Вы теперь друзья с ${sent.receiver_first_name} ${sent.receiver_last_name}`
          : `Заявка отправлена: ${sent.receiver_first_name} ${sent.receiver_last_name}`,
      )
      await onFriendsChanged()
    } catch (err) {
      setCodeError(err instanceof ApiError ? err.message : 'Не удалось отправить заявку.')
    } finally {
      setIsSendingCode(false)
    }
  }

  const row = (player: PlayerSuggestionRead, meta: string) => (
    <PlayerRow
      key={player.id}
      player={player}
      meta={meta}
      relation={relationOf(player)}
      isSending={sendingId === player.id}
      onOpen={() => setOpened(player)}
      onAdd={() => void addPlayer(player)}
    />
  )

  const visibleTeammates = showAllTeammates ? (teammates ?? []) : (teammates ?? []).slice(0, TEAMMATES_SHOWN)
  const teamTitle = teammates !== null && teammates.length > 0 ? teammates[0].team_name : null

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <label className="flex min-h-12 items-center gap-2.5 rounded-xl border border-white/10 bg-dark-card px-3.5 focus-within:border-accent-ice">
          <i className="ti ti-search text-lg text-text-secondary" aria-hidden="true" />
          <span className="sr-only">Найти по имени и фамилии</span>
          <input
            type="text"
            inputMode="search"
            enterKeyHint="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Найти по имени и фамилии"
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-[15px] text-text-primary outline-none placeholder:text-text-secondary"
          />
          {searching && (
            <button
              type="button"
              onClick={() => setQuery('')}
              aria-label="Очистить поиск"
              className="flex h-8 w-8 items-center justify-center rounded-full text-text-secondary hover:text-text-primary"
            >
              <i className="ti ti-x" aria-hidden="true" />
            </button>
          )}
        </label>
        {user !== null && !user.findable_by_name && (
          <p className="flex items-center gap-2 px-1 text-xs text-text-secondary">
            Тебя самого сейчас не найти по имени ·
            <Link to="/settings/privacy" className="font-medium text-accent-ice">
              Изменить
            </Link>
          </p>
        )}
      </div>

      <FormError message={actionError} />

      {searching ? (
        <SearchResults
          searchable={searchable}
          results={results}
          error={searchError}
          renderRow={(player) => row(player, metaLine(player, true))}
          onShareLink={() => void shareLink()}
        />
      ) : (
        <>
          {teammates !== null && teammates.length > 0 && (
            <section className="flex flex-col gap-2">
              <h2 className="text-xs font-medium uppercase tracking-wide text-text-secondary">
                Из твоей команды{teamTitle !== null ? ` · ${teamTitle}` : ''}
              </h2>
              {visibleTeammates.map((player) => row(player, metaLine(player, false)))}
              {!showAllTeammates && teammates.length > TEAMMATES_SHOWN && (
                <button
                  type="button"
                  onClick={() => setShowAllTeammates(true)}
                  className="min-h-10 self-start px-1 text-sm font-medium text-accent-ice"
                >
                  Показать всех · ещё {teammates.length - TEAMMATES_SHOWN}
                </button>
              )}
            </section>
          )}

          {suggestions.length > 0 && (
            <section className="flex flex-col gap-2">
              <h2 className="text-xs font-medium uppercase tracking-wide text-text-secondary">Возможно, знакомы</h2>
              {suggestions.map((player) =>
                row(player, [player.team_name ?? 'Без команды', mutualLine(player.mutual_friends)].filter(Boolean).join(' · ')),
              )}
            </section>
          )}

          <section className="flex flex-col gap-3.5 rounded-2xl border border-accent-ice/15 bg-dark-card p-4">
            <div className="flex flex-col gap-1">
              <h2 className="font-display text-base font-semibold uppercase tracking-wide">Позвать друга</h2>
              <p className="text-[13px] leading-relaxed text-text-secondary">
                Отправь ссылку в мессенджер. Друг откроет её — и заявка придёт тебе, даже если он только что
                зарегистрировался.
              </p>
            </div>
            {user?.friend_code != null && (
              <div className="flex items-center justify-between gap-2 rounded-lg bg-dark-bg py-1 pl-3 pr-1 text-sm">
                <span className="min-w-0 truncate text-accent-ice">{inviteLink(user.friend_code).replace(/^https?:\/\//, '')}</span>
                <button
                  type="button"
                  onClick={() => void copyLink()}
                  aria-label="Скопировать ссылку"
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-text-secondary hover:text-text-primary"
                >
                  <i className="ti ti-copy" aria-hidden="true" />
                </button>
              </div>
            )}
            <Button type="button" onClick={() => void shareLink()} disabled={user?.friend_code == null} className="w-full">
              <i className="ti ti-share mr-2" aria-hidden="true" />
              Поделиться ссылкой
            </Button>
            {linkState !== null && <p className="text-center text-xs text-text-secondary">{linkState}</p>}
          </section>

          <section className="flex flex-col gap-2.5">
            <h2 className="text-xs font-medium uppercase tracking-wide text-text-secondary">Или по коду</h2>
            <p className="text-sm text-text-secondary">
              Твой код: <span className="font-mono text-text-primary">{user?.friend_code ?? '—'}</span>
            </p>
            <form onSubmit={sendByCode} className="flex gap-2">
              <label className="flex min-w-0 flex-1">
                <span className="sr-only">Код друга</span>
                <input
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  maxLength={16}
                  placeholder="Код друга"
                  className="min-h-11 min-w-0 flex-1 rounded-lg border border-white/10 bg-dark-card px-3 text-sm uppercase text-text-primary outline-none placeholder:normal-case placeholder:text-text-secondary focus:border-accent-ice"
                />
              </label>
              <Button type="submit" variant="neutral" isLoading={isSendingCode} disabled={code.trim() === ''}>
                Отправить
              </Button>
            </form>
            <FormError message={codeError} />
            {codeSuccess !== null && <p className="text-sm text-accent-ice">{codeSuccess}</p>}
          </section>
        </>
      )}

      {opened !== null && (
        <PlayerSheet
          player={opened}
          relation={relationOf(opened)}
          isSending={sendingId === opened.id}
          onAdd={() => void addPlayer(opened)}
          onClose={() => setOpened(null)}
        />
      )}
    </div>
  )
}

function SearchResults({
  searchable,
  results,
  error,
  renderRow,
  onShareLink,
}: {
  searchable: boolean
  results: PlayerSuggestionRead[] | null
  error: string | null
  renderRow: (player: PlayerSuggestionRead) => ReactNode
  onShareLink: () => void
}) {
  if (!searchable) {
    return <p className="px-1 text-sm text-text-secondary">Напиши имя и фамилию — хотя бы по 2 буквы</p>
  }
  if (error !== null) {
    return <FormError message={error} />
  }
  if (results === null) {
    return <p className="px-1 text-sm text-text-secondary">Ищем...</p>
  }
  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-white/15 px-4 py-6 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-dark-card text-text-secondary">
          <i className="ti ti-user-search text-2xl" aria-hidden="true" />
        </span>
        <p className="text-[15px] font-semibold">Никого не нашли</p>
        <p className="max-w-[280px] text-[13px] leading-relaxed text-text-secondary">
          Возможно, он скрыт из поиска или ещё не в IceLevel. Отправь ему ссылку — заявка придёт сама.
        </p>
        <Button type="button" onClick={onShareLink}>
          Поделиться ссылкой
        </Button>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-2">
      <p className="px-1 text-xs text-text-secondary">
        Найдено {results.length} · нажми на игрока, чтобы открыть его карточку
      </p>
      {results.map(renderRow)}
    </div>
  )
}

function Avatar({ player, size = 'h-11 w-11' }: { player: PlayerSuggestionRead; size?: string }) {
  const initials = `${player.first_name.charAt(0)}${player.last_name.charAt(0)}`.toUpperCase()
  return (
    <span className={`flex ${size} shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-accent-ice bg-[#22304A]`}>
      {player.avatar_url !== null ? (
        <img src={`${API_BASE_URL}${player.avatar_url}`} alt="" className="h-full w-full object-cover" />
      ) : (
        <span className="font-display text-sm font-semibold text-accent-ice">{initials}</span>
      )}
    </span>
  )
}

function RelationAction({
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
      {relation === 'incoming' ? 'Принять заявку' : wide ? 'Добавить в друзья' : 'Добавить'}
    </Button>
  )
}

function PlayerRow({
  player,
  meta,
  relation,
  isSending,
  onOpen,
  onAdd,
}: {
  player: PlayerSuggestionRead
  meta: string
  relation: FriendRelation
  isSending: boolean
  onOpen: () => void
  onAdd: () => void
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl bg-dark-card p-3">
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Открыть карточку: ${player.first_name} ${player.last_name}`}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
      >
        <Avatar player={player} />
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate text-sm font-semibold text-text-primary">
            {player.first_name} {player.last_name}
          </span>
          <span className="truncate text-xs text-text-secondary">{meta}</span>
        </span>
      </button>
      <RelationAction relation={relation} isSending={isSending} onAdd={onAdd} />
    </div>
  )
}

// Their player card -- the one a friend would see, minus nothing (it never
// carries the age) -- with the same add button.
function PlayerSheet({
  player,
  relation,
  isSending,
  onAdd,
  onClose,
}: {
  player: PlayerSuggestionRead
  relation: FriendRelation
  isSending: boolean
  onAdd: () => void
  onClose: () => void
}) {
  const { accessToken } = useAuth()
  const [profile, setProfile] = useState<UserPublicRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    usersApi
      .getUserPublicProfile(player.id, accessToken)
      .then((result) => {
        if (!cancelled) {
          setProfile(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить карточку.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, player.id])

  const mutual = mutualLine(player.mutual_friends)

  return (
    <Modal title={`${player.first_name} ${player.last_name}`} onClose={onClose}>
      <div className="flex flex-col items-center gap-4">
        <FormError message={loadError} />
        {profile === null && loadError === null && <p className="text-sm text-text-secondary">Загрузка...</p>}
        {profile !== null && (
          <div className="w-full max-w-[340px]">
            <PublicPlayerCard profile={profile} />
          </div>
        )}
        {(player.team_name !== null || mutual !== null) && (
          <p className="text-center text-[13px] text-text-secondary">
            {[player.team_name, mutual].filter(Boolean).join(' · ')}
          </p>
        )}
        <div className="flex w-full justify-center">
          <RelationAction relation={relation} isSending={isSending} onAdd={onAdd} wide />
        </div>
        {relation !== 'friend' && (
          <p className="text-center text-xs leading-relaxed text-text-secondary">
            Возраст и лента тренировок откроются, когда вы станете друзьями
          </p>
        )}
      </div>
    </Modal>
  )
}
