import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { Checkbox } from '../components/ui/Checkbox'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { ProgressBar } from '../components/ui/ProgressBar'
import * as exercisesApi from '../api/exercises'
import * as trainingPartiesApi from '../api/trainingParties'
import { API_BASE_URL, ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { TARGET_STAT_LABELS } from '../types/exercise'
import type { ExerciseRead } from '../types/exercise'
import type { TrainingPartyDetailRead, TrainingPartyMemberRead } from '../types/trainingParty'
import { formatShortDate, parseIsoDate } from '../utils/date'
import { getDisplayName } from '../utils/displayName'

// Refresh while the party is still open -- everyone's training on the same
// shared exercise set once the organizer confirms it, this is the only way
// to see live progress without websockets.
const POLL_INTERVAL_MS = 8000

type BuilderMode = 'closed' | 'auto' | 'manual'

export function TrainingPartyDetailPage() {
  const { partyId } = useParams<{ partyId: string }>()
  const navigate = useNavigate()
  const { user, accessToken } = useAuth()

  const [party, setParty] = useState<TrainingPartyDetailRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyUserId, setBusyUserId] = useState<string | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const [isLeaving, setIsLeaving] = useState(false)

  // -- creator-only exercise builder --
  const [builderMode, setBuilderMode] = useState<BuilderMode>('closed')
  const [suggestions, setSuggestions] = useState<ExerciseRead[] | null>(null)
  const [catalog, setCatalog] = useState<ExerciseRead[] | null>(null)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [isSuggesting, setIsSuggesting] = useState(false)
  const [isConfirming, setIsConfirming] = useState(false)
  const [builderError, setBuilderError] = useState<string | null>(null)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  async function refresh() {
    if (accessToken === null || partyId === undefined) {
      return
    }
    const result = await trainingPartiesApi.getTrainingParty(partyId, accessToken)
    setParty(result)
    return result
  }

  useEffect(() => {
    if (accessToken === null || partyId === undefined) {
      return
    }
    let cancelled = false
    refresh().catch((err: unknown) => {
      if (!cancelled) {
        setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить тренировку.')
      }
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, partyId])

  useEffect(() => {
    if (party?.status !== 'pending') {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
      return
    }
    pollRef.current = setInterval(() => {
      refresh().catch(() => {
        // Best-effort background refresh -- a transient failure just tries
        // again on the next tick, no need to surface a banner for it.
      })
    }, POLL_INTERVAL_MS)
    return () => {
      if (pollRef.current !== null) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [party?.status])

  async function handleDecide(accept: boolean) {
    if (accessToken === null || partyId === undefined || user === null) {
      return
    }
    setActionError(null)
    setBusyUserId(user.id)
    try {
      if (accept) {
        await trainingPartiesApi.acceptTrainingPartyInvite(partyId, accessToken)
      } else {
        await trainingPartiesApi.declineTrainingPartyInvite(partyId, accessToken)
      }
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось обработать приглашение.')
    } finally {
      setBusyUserId(null)
    }
  }

  async function handleCancel() {
    if (accessToken === null || partyId === undefined || party === null) {
      return
    }
    if (!window.confirm('Отменить эту совместную тренировку?')) {
      return
    }
    setActionError(null)
    setIsCancelling(true)
    try {
      await trainingPartiesApi.cancelTrainingParty(partyId, accessToken)
      await refresh()
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось отменить тренировку.')
    } finally {
      setIsCancelling(false)
    }
  }

  async function handleLeave() {
    if (accessToken === null || partyId === undefined) {
      return
    }
    if (!window.confirm('Выйти из совместной тренировки?')) {
      return
    }
    setActionError(null)
    setIsLeaving(true)
    try {
      await trainingPartiesApi.leaveTrainingParty(partyId, accessToken)
      navigate('/training-parties', { replace: true })
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось выйти из тренировки.')
    } finally {
      setIsLeaving(false)
    }
  }

  // -- exercise builder --

  async function fetchSuggestions(): Promise<ExerciseRead[]> {
    if (accessToken === null || partyId === undefined) {
      return []
    }
    const result = await trainingPartiesApi.suggestTrainingPartyExercises(partyId, accessToken)
    setSuggestions(result)
    return result
  }

  async function handleOpenAuto() {
    setBuilderError(null)
    setBuilderMode('auto')
    setIsSuggesting(true)
    try {
      const result = await fetchSuggestions()
      setSelectedIds(result.map((exercise) => exercise.id))
    } catch (err) {
      setBuilderError(err instanceof ApiError ? err.message : 'Не удалось подобрать упражнения.')
    } finally {
      setIsSuggesting(false)
    }
  }

  async function handleReshuffle() {
    setBuilderError(null)
    setIsSuggesting(true)
    try {
      const result = await fetchSuggestions()
      setSelectedIds(result.map((exercise) => exercise.id))
    } catch (err) {
      setBuilderError(err instanceof ApiError ? err.message : 'Не удалось подобрать упражнения.')
    } finally {
      setIsSuggesting(false)
    }
  }

  async function handleOpenManual() {
    if (accessToken === null) {
      return
    }
    setBuilderError(null)
    setBuilderMode('manual')
    setIsSuggesting(true)
    try {
      const [recommended, fullCatalog] = await Promise.all([
        suggestions ?? fetchSuggestions(),
        catalog ?? exercisesApi.listExercises({ category: 'off_ice', phase: 'main' }, accessToken),
      ])
      setCatalog(fullCatalog)
      setSelectedIds(recommended.map((exercise) => exercise.id))
    } catch (err) {
      setBuilderError(err instanceof ApiError ? err.message : 'Не удалось загрузить список упражнений.')
    } finally {
      setIsSuggesting(false)
    }
  }

  function handleReopenBuilder() {
    if (party?.exercises === null || party?.exercises === undefined) {
      return
    }
    setBuilderMode('manual')
    setSelectedIds(party.exercises.map((exercise) => exercise.id))
    if (catalog === null && accessToken !== null) {
      exercisesApi
        .listExercises({ category: 'off_ice', phase: 'main' }, accessToken)
        .then(setCatalog)
        .catch(() => {
          // Best-effort prefetch -- the picker just stays empty until retried.
        })
    }
    if (suggestions === null) {
      fetchSuggestions().catch(() => {
        // Recommendations are a nice-to-have highlight, not required to edit.
      })
    }
  }

  function toggleSelected(exerciseId: string) {
    setSelectedIds((previous) =>
      previous.includes(exerciseId)
        ? previous.filter((id) => id !== exerciseId)
        : [...previous, exerciseId],
    )
  }

  async function handleConfirm() {
    if (accessToken === null || partyId === undefined || selectedIds.length === 0) {
      return
    }
    setBuilderError(null)
    setIsConfirming(true)
    try {
      const result = await trainingPartiesApi.confirmTrainingPartyExercises(
        partyId,
        { exercise_ids: selectedIds },
        accessToken,
      )
      setParty(result)
      setBuilderMode('closed')
    } catch (err) {
      setBuilderError(err instanceof ApiError ? err.message : 'Не удалось сохранить набор упражнений.')
    } finally {
      setIsConfirming(false)
    }
  }

  const isLoading = party === null
  const isCreator = party !== null && user !== null && party.created_by === user.id
  const myMember = party?.members.find((member) => member.user_id === user?.id) ?? null
  const recommendedIds = new Set((suggestions ?? []).map((exercise) => exercise.id))

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <BackLink to="/training-parties" />

        <FormError message={loadError} />
        {isLoading && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {party !== null && (
          <>
            <StatusBanner party={party} />

            {party.status === 'pending' && isCreator && builderMode === 'closed' && (
              <ExerciseBuilderLauncher
                party={party}
                onOpenAuto={handleOpenAuto}
                onReopen={handleReopenBuilder}
              />
            )}

            {party.status === 'pending' && isCreator && builderMode !== 'closed' && (
              <ExerciseBuilder
                mode={builderMode}
                suggestions={suggestions}
                catalog={catalog}
                selectedIds={selectedIds}
                recommendedIds={recommendedIds}
                isSuggesting={isSuggesting}
                isConfirming={isConfirming}
                error={builderError}
                onSwitchToManual={handleOpenManual}
                onReshuffle={handleReshuffle}
                onToggle={toggleSelected}
                onConfirm={handleConfirm}
                onCancel={() => {
                  setBuilderMode('closed')
                  setBuilderError(null)
                }}
              />
            )}

            {party.exercises !== null && party.exercises.length > 0 && builderMode === 'closed' && (
              <FinalizedExercisesCard exercises={party.exercises} />
            )}

            <div className="flex flex-col gap-2">
              {party.members.map((member) => (
                <MemberCard
                  key={member.user_id}
                  member={member}
                  isSelf={member.user_id === user?.id}
                  isBusy={busyUserId === member.user_id}
                  showActions={party.status === 'pending'}
                  exercisesFinalized={party.exercises_finalized_at !== null}
                  onAccept={() => handleDecide(true)}
                  onDecline={() => handleDecide(false)}
                  onGoToTraining={() => navigate(`/training/${member.day_plan_id}`)}
                />
              ))}
            </div>

            <FormError message={actionError} />

            {party.status === 'pending' && (
              <div className="flex flex-col gap-2">
                {isCreator ? (
                  <Button
                    type="button"
                    variant="neutral"
                    isLoading={isCancelling}
                    onClick={handleCancel}
                    className="self-start"
                  >
                    Отменить тренировку
                  </Button>
                ) : myMember?.membership_status === 'joined' ? (
                  <Button
                    type="button"
                    variant="neutral"
                    isLoading={isLeaving}
                    onClick={handleLeave}
                    className="self-start"
                  >
                    Выйти
                  </Button>
                ) : null}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function StatusBanner({ party }: { party: TrainingPartyDetailRead }) {
  const dateLabel = formatShortDate(parseIsoDate(party.target_date))

  if (party.status === 'completed') {
    return (
      <div className={`flex items-center gap-3 p-4 ${CARD_CLASS} border-accent-ice/40`}>
        <i className="ti ti-confetti text-2xl text-accent-ice" aria-hidden="true" />
        <div className="flex flex-col">
          <span className="text-sm font-semibold text-[#F5F7FA]">Все потренировались вместе!</span>
          <span className="text-xs text-[#8A94A6]">{dateLabel}</span>
        </div>
      </div>
    )
  }

  const labels: Record<string, string> = {
    pending: 'Совместная тренировка',
    cancelled: 'Тренировка отменена',
    expired: 'Тренировка не состоялась',
  }

  return (
    <div className="flex flex-col gap-1">
      <h1 className="text-xl font-semibold">{labels[party.status] ?? 'Совместная тренировка'}</h1>
      <p className="text-sm text-[#8A94A6]">{dateLabel}</p>
      {party.status === 'pending' && party.exercises_finalized_at === null && (
        <p className="text-xs text-[#8A94A6]">
          Организатор ещё не выбрал упражнения — у всех участников будет один общий набор.
        </p>
      )}
    </div>
  )
}

function ExerciseBuilderLauncher({
  party,
  onOpenAuto,
  onReopen,
}: {
  party: TrainingPartyDetailRead
  onOpenAuto: () => void
  onReopen: () => void
}) {
  if (party.exercises_finalized_at !== null) {
    return (
      <div className={`flex flex-col gap-2 p-4 ${CARD_CLASS}`}>
        <span className="text-sm text-[#8A94A6]">
          Набор упражнений уже подтверждён — его можно поменять, пока никто не начал тренировку.
        </span>
        <Button type="button" variant="neutral" onClick={onReopen} className="self-start !px-3 !py-1.5 !text-xs">
          Изменить набор
        </Button>
      </div>
    )
  }

  return (
    <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <span className="text-sm text-[#F5F7FA]">
        Выберите общий набор упражнений — его пройдут все участники.
      </span>
      <div className="flex gap-2">
        <Button type="button" onClick={onOpenAuto} className="!px-3 !py-1.5 !text-xs">
          Сгенерировать
        </Button>
      </div>
    </div>
  )
}

function ExerciseBuilder({
  mode,
  suggestions,
  catalog,
  selectedIds,
  recommendedIds,
  isSuggesting,
  isConfirming,
  error,
  onSwitchToManual,
  onReshuffle,
  onToggle,
  onConfirm,
  onCancel,
}: {
  mode: BuilderMode
  suggestions: ExerciseRead[] | null
  catalog: ExerciseRead[] | null
  selectedIds: string[]
  recommendedIds: Set<string>
  isSuggesting: boolean
  isConfirming: boolean
  error: string | null
  onSwitchToManual: () => void
  onReshuffle: () => void
  onToggle: (exerciseId: string) => void
  onConfirm: () => void
  onCancel: () => void
}) {
  const selected = new Set(selectedIds)

  // Manual mode: recommended exercises first (in suggestion order), then
  // the rest of the catalog alphabetically -- same pool the personal-plan
  // side already fetches from (GET /exercises), just with recommendations
  // from suggest_party_exercises visually promoted.
  const orderedCatalog =
    catalog === null
      ? null
      : [...catalog].sort((a, b) => {
          const aRecommended = recommendedIds.has(a.id) ? 0 : 1
          const bRecommended = recommendedIds.has(b.id) ? 0 : 1
          return aRecommended - bRecommended
        })

  return (
    <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-[#F5F7FA]">
          {mode === 'auto' ? 'Сгенерированный набор' : 'Соберите набор сами'}
        </span>
        {mode === 'auto' && (
          <button
            type="button"
            onClick={onSwitchToManual}
            className="text-xs text-accent-ice hover:underline"
          >
            Собрать самому
          </button>
        )}
      </div>

      {isSuggesting && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

      {mode === 'auto' && !isSuggesting && suggestions !== null && (
        <div className="flex flex-col gap-2">
          {suggestions.map((exercise) => (
            <ExerciseRow key={exercise.id} exercise={exercise} recommended />
          ))}
          {suggestions.length === 0 && (
            <p className="text-sm text-[#8A94A6]">
              Не удалось подобрать общие упражнения — попробуйте собрать набор вручную.
            </p>
          )}
        </div>
      )}

      {mode === 'manual' && !isSuggesting && orderedCatalog !== null && (
        <div className="flex max-h-96 flex-col gap-1 overflow-y-auto">
          {orderedCatalog.map((exercise) => (
            <button
              key={exercise.id}
              type="button"
              onClick={() => onToggle(exercise.id)}
              className="flex items-center gap-3 p-2 text-left hover:bg-white/5"
            >
              <Checkbox checked={selected.has(exercise.id)} />
              <ExerciseRow exercise={exercise} recommended={recommendedIds.has(exercise.id)} compact />
            </button>
          ))}
        </div>
      )}

      <FormError message={error} />

      <div className="flex flex-wrap gap-2">
        {mode === 'auto' && (
          <Button
            type="button"
            variant="neutral"
            isLoading={isSuggesting}
            onClick={onReshuffle}
            className="!px-3 !py-1.5 !text-xs"
          >
            Перемешать
          </Button>
        )}
        <Button
          type="button"
          isLoading={isConfirming}
          disabled={selectedIds.length === 0}
          onClick={onConfirm}
          className="!px-3 !py-1.5 !text-xs"
        >
          Подтвердить набор ({selectedIds.length})
        </Button>
        <Button
          type="button"
          variant="neutral"
          disabled={isConfirming}
          onClick={onCancel}
          className="!px-3 !py-1.5 !text-xs"
        >
          Отмена
        </Button>
      </div>
    </div>
  )
}

function ExerciseRow({
  exercise,
  recommended,
  compact = false,
}: {
  exercise: ExerciseRead
  recommended: boolean
  compact?: boolean
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
      <div className="flex min-w-0 flex-col">
        <span className={`truncate text-sm ${compact ? '' : 'font-medium'} text-[#F5F7FA]`}>
          {exercise.name}
        </span>
        <span className="text-xs text-[#8A94A6]">
          {exercise.target_stats.map((stat) => TARGET_STAT_LABELS[stat]).join(', ')}
        </span>
      </div>
      {recommended && (
        <span className="shrink-0 rounded-full border border-accent-ice/40 px-2 py-0.5 text-[10px] text-accent-ice">
          Рекомендовано
        </span>
      )}
    </div>
  )
}

function FinalizedExercisesCard({ exercises }: { exercises: ExerciseRead[] }) {
  return (
    <div className={`flex flex-col gap-2 p-4 ${CARD_CLASS}`}>
      <span className="text-sm font-medium text-[#F5F7FA]">Общая тренировка</span>
      <div className="flex flex-col gap-1.5">
        {exercises.map((exercise) => (
          <div key={exercise.id} className="flex items-center justify-between gap-2 text-sm">
            <span className="truncate text-[#F5F7FA]">{exercise.name}</span>
            <span className="shrink-0 text-xs text-[#8A94A6]">
              {exercise.target_stats.map((stat) => TARGET_STAT_LABELS[stat]).join(', ')}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

function MemberCard({
  member,
  isSelf,
  isBusy,
  showActions,
  exercisesFinalized,
  onAccept,
  onDecline,
  onGoToTraining,
}: {
  member: TrainingPartyMemberRead
  isSelf: boolean
  isBusy: boolean
  // False once the party is no longer pending (completed/cancelled/expired)
  // -- accept/decline and start/continue all stop being meaningful actions
  // at that point, even though the member's own training_status value
  // (e.g. "not_started") wouldn't otherwise hide them.
  showActions: boolean
  exercisesFinalized: boolean
  onAccept: () => void
  onDecline: () => void
  onGoToTraining: () => void
}) {
  const dimmed = member.membership_status === 'declined'

  return (
    <div className={`flex items-center gap-3 p-3 ${CARD_CLASS} ${dimmed ? 'opacity-50' : ''}`}>
      <div
        className={`flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-dark-bg ${
          isSelf ? 'border-2 border-accent-ice' : 'border border-white/10'
        }`}
      >
        {member.avatar_url !== null ? (
          <img src={`${API_BASE_URL}${member.avatar_url}`} alt="" className="h-full w-full object-cover" />
        ) : (
          <i className="ti ti-user text-lg text-[#8A94A6]" aria-hidden="true" />
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="truncate text-sm font-medium text-[#F5F7FA]">
          {getDisplayName(member)}
          {isSelf ? ' (вы)' : ''}
        </span>
        <MemberStatusRow member={member} exercisesFinalized={exercisesFinalized} />
      </div>

      {showActions && (
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {isSelf && member.membership_status === 'invited' && (
            <div className="flex gap-2">
              <Button type="button" isLoading={isBusy} onClick={onAccept} className="!px-3 !py-1.5 !text-xs">
                Принять
              </Button>
              <Button
                type="button"
                variant="neutral"
                disabled={isBusy}
                onClick={onDecline}
                className="!px-3 !py-1.5 !text-xs"
              >
                Отклонить
              </Button>
            </div>
          )}
          {isSelf &&
            (member.training_status === 'not_started' || member.training_status === 'in_progress') && (
              <Button type="button" onClick={onGoToTraining} className="!px-3 !py-1.5 !text-xs">
                {member.training_status === 'not_started' ? 'Начать' : 'Продолжить'}
              </Button>
            )}
        </div>
      )}
    </div>
  )
}

function MemberStatusRow({
  member,
  exercisesFinalized,
}: {
  member: TrainingPartyMemberRead
  exercisesFinalized: boolean
}) {
  if (member.membership_status === 'invited') {
    return <span className="text-xs text-[#8A94A6]">Ещё не ответил(а)</span>
  }
  if (member.membership_status === 'declined') {
    return <span className="text-xs text-[#8A94A6]">Отклонил(а) приглашение</span>
  }

  // Before the organizer confirms a set, a joined member's own plan for that
  // day (rest, no plan, or whatever they already had) is about to be
  // replaced with the shared session -- showing it as-is would read like it
  // matters, so a single waiting label covers all of those states instead.
  if (!exercisesFinalized) {
    return <span className="text-xs text-[#8A94A6]">Ждёт набор упражнений от организатора</span>
  }

  switch (member.training_status) {
    case 'game_day':
      return (
        <span className="flex items-center gap-1 text-xs text-[#8A94A6]">
          <i className="ti ti-shirt-sport" aria-hidden="true" />
          Игровой день — не участвует
        </span>
      )
    case 'not_started':
      return <span className="text-xs text-[#8A94A6]">Ещё не начал(а)</span>
    case 'in_progress':
      return (
        <div className="flex flex-col gap-1">
          <span className="text-xs text-accent-ice">
            {member.completed_blocks}/{member.total_blocks} блоков
          </span>
          <div className="w-32">
            <ProgressBar value={member.completed_blocks ?? 0} max={member.total_blocks ?? 1} />
          </div>
        </div>
      )
    case 'completed':
      return (
        <span className="flex items-center gap-1 text-xs font-medium text-accent-ice">
          <i className="ti ti-circle-check-filled" aria-hidden="true" />
          Завершил(а) тренировку
        </span>
      )
    default:
      return null
  }
}
