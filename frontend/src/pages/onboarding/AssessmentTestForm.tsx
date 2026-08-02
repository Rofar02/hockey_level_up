import { useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import { TextField } from '../../components/ui/TextField'
import * as assessmentApi from '../../api/assessment'
import { ApiError } from '../../api/client'

function parseRunTimeToSeconds(value: string): number | null {
  const match = /^(\d{1,2}):([0-5]?\d)$/.exec(value.trim())
  if (match === null) {
    return null
  }
  return Number(match[1]) * 60 + Number(match[2])
}

export function AssessmentTestForm({
  accessToken,
  onSuccess,
}: {
  accessToken: string
  onSuccess: () => void
}) {
  const [longJumpCm, setLongJumpCm] = useState('')
  const [pushupsReps, setPushupsReps] = useState('')
  const [squatsReps, setSquatsReps] = useState('')
  const [plankSeconds, setPlankSeconds] = useState('')
  const [run1kmInput, setRun1kmInput] = useState('')

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)

    const run1kmSeconds = parseRunTimeToSeconds(run1kmInput)
    if (run1kmSeconds === null) {
      setError('Время бега укажите в формате мм:сс, например 05:30')
      return
    }

    setIsSubmitting(true)
    try {
      await assessmentApi.submitTest(
        {
          long_jump_cm: Number(longJumpCm),
          pushups_reps: Number(pushupsReps),
          squats_reps: Number(squatsReps),
          plank_seconds: Number(plankSeconds),
          run_1km_seconds: run1kmSeconds,
        },
        accessToken,
      )
      onSuccess()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось отправить результаты. Попробуйте ещё раз.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 border-t border-white/10 pt-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <TextField
          label="Прыжок в длину, см"
          type="number"
          numeric
          min={0}
          step="any"
          value={longJumpCm}
          onChange={(event) => setLongJumpCm(event.target.value)}
          required
        />
        <TextField
          label="Отжимания, повторы"
          type="number"
          numeric
          min={0}
          value={pushupsReps}
          onChange={(event) => setPushupsReps(event.target.value)}
          required
        />
        <TextField
          label="Приседания за минуту, повторы"
          type="number"
          numeric
          min={0}
          value={squatsReps}
          onChange={(event) => setSquatsReps(event.target.value)}
          required
        />
        <TextField
          label="Планка, секунды"
          type="number"
          numeric
          min={0}
          value={plankSeconds}
          onChange={(event) => setPlankSeconds(event.target.value)}
          required
        />
        <TextField
          label="Бег 1 км, мм:сс"
          type="text"
          numeric
          placeholder="05:30"
          value={run1kmInput}
          onChange={(event) => setRun1kmInput(event.target.value)}
          required
        />
      </div>
      {isSubmitting && <p className="text-sm text-text-secondary">Загрузка...</p>}
      <FormError message={error} />
      <Button type="submit" isLoading={isSubmitting} className="self-end">
        Отправить результаты
      </Button>
    </form>
  )
}
