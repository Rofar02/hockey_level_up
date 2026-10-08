import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import * as friendsApi from '../../api/friends'
import { API_BASE_URL, ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { FriendRelation, PlayerSuggestionRead } from '../../types/friend'
import { POSITION_LABELS } from '../../types/user'
import { copyText } from '../../utils/clipboard'
import { Button } from '../ui/Button'
import { FormError } from '../ui/FormError'
import { FriendAction, PlayerSheet } from './PlayerSheet'
import { inviteLink, isFullName, isSearchable, mutualLine } from '../../utils/friendSearch'

const SEARCH_DELAY_MS = 350
const TEAMMATES_SHOWN = 3

export function PlayerAvatar({ player, size = 'h-11 w-11' }: { player: PlayerSuggestionRead; size?: string }) {
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

function metaLine(player: PlayerSuggestionRead, withTeam: boolean): string {
  return [
    withTeam ? (player.team_name ?? 'Без команды') : player.jersey_number !== null ? `#${player.jersey_number}` : null,
    player.position !== null ? POSITION_LABELS[player.position] : null,
    `ур. ${player.level}`,
    withTeam ? mutualLine(player.mutual_friends) : null,
  ]
    .filter(Boolean)
    .join(' · ')
}

// The "Добавить" tab (2026-10-08): friend requests only -- teams invite on
// their own page. Smart search (one word among the people around me, first
// and last name among everyone findable, similar spellings), teammates,
// friends of friends, and the invite link; the code stays at the bottom. A
// tap on a player opens their card.
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
    setLinkState(
      (await copyText(inviteLink(user.friend_code))) ? 'Ссылка скопирована' : 'Не удалось скопировать — выделите ссылку вручную',
    )
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
  const exact = results?.filter((player) => player.match === 'exact') ?? []
  const similar = results?.filter((player) => player.match === 'similar') ?? []

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <div className="flex flex-col gap-0.5 px-1">
          <h2 className="text-[15px] font-semibold">Добавить в друзья</h2>
          <p className="text-[13px] leading-relaxed text-text-secondary">
            Игроку придёт заявка в друзья. В команду зовут на странице команды.
          </p>
        </div>
        <label className="flex min-h-12 items-center gap-2.5 rounded-xl border border-white/10 bg-dark-card px-3.5 focus-within:border-accent-ice">
          <i className="ti ti-search text-lg text-text-secondary" aria-hidden="true" />
          <span className="sr-only">Найти игрока</span>
          <input
            type="text"
            inputMode="search"
            enterKeyHint="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Имя или фамилия игрока"
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
        <div className="flex flex-col gap-2">
          {!searchable && <p className="px-1 text-sm text-text-secondary">Напиши хотя бы 2 буквы</p>}
          {searchable && searchError !== null && <FormError message={searchError} />}
          {searchable && searchError === null && results === null && (
            <p className="px-1 text-sm text-text-secondary">Ищем...</p>
          )}
          {searchable && results !== null && (
            <>
              <p className="px-1 text-xs leading-relaxed text-text-secondary">
                {isFullName(query)
                  ? 'Ищем среди всех, кто разрешил себя находить. Нажми на игрока — откроется его карточка.'
                  : 'Ищем среди твоих знакомых: друзья, команда, друзья друзей. Чтобы найти любого — напиши имя и фамилию.'}
              </p>
              {exact.map((player) => row(player, metaLine(player, true)))}
              {similar.length > 0 && (
                <>
                  <h3 className="mt-2 px-1 text-xs font-medium uppercase tracking-wide text-text-secondary">
                    Похожие
                  </h3>
                  {similar.map((player) => row(player, metaLine(player, true)))}
                </>
              )}
              {results.length === 0 && (
                <NothingFound fullName={isFullName(query)} onShareLink={() => void shareLink()} />
              )}
            </>
          )}
        </div>
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
              <h2 className="font-display text-base font-semibold uppercase tracking-wide">Ссылка для друга</h2>
              <p className="text-[13px] leading-relaxed text-text-secondary">
                Отправь её в мессенджер. Друг откроет — и тебе придёт его заявка в друзья, даже если он только что
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
          userId={opened.id}
          title={`${opened.first_name} ${opened.last_name}`}
          onClose={() => setOpened(null)}
          onChanged={(relation) => {
            setSentTo((prev) => ({ ...prev, [opened.id]: relation }))
            void onFriendsChanged()
          }}
        />
      )}
    </div>
  )
}

function NothingFound({ fullName, onShareLink }: { fullName: boolean; onShareLink: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-white/15 px-4 py-6 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-dark-card text-text-secondary">
        <i className="ti ti-user-search text-2xl" aria-hidden="true" />
      </span>
      <p className="text-[15px] font-semibold">Никого не нашли</p>
      <p className="max-w-[290px] text-[13px] leading-relaxed text-text-secondary">
        {fullName
          ? 'Возможно, он скрыт из поиска или ещё не в IceLevel. Отправь ему ссылку — заявка придёт сама.'
          : 'Среди знакомых таких нет. Напиши имя и фамилию, чтобы искать среди всех, или отправь ссылку.'}
      </p>
      <Button type="button" onClick={onShareLink}>
        Поделиться ссылкой
      </Button>
    </div>
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
        <PlayerAvatar player={player} />
        <span className="flex min-w-0 flex-col gap-0.5">
          <span className="truncate text-sm font-semibold text-text-primary">
            {player.first_name} {player.last_name}
          </span>
          <span className="truncate text-xs text-text-secondary">{meta}</span>
        </span>
      </button>
      <FriendAction relation={relation} isSending={isSending} onAdd={onAdd} />
    </div>
  )
}
