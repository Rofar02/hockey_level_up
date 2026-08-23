import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import * as trainingDiaryApi from '../api/trainingDiary'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { DAY_SESSION_TYPE_LABELS, SESSION_TYPE_COLORS, SESSION_TYPE_ICONS } from '../types/schedule'
import type { TrainingDiaryEntryListItem } from '../types/trainingDiary'
import { formatShortDate, parseIsoDate } from '../utils/date'

// Same icy top-border card convention as Home/Profile/TrainingSession.
const CARD_CLASS = 'rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-card'

// "Open my diary and read it back" -- the player's own notebook across
// every ON_ICE/GAME session, newest first (entries are written from
// TrainingSessionPage's TrainingDiaryCard, one per session). Read-only:
// editing an entry happens back on that session's own page, not here.
export function DiaryPage() {
  const { accessToken } = useAuth()
  const [entries, setEntries] = useState<TrainingDiaryEntryListItem[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    trainingDiaryApi
      .listDiaryEntries(accessToken)
      .then((result) => {
        if (!cancelled) {
          setEntries(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить дневник.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Дневник</h1>
        </div>

        <FormError message={loadError} />

        {entries === null && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {entries !== null && entries.length === 0 && (
          <EmptyState
            icon="ti-notebook"
            title="Пока пусто"
            hint="Записи появятся здесь после тренировок на льду и игр"
          />
        )}

        {entries !== null && entries.length > 0 && (
          <div className="flex flex-col gap-3">
            {entries.map((entry) => (
              <DiaryEntryCard key={entry.id} entry={entry} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function DiaryEntryCard({ entry }: { entry: TrainingDiaryEntryListItem }) {
  return (
    <div className={`flex flex-col gap-2 p-4 ${CARD_CLASS}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-sm text-[#8A94A6]">{formatShortDate(parseIsoDate(entry.date))}</span>
        <span className={`flex items-center gap-1.5 text-sm ${SESSION_TYPE_COLORS[entry.session_type]}`}>
          <i className={`ti ${SESSION_TYPE_ICONS[entry.session_type]}`} aria-hidden="true" />
          {DAY_SESSION_TYPE_LABELS[entry.session_type]}
        </span>
      </div>
      {entry.note !== null && entry.note !== '' ? (
        <p className="whitespace-pre-wrap text-sm text-[#F5F7FA]">{entry.note}</p>
      ) : (
        <p className="text-sm italic text-[#8A94A6]">Без заметки</p>
      )}
    </div>
  )
}
