import { useEffect, useState } from 'react'
import * as teamsApi from '../../api/teams'
import { API_BASE_URL, ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { TeamInviteCandidateRead, TeamRead } from '../../types/team'
import { POSITION_LABELS } from '../../types/user'
import { copyText } from '../../utils/clipboard'
import { isSearchable } from '../friends/AddFriendsTab'
import { Button } from '../ui/Button'
import { FormError } from '../ui/FormError'
import { Modal } from '../ui/Modal'

const SEARCH_DELAY_MS = 400

export function teamInviteLink(code: string): string {
  return `${window.location.origin}/t/${code}`
}

// "Позвать в команду" (2026-10-08), on the team hub and the team page: the
// invite link for anyone in the team to share (it opens the team's page;
// "Вступить" sends the captain a request), and for the captain a sheet to
// invite a friend or a player found by name. The bare code stays as a
// fallback line.
export function TeamInviteBlock({ team }: { team: TeamRead }) {
  const [state, setState] = useState<string | null>(null)
  const [isPicking, setIsPicking] = useState(false)
  const link = teamInviteLink(team.invite_code)

  async function share() {
    setState(null)
    if (typeof navigator.share === 'function') {
      try {
        await navigator.share({ title: team.name, text: `Вступай в «${team.name}» в IceLevel`, url: link })
        return
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          return
        }
      }
    }
    setState((await copyText(link)) ? 'Ссылка скопирована' : 'Не удалось скопировать — выделите ссылку вручную')
  }

  async function copy(text: string, done: string) {
    setState((await copyText(text)) ? done : 'Не удалось скопировать — выделите вручную')
  }

  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-accent-ice/15 bg-dark-card p-4">
      <div className="flex flex-col gap-1">
        <h2 className="font-display text-base font-semibold uppercase tracking-wide">Позвать в команду</h2>
        <p className="text-[13px] leading-relaxed text-text-secondary">
          {team.is_captain
            ? 'Отправь ссылку в чат команды или пригласи игрока из друзей и по имени.'
            : 'Отправь ссылку другу — капитану придёт его заявка.'}
        </p>
      </div>
      <div className="flex items-center justify-between gap-2 rounded-lg bg-dark-bg py-1 pl-3 pr-1 text-sm">
        <span className="min-w-0 truncate text-accent-ice">{link.replace(/^https?:\/\//, '')}</span>
        <button
          type="button"
          onClick={() => void copy(link, 'Ссылка скопирована')}
          aria-label="Скопировать ссылку на команду"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-text-secondary hover:text-text-primary"
        >
          <i className="ti ti-copy" aria-hidden="true" />
        </button>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={() => void share()} className="min-w-[150px] flex-1">
          <i className="ti ti-share mr-2" aria-hidden="true" />
          Поделиться ссылкой
        </Button>
        {team.is_captain && (
          <Button type="button" variant="neutral" onClick={() => setIsPicking(true)} className="min-w-[150px] flex-1">
            <i className="ti ti-user-plus mr-2" aria-hidden="true" />
            Пригласить игрока
          </Button>
        )}
      </div>
      <p className="text-xs text-text-secondary">
        Или по коду:{' '}
        <button
          type="button"
          onClick={() => void copy(team.invite_code, 'Код скопирован')}
          className="font-mono text-text-primary underline decoration-white/20 underline-offset-2"
        >
          {team.invite_code}
        </button>
      </p>
      {state !== null && <p className="text-center text-xs text-text-secondary">{state}</p>}
      {isPicking && <InvitePlayersSheet team={team} onClose={() => setIsPicking(false)} />}
    </section>
  )
}

const STATUS_LABELS: Record<Exclude<TeamInviteCandidateRead['status'], 'none'>, string> = {
  invited: 'Приглашён',
  member: 'В команде',
  in_team: 'В другой команде',
}

function InvitePlayersSheet({ team, onClose }: { team: TeamRead; onClose: () => void }) {
  const { accessToken } = useAuth()
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState<TeamInviteCandidateRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [invitingId, setInvitingId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const searching = query.trim() !== ''
  const searchable = isSearchable(query)

  useEffect(() => {
    if (accessToken === null || (searching && !searchable)) {
      setRows(null)
      return
    }
    let cancelled = false
    setLoadError(null)
    const timer = setTimeout(
      () => {
        teamsApi
          .listInviteCandidates(team.id, searching ? query : '', accessToken)
          .then((result) => !cancelled && setRows(result))
          .catch((err: unknown) => {
            if (!cancelled) {
              setRows(null)
              setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить список.')
            }
          })
      },
      searching ? SEARCH_DELAY_MS : 0,
    )
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [accessToken, team.id, query, searching, searchable])

  async function invite(player: TeamInviteCandidateRead) {
    if (accessToken === null) {
      return
    }
    setActionError(null)
    setInvitingId(player.id)
    try {
      await teamsApi.inviteToTeam(team.id, player.id, accessToken)
      setRows((prev) => prev?.map((row) => (row.id === player.id ? { ...row, status: 'invited' } : row)) ?? prev)
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось отправить приглашение.')
    } finally {
      setInvitingId(null)
    }
  }

  return (
    <Modal title="Пригласить игрока" onClose={onClose}>
      <div className="flex flex-col gap-3">
        <label className="flex min-h-12 items-center gap-2.5 rounded-xl border border-white/10 bg-dark-bg px-3.5 focus-within:border-accent-ice">
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
        </label>
        <p className="px-1 text-xs text-text-secondary">
          {searching ? 'Поиск среди тех, кто разрешил себя находить' : 'Твои друзья'}
        </p>
        <FormError message={loadError ?? actionError} />
        {searching && !searchable && (
          <p className="px-1 text-sm text-text-secondary">Напиши имя и фамилию — хотя бы по 2 буквы</p>
        )}
        {rows === null && loadError === null && (!searching || searchable) && (
          <p className="px-1 text-sm text-text-secondary">Загрузка...</p>
        )}
        {rows !== null && rows.length === 0 && (
          <p className="px-1 text-sm leading-relaxed text-text-secondary">
            {searching
              ? 'Никого не нашли. Возможно, игрок скрыт из поиска — отправь ему ссылку на команду.'
              : 'Друзей пока нет. Найди игрока по имени или отправь ссылку на команду.'}
          </p>
        )}
        {rows !== null &&
          rows.map((player) => (
            <div key={player.id} className="flex items-center gap-3 rounded-xl bg-dark-bg/60 p-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border-2 border-accent-ice bg-[#22304A]">
                {player.avatar_url !== null ? (
                  <img src={`${API_BASE_URL}${player.avatar_url}`} alt="" className="h-full w-full object-cover" />
                ) : (
                  <span className="font-display text-sm font-semibold text-accent-ice">
                    {`${player.first_name.charAt(0)}${player.last_name.charAt(0)}`.toUpperCase()}
                  </span>
                )}
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="truncate text-sm font-semibold">
                  {player.first_name} {player.last_name}
                </span>
                <span className="truncate text-xs text-text-secondary">
                  {[player.team_name ?? 'Без команды', player.position !== null ? POSITION_LABELS[player.position] : null, `ур. ${player.level}`]
                    .filter(Boolean)
                    .join(' · ')}
                </span>
              </span>
              {player.status === 'none' ? (
                <Button
                  type="button"
                  onClick={() => void invite(player)}
                  isLoading={invitingId === player.id}
                  className="!min-h-9 shrink-0 !rounded-full !px-3.5 !py-1.5 !text-xs"
                >
                  Пригласить
                </Button>
              ) : (
                <span className="shrink-0 px-1.5 text-xs text-text-secondary">{STATUS_LABELS[player.status]}</span>
              )}
            </div>
          ))}
      </div>
    </Modal>
  )
}
