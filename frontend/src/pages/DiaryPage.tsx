import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
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

// Uppercase 3-letter, same register as WEEKDAY_LABELS elsewhere -- used only
// for the day-planner-style date tab below, not worth a shared util for one
// call site.
const MONTH_ABBREVIATIONS = [
  'ЯНВ', 'ФЕВ', 'МАР', 'АПР', 'МАЙ', 'ИЮН', 'ИЮЛ', 'АВГ', 'СЕН', 'ОКТ', 'НОЯ', 'ДЕК',
]

// "Open my diary and read it back" -- the player's own notebook across
// every ON_ICE/GAME session, newest first (entries are written from
// TrainingDiaryPage, one per session). Tapping a
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

        {/* 2026-09-19 design pass: entries read as pages of one notebook,
            flipped through one after another -- a single continuous list
            with a hairline between rows, not a stack of bordered cards. */}
        {entries !== null && entries.length > 0 && (
          <div className="flex flex-col">
            {entries.map((entry) => (
              <DiaryEntryRow key={entry.id} entry={entry} onOpen={() => setOpenEntry(entry)} />
            ))}
          </div>
        )}
      </div>

      {openEntry !== null && <DiaryEntryModal entry={openEntry} onClose={() => setOpenEntry(null)} />}
    </div>
  )
}

function DiaryEntryRow({ entry, onOpen }: { entry: TrainingDiaryEntryListItem; onOpen: () => void }) {
  const date = parseIsoDate(entry.date)
  const hasNote = entry.note !== null && entry.note !== ''
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex gap-3.5 border-t border-white/10 py-4 text-left transition-colors first:border-t-0 hover:bg-white/[0.02]"
    >
      {/* Day-planner-style date tab -- the day itself is the headline (same
          "display" face the app already uses for stat/level numbers), the
          month a quiet caption under it, rather than a monospace "18.09"
          code string. */}
      <div className="w-9 shrink-0 pt-0.5 text-center">
        <div className={`font-display text-2xl leading-none ${hasNote ? 'text-accent-persimmon' : 'text-[#5B6480]'}`}>
          {date.getDate()}
        </div>
        <div className="mt-1 font-display text-[10px] tracking-wide text-[#8A94A6]">
          {MONTH_ABBREVIATIONS[date.getMonth()]}
        </div>
      </div>
      <div className="w-px shrink-0 self-stretch bg-accent-persimmon/20" />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <span className={`flex w-fit items-center gap-1.5 text-xs ${SESSION_TYPE_COLORS[entry.session_type]}`}>
          <i className={`ti ${SESSION_TYPE_ICONS[entry.session_type]}`} aria-hidden="true" />
          {DAY_SESSION_TYPE_LABELS[entry.session_type]}
        </span>
        {hasNote ? (
          <p className="line-clamp-2 whitespace-pre-wrap text-sm leading-snug text-[#D7DCE6]">{entry.note}</p>
        ) : (
          <p className="text-sm italic text-[#5B6480]">Без заметки</p>
        )}
      </div>
    </button>
  )
}

// Read-only: no textarea, no save/skip -- this is the history list's own
// view of an entry, distinct from TrainingDiaryPage,
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
