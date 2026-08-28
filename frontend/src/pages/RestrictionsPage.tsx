import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { RestrictionAvatar } from '../components/RestrictionAvatar'
import * as restrictionsApi from '../api/userTemporaryRestrictions'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { MOVEMENT_PATTERN_LABELS, MUSCLE_GROUP_LABELS } from '../types/exercise'
import type { MuscleGroup } from '../types/exercise'
import type { UserTemporaryRestrictionRead } from '../types/userTemporaryRestriction'
import { formatShortDate, parseIsoDate } from '../utils/date'

// Only muscle_group is reportable from this page now (2026-08-27) --
// RestrictionAvatar's body-map covers every real case; the earlier
// movement_pattern picker (rotation/coordination/stick-handling, no single
// body location) was dropped as a maximally-rare case not worth the extra
// UI. MOVEMENT_PATTERN_LABELS (admin/S&C jargon, not this page's usual
// friendlier copy) is used only as a display fallback below for any
// pre-existing movement_pattern-based restriction still active from before
// this change -- the backend model/schema still support it, only the
// picker was removed.
function restrictionLabel(restriction: UserTemporaryRestrictionRead): string {
  if (restriction.muscle_group !== null) {
    return MUSCLE_GROUP_LABELS[restriction.muscle_group]
  }
  if (restriction.movement_pattern !== null) {
    return MOVEMENT_PATTERN_LABELS[restriction.movement_pattern]
  }
  // Unreachable given the backend's "exactly one of the two" CHECK
  // constraint -- kept as a total fallback rather than a non-null
  // assertion, so a future schema change here fails loud, not silently.
  return '—'
}

// P3 item #7, manual-report-only first pass: a player flags a movement
// that hurts right now, and the app stops suggesting exercises tagged
// with it -- everywhere (warmup/cooldown/MAIN, on and off ice), for
// DEFAULT_RESTRICTION_DAYS unless lifted early. No AI classification of a
// free-text message yet -- that's a later layer on this same backend
// table, not this page.
export function RestrictionsPage() {
  const { accessToken } = useAuth()
  const [restrictions, setRestrictions] = useState<UserTemporaryRestrictionRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  // null (nothing picked yet), not a silent default -- picking one of
  // these should be a deliberate choice the player can see they made, not
  // a pre-selected value they'd have to notice and change.
  const [selectedGroup, setSelectedGroup] = useState<MuscleGroup | null>(null)
  const [reason, setReason] = useState('')
  const [isReporting, setIsReporting] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  const [liftingId, setLiftingId] = useState<string | null>(null)
  const [liftError, setLiftError] = useState<string | null>(null)

  function loadRestrictions(token: string) {
    restrictionsApi
      .listActiveRestrictions(token)
      .then(setRestrictions)
      .catch((err: unknown) => {
        setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить ограничения.')
      })
  }

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    loadRestrictions(accessToken)
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken])

  async function handleReport() {
    if (accessToken === null || selectedGroup === null) {
      return
    }
    setReportError(null)
    setIsReporting(true)
    try {
      await restrictionsApi.reportRestriction(
        {
          movement_pattern: null,
          muscle_group: selectedGroup,
          reason: reason.trim() === '' ? null : reason,
        },
        accessToken,
      )
      setSelectedGroup(null)
      setReason('')
      loadRestrictions(accessToken)
    } catch (err) {
      setReportError(err instanceof ApiError ? err.message : 'Не удалось сохранить.')
    } finally {
      setIsReporting(false)
    }
  }

  async function handleLift(restrictionId: string) {
    if (accessToken === null) {
      return
    }
    setLiftError(null)
    setLiftingId(restrictionId)
    try {
      await restrictionsApi.liftRestriction(restrictionId, accessToken)
      setRestrictions((previous) => previous?.filter((r) => r.id !== restrictionId) ?? previous)
    } catch (err) {
      setLiftError(err instanceof ApiError ? err.message : 'Не удалось снять ограничение.')
    } finally {
      setLiftingId(null)
    }
  }

  const restrictedGroups: MuscleGroup[] =
    restrictions?.flatMap((r) => (r.muscle_group !== null ? [r.muscle_group] : [])) ?? []

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Ограничения</h1>
          <p className="text-sm text-[#8A94A6]">
            Если что-то болит или неудобно — покажите на теле ниже, и мы на время перестанем
            предлагать упражнения на эту область.
          </p>
        </div>

        <FormError message={loadError} />

        {restrictions !== null && restrictions.length > 0 && (
          <div className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-[#8A94A6]">Сейчас ограничено</h2>
            <FormError message={liftError} />
            {restrictions.map((restriction) => (
              <div
                key={restriction.id}
                className="flex flex-col gap-2 rounded-md border border-dashed border-accent-persimmon/40 bg-accent-persimmon/5 p-4"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-[#F5F7FA]">
                    {restrictionLabel(restriction)}
                  </span>
                  <span className="font-mono text-xs text-[#8A94A6]">
                    до {formatShortDate(parseIsoDate(restriction.expires_at))}
                  </span>
                </div>
                {restriction.reason !== null && restriction.reason !== '' && (
                  <p className="text-sm text-[#8A94A6]">{restriction.reason}</p>
                )}
                <Button
                  variant="neutral"
                  onClick={() => handleLift(restriction.id)}
                  isLoading={liftingId === restriction.id}
                  className="self-end"
                >
                  Снять
                </Button>
              </div>
            ))}
          </div>
        )}

        {restrictions !== null && restrictions.length === 0 && (
          <EmptyState icon="ti-bandage" title="Сейчас ничего не ограничено" />
        )}

        <div className={`flex flex-col gap-4 p-4 ${CARD_CLASS}`}>
          <div className="flex flex-col gap-1">
            <span className="text-sm font-medium text-[#F5F7FA]">Что болит или неудобно?</span>
            <span className="text-xs text-[#8A94A6]">Нажмите на область тела</span>
          </div>

          <RestrictionAvatar
            restrictedGroups={restrictedGroups}
            selectedGroup={selectedGroup}
            onSelectGroup={setSelectedGroup}
          />

          {selectedGroup !== null && (
            <p className="text-sm text-[#8A94A6]">
              Выбрано: <span className="font-medium text-accent-ice">{MUSCLE_GROUP_LABELS[selectedGroup]}</span>
            </p>
          )}

          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Что именно болит или неудобно (необязательно)"
            rows={2}
            maxLength={500}
            className="resize-none rounded border border-white/10 bg-dark-bg px-3 py-2 text-sm text-[#F5F7FA] placeholder:text-[#8A94A6]/60 focus:border-accent-ice focus:outline-none"
          />
          <FormError message={reportError} />
          <Button
            onClick={handleReport}
            isLoading={isReporting}
            disabled={selectedGroup === null}
            className="self-end"
          >
            Сообщить
          </Button>
        </div>
      </div>
    </div>
  )
}
