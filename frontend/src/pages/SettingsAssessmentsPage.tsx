import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { AssessmentTestForm } from './onboarding/AssessmentTestForm'
import { OnIceAssessmentTestForm } from './onboarding/OnIceAssessmentTestForm'
import * as assessmentApi from '../api/assessment'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { AssessmentStatus, OnIceAssessmentStatus } from '../types/assessment'

export function SettingsAssessmentsPage() {
  const { accessToken } = useAuth()

  const [assessmentStatus, setAssessmentStatus] = useState<AssessmentStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [isDismissing, setIsDismissing] = useState(false)
  const [showTestForm, setShowTestForm] = useState(false)
  const [testSuccess, setTestSuccess] = useState(false)

  const [onIceStatus, setOnIceStatus] = useState<OnIceAssessmentStatus | null>(null)
  const [onIceStatusError, setOnIceStatusError] = useState<string | null>(null)
  const [showOnIceTestForm, setShowOnIceTestForm] = useState(false)
  const [onIceTestSuccess, setOnIceTestSuccess] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    assessmentApi
      .getStatus(accessToken)
      .then((result) => {
        if (!cancelled) {
          setAssessmentStatus(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setStatusError(err instanceof ApiError ? err.message : 'Не удалось загрузить статус теста.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    assessmentApi
      .getOnIceStatus(accessToken)
      .then((result) => {
        if (!cancelled) {
          setOnIceStatus(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setOnIceStatusError(
            err instanceof ApiError ? err.message : 'Не удалось загрузить статус теста.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function handleDismissReassessment() {
    if (accessToken === null) {
      return
    }
    setStatusError(null)
    setIsDismissing(true)
    try {
      await assessmentApi.dismissReassessmentSuggestion(accessToken)
      setAssessmentStatus((previous) =>
        previous !== null ? { ...previous, suggested_reassessment: false } : previous,
      )
    } catch (err) {
      setStatusError(err instanceof ApiError ? err.message : 'Не удалось сохранить. Попробуйте ещё раз.')
    } finally {
      setIsDismissing(false)
    }
  }

  async function handleTestSuccess() {
    setShowTestForm(false)
    setTestSuccess(true)
    // Retaking the test is itself the reassessment, so clear the flag even
    // though the backend doesn't reset it on a plain test submission.
    if (accessToken !== null) {
      try {
        await assessmentApi.dismissReassessmentSuggestion(accessToken)
      } catch {
        // Best-effort -- worst case the banner stays visible despite the
        // fresh result, which is harmless.
      }
    }
    setAssessmentStatus((previous) =>
      previous !== null ? { ...previous, has_assessment: true, suggested_reassessment: false } : previous,
    )
  }

  function handleOnIceTestSuccess() {
    setShowOnIceTestForm(false)
    setOnIceTestSuccess(true)
    // Unlike the off-ice flow above, no extra dismiss call is needed here --
    // AssessmentService.run_onice_test already resets
    // suggested_onice_reassessment server-side, so the optimistic update
    // below is the only client-side bookkeeping required.
    setOnIceStatus((previous) =>
      previous !== null
        ? { ...previous, has_onice_assessment: true, suggested_onice_reassessment: false }
        : previous,
    )
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-8 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Тестирование</h1>
        </div>

        <section className="flex flex-col gap-4">
          <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
            <i className="ti ti-clipboard-list text-accent-ice" aria-hidden="true" />
            Оценка физподготовки
            <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
          </h2>
          {assessmentStatus === null && statusError === null && (
            <p className="text-sm text-[#8A94A6]">Загрузка...</p>
          )}
          <FormError message={statusError} />

          {assessmentStatus?.has_assessment === false && !showTestForm && (
            <Button variant="neutral" onClick={() => setShowTestForm(true)} className="self-start">
              Пройти тест
            </Button>
          )}

          {assessmentStatus?.has_assessment === true &&
            assessmentStatus.suggested_reassessment === true &&
            !showTestForm && (
              <div className="flex flex-col gap-3 rounded-md border border-accent-persimmon/40 bg-accent-persimmon/10 p-4">
                <p className="text-sm text-[#F5F7FA]">
                  Похоже, ваш уровень подготовки изменился. Стоит пройти тест заново, чтобы точнее
                  откалибровать характеристики.
                </p>
                <div className="flex gap-3">
                  <Button onClick={() => setShowTestForm(true)}>Пройти тест заново</Button>
                  <Button variant="neutral" onClick={handleDismissReassessment} isLoading={isDismissing}>
                    Не сейчас
                  </Button>
                </div>
              </div>
            )}

          {assessmentStatus?.has_assessment === true &&
            assessmentStatus.suggested_reassessment === false && (
              <p className="text-sm text-[#8A94A6]">
                Переоценка станет доступна в начале следующего тренировочного блока.
              </p>
            )}

          {testSuccess && <p className="text-sm text-accent-ice">Результаты сохранены.</p>}

          {showTestForm && accessToken !== null && (
            <AssessmentTestForm accessToken={accessToken} onSuccess={handleTestSuccess} />
          )}
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
            <i className="ti ti-ice-skating text-accent-ice" aria-hidden="true" />
            Оценка катания
            <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
          </h2>
          {onIceStatus === null && onIceStatusError === null && (
            <p className="text-sm text-[#8A94A6]">Загрузка...</p>
          )}
          <FormError message={onIceStatusError} />

          {onIceStatus?.has_onice_assessment === false && !showOnIceTestForm && (
            <Button variant="neutral" onClick={() => setShowOnIceTestForm(true)} className="self-start">
              Пройти тест
            </Button>
          )}

          {onIceStatus?.has_onice_assessment === true &&
            onIceStatus.suggested_onice_reassessment === true &&
            !showOnIceTestForm && (
              <div className="flex flex-col gap-3 rounded-md border border-accent-persimmon/40 bg-accent-persimmon/10 p-4">
                <p className="text-sm text-[#F5F7FA]">
                  Похоже, ваш уровень катания изменился. Стоит пройти тест заново, чтобы точнее
                  откалибровать характеристики.
                </p>
                <Button onClick={() => setShowOnIceTestForm(true)}>Пройти тест заново</Button>
              </div>
            )}

          {onIceStatus?.has_onice_assessment === true &&
            onIceStatus.suggested_onice_reassessment === false && (
              <p className="text-sm text-[#8A94A6]">Переоценка станет доступна позже.</p>
            )}

          {onIceTestSuccess && <p className="text-sm text-accent-ice">Результаты сохранены.</p>}

          {showOnIceTestForm && accessToken !== null && (
            <OnIceAssessmentTestForm accessToken={accessToken} onSuccess={handleOnIceTestSuccess} />
          )}
        </section>
      </div>
    </div>
  )
}
