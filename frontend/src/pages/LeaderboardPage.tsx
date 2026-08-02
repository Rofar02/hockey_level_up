import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import * as leaderboardApi from '../api/leaderboard'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { LeaderboardEntryRead, LeaderboardMeRead } from '../types/leaderboard'
import { POSITION_LABELS } from '../types/user'

function formatRatingExcess(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}`
}

function RatingExcess({ value }: { value: number }) {
  return (
    <span className={`font-mono text-base font-bold ${value > 0 ? 'text-accent-ice' : 'text-text-secondary'}`}>
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

  const myIndex = entries?.findIndex((entry) => entry.username === user?.username) ?? -1
  // /leaderboard is capped at a page size -- if the current user's rank
  // falls outside it, /leaderboard/me still has their rank+rating, so pin a
  // separate row for them instead of just leaving them out.
  const pinnedMe = myIndex === -1 ? me : null

  return (
    <div className="mx-auto flex min-h-svh max-w-2xl flex-col gap-6 px-4 py-8">
      <div className="flex flex-col gap-2">
        <BackLink to="/profile" />
        <h1 className="text-xl font-semibold">Рейтинг</h1>
        <p className="text-sm text-text-secondary">
          Превышение над ожидаемым уровнем для вашего возраста и стажа — не сырые характеристики.
        </p>
      </div>

      <FormError message={loadError} />
      {entries === null && loadError === null && (
        <p className="text-sm text-text-secondary">Загрузка...</p>
      )}

      {entries !== null && (
        <div className="flex flex-col gap-2">
          {pinnedMe !== null && (
            <>
              <LeaderboardRow
                rank={pinnedMe.rank}
                username={user?.username ?? ''}
                position={user?.position ?? null}
                jerseyNumber={user?.jersey_number ?? null}
                ratingExcess={pinnedMe.rating_excess}
                highlighted
              />
              <div className="my-1 border-t border-dashed border-white/10" />
            </>
          )}

          {entries.map((entry, index) => (
            <LeaderboardRow
              key={entry.username}
              rank={index + 1}
              username={entry.username}
              position={entry.position}
              jerseyNumber={entry.jersey_number}
              ratingExcess={entry.rating_excess}
              highlighted={index === myIndex}
            />
          ))}

          {entries.length === 0 && (
            <p className="text-sm text-text-secondary">Пока никто не в рейтинге.</p>
          )}
        </div>
      )}

      <FormError message={meError} />
    </div>
  )
}

function LeaderboardRow({
  rank,
  username,
  position,
  jerseyNumber,
  ratingExcess,
  highlighted,
}: {
  rank: number
  username: string
  position: LeaderboardEntryRead['position']
  jerseyNumber: number | null
  ratingExcess: number
  highlighted: boolean
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-md border p-3 ${
        highlighted
          ? 'border-accent-ice/40 bg-accent-ice/10'
          : 'border-white/5 bg-dark-card'
      }`}
    >
      <span className="w-8 shrink-0 text-center font-mono text-sm text-text-secondary">{rank}</span>
      <div className="flex min-w-0 flex-1 flex-col">
        <span className={`truncate font-medium ${highlighted ? 'text-accent-ice' : 'text-text-primary'}`}>
          {username}
        </span>
        <span className="text-xs text-text-secondary">
          {[position !== null ? POSITION_LABELS[position] : null, jerseyNumber !== null ? `№${jerseyNumber}` : null]
            .filter(Boolean)
            .join(' · ')}
        </span>
      </div>
      <RatingExcess value={ratingExcess} />
    </div>
  )
}
