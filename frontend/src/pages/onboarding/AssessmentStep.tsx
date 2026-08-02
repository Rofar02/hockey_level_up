import { useState } from 'react'
import { ChoiceCard } from '../../components/ui/ChoiceCard'
import { FormError } from '../../components/ui/FormError'
import * as assessmentApi from '../../api/assessment'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { AssessmentTestForm } from './AssessmentTestForm'

type Mode = 'test' | null

export function AssessmentStep({ onNext }: { onNext: () => void }) {
  const { accessToken } = useAuth()
  const [mode, setMode] = useState<Mode>(null)
  const [isStartingFromScratch, setIsStartingFromScratch] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleStartFromScratch() {
    if (accessToken === null) {
      return
    }
    setError(null)
    setIsStartingFromScratch(true)
    try {
      await assessmentApi.startFromScratch(accessToken)
      onNext()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить. Попробуйте ещё раз.')
    } finally {
      setIsStartingFromScratch(false)
    }
  }

  function handleTestSuccess() {
    onNext()
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold">Оцените текущий уровень подготовки</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <ChoiceCard
          title="Пройти тест"
          description="5 простых упражнений — точнее оценим стартовые характеристики"
          selected={mode === 'test'}
          disabled={isStartingFromScratch}
          onClick={() => setMode('test')}
        />
        <ChoiceCard
          title="Начать с нуля"
          description="Базовый уровень без теста — подстроим сложность по вашей обратной связи"
          disabled={isStartingFromScratch}
          onClick={handleStartFromScratch}
        />
      </div>
      {isStartingFromScratch && <p className="text-sm text-text-secondary">Загрузка...</p>}
      <FormError message={error} />

      {mode === 'test' && accessToken !== null && (
        <AssessmentTestForm accessToken={accessToken} onSuccess={handleTestSuccess} />
      )}
    </div>
  )
}
