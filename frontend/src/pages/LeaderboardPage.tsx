import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { RankBadge } from '../components/ui/RankBadge'
import * as leaderboardApi from '../api/leaderboard'
import { API_BASE_URL, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { LeaderboardEntryRead, LeaderboardMeRead } from '../types/leaderboard'
import { POSITION_LABELS } from '../types/user'
import { getDisplayName } from '../utils/displayName'

// Same icy top-border card convention as Home/TrainingSession/Profile.
const CARD_BORDER = 'border-t border-[rgba(215,239,255,0.35)]'

function formatRatingExcess(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}`
}

function RatingExcess({ value }: { value: number }) {
  return (
    <span className={`font-mono text-base font-bold ${value > 0 ? 'text-accent-ice' : 'text-[#8A94A6]'}`}>
      {formatRatingExcess(value)}
    </span>
  )
}

export function LeaderboardPage() {
  const { user, accessToken } = useAuth()

  const [entries, setEntries] = useState<LeaderboardEntryRead[] | null>(null)
  const [me, setMe] = useState<LeaderboardMeRead | null>(null)
  const [meError, setMeError] = useState<string | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false

    leaderboardApi
      .getLeaderboard(accessToken)
      .then((result) => {
        if (!cancelled) {
          setEntries(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить рейтинг.')
        }
      })

    leaderboardApi
      .getMyLeaderboardPosition(accessToken)
      .then((result) => {
        if (!cancelled) {
          setMe(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setMeError(
            err instanceof ApiError
              ? err.message
              : 'Не удалось загрузить вашу позицию в рейтинге.',
          )
        }
      })

    return () => {
      cancelled = true
    }
  }, [accessToken])

  const myIndex = entries?.findIndex((entry) => entry.id === user?.id) ?? -1
  // /leaderboard is capped at a page size -- if the current user's rank
  // falls outside it, /leaderboard/me still has their rank+rating, so pin a
  // separate row for them instead of just leaving them out.
  const pinnedMe = myIndex === -1 ? me : null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
      <div className="flex flex-col gap-2">
        <BackLink to="/profile" />
        <h1 className="text-xl font-semibold">Рейтинг</h1>
        <p className="text-sm text-[#8A94A6]">
          Превышение над ожидаемым уровнем для вашего возраста и стажа — не сырые характеристики.
        </p>
      </div>

      <FormError message={loadError} />
      {entries === null && loadError === null && (
        <p className="text-sm text-[#8A94A6]">Загрузка...</p>
      )}

      {entries !== null && entries.length === 0 && pinnedMe === null && (
        <EmptyState icon="ti-trophy" title="Пока никто не в рейтинге" />
      )}

      {entries !== null && (entries.length > 0 || pinnedMe !== null) && (
        <div className="flex flex-col gap-2">
          {entries.length > 0 && <LeaderboardPodium entries={entries.slice(0, 3)} meId={user?.id ?? null} />}

          {pinnedMe !== null && (
            <>
              <LeaderboardRow
                rank={pinnedMe.rank}
                displayName={user !== null ? getDisplayName(user) : ''}
                position={user?.position ?? null}
                jerseyNumber={user?.jersey_number ?? null}
                avatarUrl={user?.avatar_url ?? null}
                ratingExcess={pinnedMe.rating_excess}
                highlighted
              />
              <div className="my-1 border-t border-dashed border-white/10" />
            </>
          )}

          {entries.slice(3).map((entry, index) => (
            <LeaderboardRow
              key={entry.id}
              rank={index + 4}
              displayName={getDisplayName(entry)}
              position={entry.position}
              jerseyNumber={entry.jersey_number}
              avatarUrl={entry.avatar_url}
              ratingExcess={entry.rating_excess}
              highlighted={index + 3 === myIndex}
            />
          ))}
        </div>
      )}

      <FormError message={meError} />
      </div>
    </div>
  )
}

function LeaderboardRow({
  rank,
  displayName,
  position,
  jerseyNumber,
  avatarUrl,
  ratingExcess,
  highlighted,
}: {
  rank: number
  displayName: string
  position: LeaderboardEntryRead['position']
  jerseyNumber: number | null
  avatarUrl: string | null
  ratingExcess: number
  highlighted: boolean
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-md p-3 ${
        highlighted
          ? 'border border-accent-ice/40 bg-accent-ice/10'
          : `${CARD_BORDER} bg-dark-card`
      }`}
    >
      <RankBadge rank={rank} />
      <div className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/10 bg-dark-bg">
        {avatarUrl !== null ? (
          <img src={`${API_BASE_URL}${avatarUrl}`} alt="" className="h-full w-full object-cover" />
        ) : (
          <i className="ti ti-user text-lg text-[#8A94A6]" aria-hidden="true" />
        )}
      </div>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className={`truncate font-medium ${highlighted ? 'text-accent-ice' : 'text-[#F5F7FA]'}`}>
          {displayName}
        </span>
        <span className="text-xs text-[#8A94A6]">
          {[position !== null ? POSITION_LABELS[position] : null, jerseyNumber !== null ? `№${jerseyNumber}` : null]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </div>
      <RatingExcess value={ratingExcess} />
    </div>
  )
}

// Top-3 podium above the plain-row list -- ranks 4+ still render as
// LeaderboardRow below this. Displayed in the classic 2nd/1st/3rd left-to-
// right arrangement, not rank order; a slot is skipped (not padded) if
// fewer than 3 entries exist. Same medal colors as RankBadge.tsx's own
// (private) MEDAL_COLORS -- duplicated rather than imported, matching this
// file's own CARD_BORDER-duplication convention (a component file only
// exports its component, not shared constants -- oxlint's
// react/only-export-components flags the alternative).
const MEDAL_COLORS: Record<number, string> = { 1: '#FFC94A', 2: '#C7CFDB', 3: '#D3915B' }
const PODIUM_DISPLAY_ORDER = [2, 1, 3]
const PODIUM_AVATAR_SIZE: Record<number, string> = {
  1: 'h-[66px] w-[66px]',
  2: 'h-[52px] w-[52px]',
  3: 'h-[52px] w-[52px]',
}
const PODIUM_PEDESTAL_HEIGHT: Record<number, string> = { 1: 'h-[82px]', 2: 'h-14', 3: 'h-10' }

function LeaderboardPodium({ entries, meId }: { entries: LeaderboardEntryRead[]; meId: string | null }) {
  return (
    <div className="mb-2 flex items-end justify-center gap-2.5">
      {PODIUM_DISPLAY_ORDER.map((rank) => {
        const entry = entries[rank - 1]
        if (entry === undefined) {
          return null
        }
        return <PodiumSlot key={entry.id} rank={rank} entry={entry} isSelf={entry.id === meId} />
      })}
    </div>
  )
}

function PodiumSlot({
  rank,
  entry,
  isSelf,
}: {
  rank: number
  entry: LeaderboardEntryRead
  isSelf: boolean
}) {
  const medalColor = MEDAL_COLORS[rank]
  const avatarUrl = entry.avatar_url !== null ? `${API_BASE_URL}${entry.avatar_url}` : null

  return (
    <div className="flex flex-1 flex-col items-center gap-1.5">
      <div
        className={`flex shrink-0 items-center justify-center overflow-hidden rounded-full border-[3px] ${PODIUM_AVATAR_SIZE[rank]}`}
        style={{ borderColor: medalColor, boxShadow: `0 0 ${rank === 1 ? 16 : 10}px ${medalColor}80` }}
      >
        {avatarUrl !== null ? (
          <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
        ) : (
          <i className="ti ti-user text-xl text-[#8A94A6]" aria-hidden="true" />
        )}
      </div>
      <span className="max-w-full truncate text-xs font-semibold text-[#F5F7FA]">
        {getDisplayName(entry)}
        {isSelf ? ' (вы)' : ''}
      </span>
      <span className="font-mono text-xs font-bold" style={{ color: medalColor }}>
        {formatRatingExcess(entry.rating_excess)}
      </span>
      <div
        className={`flex w-full items-center justify-center rounded-t-md border-t-2 ${PODIUM_PEDESTAL_HEIGHT[rank]}`}
        style={{
          background: `linear-gradient(180deg, ${medalColor}30, ${medalColor}08)`,
          borderColor: medalColor,
        }}
      >
        {rank === 1 ? (
          <i className="ti ti-trophy text-xl" style={{ color: medalColor }} aria-hidden="true" />
        ) : (
          <span className="font-mono text-xl font-extrabold" style={{ color: medalColor }}>
            {rank}
          </span>
        )}
      </div>
    </div>
  )
}

