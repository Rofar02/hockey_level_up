import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import * as teamEventsApi from '../api/teamEvents'
import { ApiError } from '../api/client'
import { ShareCardModal } from '../components/ShareCardModal'
import { LineCard, MiniPlayerCard, slotLabel } from '../components/teams/LineupCards'
import { teamCardStyle } from '../components/teams/TeamCard'
import { getPlayerCardLook } from '../components/playerCardLook'
import { BackLink } from '../components/ui/BackLink'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { TabButton } from '../components/ui/TabButton'
import { useAuth } from '../hooks/useAuth'
import type { TeamCurrentLineupRead, TeamEventLineupGroupRead } from '../types/teamEvent'
import { renderCardImage } from '../utils/cardImage'

type LineupTab = 'lines' | 'all'

function gameLine(lineup: TeamCurrentLineupRead): string {
  if (lineup.event === null) {
    return ''
  }
  const date = new Date(lineup.event.starts_at).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
  return lineup.event.opponent_name !== null ? `vs ${lineup.event.opponent_name} · ${date}` : date
}

// "Состав по звеньям" (2026-10-09): the next game's lineup (the last one's
// when none is scheduled) -- forward lines of three mini-cards, defense
// pairs, goalies; a tap on a line opens its card, which can be shared.
export function TeamLineupPage() {
  const { teamId } = useParams<{ teamId: string }>()
  const { accessToken, user } = useAuth()
  const [data, setData] = useState<TeamCurrentLineupRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [tab, setTab] = useState<LineupTab>('lines')
  const [openLine, setOpenLine] = useState<TeamEventLineupGroupRead | null>(null)
  const [sharedImage, setSharedImage] = useState<Blob | null>(null)
  const [shareError, setShareError] = useState<string | null>(null)
  const [isSharing, setIsSharing] = useState(false)
  const lineCardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (accessToken === null || teamId === undefined) {
      return
    }
    let cancelled = false
    teamEventsApi
      .getCurrentLineup(teamId, accessToken)
      .then((result) => {
        if (!cancelled) {
          setData(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить состав.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId])

  const groups = data?.lineup?.groups ?? null
  const lines = groups?.filter((g) => g.kind === 'forwards') ?? []
  const pairs = groups?.filter((g) => g.kind === 'defense') ?? []
  const goalies = groups?.filter((g) => g.kind === 'goalies') ?? []
  const mixed = groups?.filter((g) => g.kind === undefined || g.kind === 'mixed') ?? []
  const everyone = (groups ?? []).flatMap((g) => g.players.map((p) => ({ player: p, group: g })))

  async function handleShareLine() {
    const frame = lineCardRef.current?.querySelector<HTMLElement>('[data-card="frame"]')
    if (frame == null || openLine === null) {
      return
    }
    setShareError(null)
    setIsSharing(true)
    try {
      setSharedImage(await renderCardImage(frame, getPlayerCardLook(teamCardStyle(openLine.rating ?? null))))
    } catch (err) {
      setShareError(`Не удалось подготовить карточку (${err instanceof Error ? err.message : String(err)}).`)
    } finally {
      setIsSharing(false)
    }
  }

  function groupHeader(group: TeamEventLineupGroupRead) {
    return (
      <div className="flex items-center gap-2">
        {group.color !== null && <span className="h-3 w-3 rounded-full" style={{ backgroundColor: group.color }} aria-hidden="true" />}
        <span className="text-sm font-semibold text-[#F5F7FA]">{group.name ?? 'Без названия'}</span>
        {group.rating != null && (
          <span className="ml-auto font-display text-sm font-semibold text-accent-ice">рейтинг {group.rating}</span>
        )}
      </div>
    )
  }

  function groupGrid(group: TeamEventLineupGroupRead, columns: string) {
    return (
      <div className={`grid gap-2 pt-1 ${columns}`}>
        {group.players.map((player) => (
          <MiniPlayerCard key={player.user_id} player={player} isMe={player.user_id === user?.id} />
        ))}
      </div>
    )
  }

  const pairFor = (line: TeamEventLineupGroupRead) => pairs[lines.indexOf(line)] ?? null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-md flex-col gap-4 px-4 py-6">
        <BackLink />
        <div className="flex flex-col gap-0.5">
          <h1 className="font-display text-2xl font-semibold text-[#F5F7FA]">Состав по звеньям</h1>
          {data?.event != null && <span className="text-sm text-[#8A94A6]">{gameLine(data)}</span>}
        </div>

        <FormError message={loadError} />
        {data === null && loadError === null && <p className="text-sm text-text-secondary">Загрузка...</p>}

        {data !== null && data.event === null && (
          <EmptyState icon="ti-users-group" title="Пока нет игр" hint="Состав появится, когда капитан добавит игру." />
        )}
        {data?.event != null && groups === null && (
          <EmptyState icon="ti-lock" title="Состав ещё не опубликован" hint="Капитан опубликует звенья перед игрой." />
        )}

        {groups !== null && (
          <>
            <div className="flex border-b border-white/10">
              <TabButton active={tab === 'lines'} onClick={() => setTab('lines')}>
                Звенья
              </TabButton>
              <TabButton active={tab === 'all'} onClick={() => setTab('all')}>
                Весь состав
              </TabButton>
            </div>

            {tab === 'lines' && (
              <div className="flex flex-col gap-3">
                {groups.length === 0 && <EmptyState icon="ti-users-group" title="Звеньев пока нет" />}
                {lines.map((line) => (
                  <button
                    key={line.id}
                    type="button"
                    onClick={() => setOpenLine(line)}
                    className={`flex flex-col gap-2 p-3 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
                  >
                    {groupHeader(line)}
                    {groupGrid(line, 'grid-cols-3')}
                    <span className="text-xs text-accent-ice">Карточка звена ›</span>
                  </button>
                ))}
                {pairs.length > 0 && (
                  <span className="pt-1 text-xs font-medium uppercase tracking-wide text-[#8A94A6]">Пары защиты</span>
                )}
                {pairs.map((pair) => (
                  <div key={pair.id} className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
                    {groupHeader(pair)}
                    {groupGrid(pair, 'grid-cols-3')}
                  </div>
                ))}
                {goalies.map((group) => (
                  <div key={group.id} className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
                    {groupHeader(group)}
                    {groupGrid(group, 'grid-cols-3')}
                  </div>
                ))}
                {mixed.map((group) => (
                  <div key={group.id} className={`flex flex-col gap-2 p-3 ${CARD_CLASS}`}>
                    {groupHeader(group)}
                    {groupGrid(group, 'grid-cols-3')}
                  </div>
                ))}
              </div>
            )}

            {tab === 'all' && (
              <div className={`flex flex-col ${CARD_CLASS}`}>
                {everyone.map(({ player, group }) => (
                  <div
                    key={player.user_id}
                    className="flex min-h-12 items-center gap-3 border-b border-white/5 px-3.5 last:border-b-0"
                  >
                    <span className="w-9 font-display text-sm font-semibold text-accent-ice">{slotLabel(player)}</span>
                    <span className="w-9 font-display text-sm text-[#8A94A6]">
                      {player.jersey_number != null ? `#${player.jersey_number}` : ''}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-[#F5F7FA]">
                      {player.last_name || player.first_name}
                      {player.user_id === user?.id && <span className="ml-1.5 text-xs text-accent-persimmon">ты</span>}
                    </span>
                    <span className="truncate text-xs text-[#8A94A6]">{group.name ?? ''}</span>
                    <span className="w-7 text-right font-display text-sm font-semibold text-[#F5F7FA]">{player.rating ?? '—'}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {openLine !== null && data !== null && (
        <Modal title={openLine.name ?? 'Звено'} onClose={() => setOpenLine(null)}>
          <div className="flex flex-col gap-3">
            <div ref={lineCardRef}>
              <LineCard line={openLine} pair={pairFor(openLine)} gameLine={gameLine(data)} />
            </div>
            <FormError message={shareError} />
            <button
              type="button"
              onClick={handleShareLine}
              disabled={isSharing}
              className="flex h-12 items-center justify-center gap-2 rounded-[14px] bg-accent-persimmon font-semibold text-dark-bg disabled:cursor-wait"
            >
              <i className={`ti ${isSharing ? 'ti-loader-2 animate-spin' : 'ti-share'}`} aria-hidden="true" />
              Поделиться
            </button>
          </div>
        </Modal>
      )}
      {sharedImage !== null && (
        <ShareCardModal
          image={sharedImage}
          onClose={() => setSharedImage(null)}
          title="Карточка звена"
          shareTitle="Наше звено — IceLevel"
        />
      )}
    </div>
  )
}
