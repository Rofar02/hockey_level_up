import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import * as trainingDiaryApi from '../api/trainingDiary'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { DAY_SESSION_TYPE_LABELS, SESSION_TYPE_COLORS, SESSION_TYPE_ICONS } from '../types/schedule'
import type { TrainingDiaryEntryListItem } from '../types/trainingDiary'
import { formatShortDate, parseIsoDate } from '../utils/date'

// "Open my diary and read it back" -- the player's own notebook across
// every ON_ICE/GAME session, newest first (entries are written from
// TrainingSessionPage's TrainingDiaryCard, one per session). Tapping a
// card opens it for READING in a modal right here (2026-09-18: navigating
// straight into TrainingSessionPage instead, as an earlier version of
// this did, dropped the player into the live exercise/phase flow of a
// long-finished session, which read as "start this workout again" --
// wrong for a history list). The modal itself offers an explicit, opt-in
// link to that session for whoever actually wants to open it.
export function DiaryPage() {
  const { accessToken } = useAuth()
  const [entries, setEntries] = useState<TrainingDiaryEntryListItem[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [openEntry, setOpenEntry] = useState<TrainingDiaryEntryListItem | null>(null)

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
              <DiaryEntryCard key={entry.id} entry={entry} onOpen={() => setOpenEntry(entry)} />
            ))}
          </div>
        )}
      </div>

      {openEntry !== null && <DiaryEntryModal entry={openEntry} onClose={() => setOpenEntry(null)} />}
    </div>
  )
}

function DiaryEntryCard({ entry, onOpen }: { entry: TrainingDiaryEntryListItem; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`flex w-full flex-col gap-2 p-4 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="font-mono text-sm text-[#8A94A6]">{formatShortDate(parseIsoDate(entry.date))}</span>
        <span className="flex items-center gap-3">
          <span className={`flex items-center gap-1.5 text-sm ${SESSION_TYPE_COLORS[entry.session_type]}`}>
            <i className={`ti ${SESSION_TYPE_ICONS[entry.session_type]}`} aria-hidden="true" />
            {DAY_SESSION_TYPE_LABELS[entry.session_type]}
          </span>
          <i className="ti ti-chevron-right text-[#8A94A6]" aria-hidden="true" />
        </span>
      </div>
      {entry.note !== null && entry.note !== '' ? (
        <p className="line-clamp-3 whitespace-pre-wrap text-sm text-[#F5F7FA]">{entry.note}</p>
      ) : (
        <p className="text-sm italic text-[#8A94A6]">Без заметки</p>
      )}
    </button>
  )
}

// Read-only: no textarea, no save/skip -- this is the history list's own
// view of an entry, distinct from TrainingDiaryCard (TrainingSessionPage),
// which is the one place an entry is actually written/edited. "Открыть
// тренировку" is the one deliberate way out of "just reading" into the
// live session, for whoever wants the full exercise breakdown for that day.
function DiaryEntryModal({ entry, onClose }: { entry: TrainingDiaryEntryListItem; onClose: () => void }) {
  const navigate = useNavigate()

  return (
    <Modal title={formatShortDate(parseIsoDate(entry.date))} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <span className={`flex w-fit items-center gap-1.5 text-sm ${SESSION_TYPE_COLORS[entry.session_type]}`}>
          <i className={`ti ${SESSION_TYPE_ICONS[entry.session_type]}`} aria-hidden="true" />
          {DAY_SESSION_TYPE_LABELS[entry.session_type]}
        </span>
        {entry.note !== null && entry.note !== '' ? (
          <p className="whitespace-pre-wrap text-sm text-[#F5F7FA]">{entry.note}</p>
        ) : (
          <p className="text-sm italic text-[#8A94A6]">Без заметки</p>
        )}
        <button
          type="button"
          onClick={() => navigate(`/training/${entry.day_plan_id}`)}
          className="flex items-center gap-1.5 self-start text-sm text-accent-ice underline decoration-dotted underline-offset-2 transition-colors hover:text-text-primary"
        >
          Открыть тренировку
          <i className="ti ti-arrow-right" aria-hidden="true" />
        </button>
      </div>
    </Modal>
  )
}
