import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import * as restrictionsApi from '../api/userTemporaryRestrictions'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { MovementPattern } from '../types/exercise'
import type { UserTemporaryRestrictionRead } from '../types/userTemporaryRestriction'
import { formatShortDate, parseIsoDate } from '../utils/date'

// Same icy top-border card convention as Home/Profile/Diary.
const CARD_CLASS = 'rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-card'

// MOVEMENT_PATTERN_LABELS (types/exercise.ts) is S&C/admin vocabulary for
// tagging exercises ("Хип-хиндж", "Ротация") -- a player reporting pain
// doesn't think in movement-pattern taxonomy, they think in body part /
// what they were doing. Local-only friendlier copy for this page: a short
// plain-language label plus a one-line example so it's obvious what each
// option actually covers, without touching the shared admin labels.
// Grouped (not alphabetical/enum order) so related options sit together:
// strength patterns, then mobility, then on-ice/hockey-specific.
const RESTRICTION_PATTERN_GROUPS: { pattern: MovementPattern; label: string; hint: string }[] = [
  { pattern: 'squat', label: 'Присед', hint: 'приседания, выпады' },
  { pattern: 'hip_hinge', label: 'Поясница и задняя поверхность бедра', hint: 'наклоны, становая тяга' },
  { pattern: 'push', label: 'Толкающие движения руками', hint: 'жим, отжимания' },
  { pattern: 'pull', label: 'Тянущие движения руками', hint: 'подтягивания, тяга к поясу' },
  { pattern: 'rotation', label: 'Повороты корпуса', hint: 'скручивания, броски' },
  { pattern: 'core', label: 'Пресс и корпус', hint: 'планка, скручивания' },
  { pattern: 'ankle_mobility', label: 'Голеностоп', hint: 'стопа, лодыжка' },
  { pattern: 'hip_mobility', label: 'Тазобедренный сустав', hint: 'подвижность таза' },
  { pattern: 'shoulder_mobility', label: 'Плечи', hint: 'плечевой пояс' },
  { pattern: 'wrist_mobility', label: 'Запястья', hint: 'кисти рук' },
  { pattern: 'locomotion', label: 'Бег и катание', hint: 'ноги в движении' },
  { pattern: 'stick_handling', label: 'Клюшка и обводка', hint: 'владение шайбой' },
  { pattern: 'coordination', label: 'Координация и баланс', hint: 'реакция, равновесие' },
]
const RESTRICTION_PATTERN_LABELS: Record<MovementPattern, string> = Object.fromEntries(
  RESTRICTION_PATTERN_GROUPS.map((g) => [g.pattern, g.label]),
) as Record<MovementPattern, string>

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
  const [selectedPattern, setSelectedPattern] = useState<MovementPattern | null>(null)
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
    if (accessToken === null || selectedPattern === null) {
      return
    }
    setReportError(null)
    setIsReporting(true)
    try {
      await restrictionsApi.reportRestriction(
        { movement_pattern: selectedPattern, reason: reason.trim() === '' ? null : reason },
        accessToken,
      )
      setSelectedPattern(null)
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

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Ограничения</h1>
          <p className="text-sm text-[#8A94A6]">
            Если что-то болит или неудобно — отметьте ниже, и мы на время перестанем предлагать
            упражнения на эту область.
          </p>
        </div>

        <FormError message={loadError} />

        {restrictions !== null && restrictions.length > 0 && (
          <div className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-[#8A94A6]">Сейчас ограничено</h2>
            <FormError message={liftError} />
            {restrictions.map((restriction) => (
              <div key={restriction.id} className={`flex flex-col gap-2 p-4 ${CARD_CLASS}`}>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-[#F5F7FA]">
                    {RESTRICTION_PATTERN_LABELS[restriction.movement_pattern]}
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
            <span className="text-xs text-[#8A94A6]">Выберите область — ниже пример движений</span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {RESTRICTION_PATTERN_GROUPS.map(({ pattern, label, hint }) => (
              <button
                key={pattern}
                type="button"
                onClick={() => setSelectedPattern(pattern)}
                className={`flex flex-col gap-0.5 rounded-md border p-2.5 text-left transition-colors ${
                  selectedPattern === pattern
                    ? 'border-accent-ice bg-accent-ice/10'
                    : 'border-white/15 hover:border-white/30'
                }`}
              >
                <span
                  className={`text-sm font-medium ${
                    selectedPattern === pattern ? 'text-accent-ice' : 'text-[#F5F7FA]'
                  }`}
                >
                  {label}
                </span>
                <span className="text-xs text-[#8A94A6]">{hint}</span>
              </button>
            ))}
          </div>
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
            disabled={selectedPattern === null}
            className="self-end"
          >
            Сообщить
          </Button>
        </div>
      </div>
    </div>
  )
}
