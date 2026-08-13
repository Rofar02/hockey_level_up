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

          {entries.map((entry, index) => (
            <LeaderboardRow
              key={entry.id}
              rank={index + 1}
              displayName={getDisplayName(entry)}
              position={entry.position}
              jerseyNumber={entry.jersey_number}
              avatarUrl={entry.avatar_url}
              ratingExcess={entry.rating_excess}
              highlighted={index === myIndex}
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

