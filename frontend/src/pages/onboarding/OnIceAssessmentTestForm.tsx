import { useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import { TextField } from '../../components/ui/TextField'
import * as assessmentApi from '../../api/assessment'
import { ApiError } from '../../api/client'

export function OnIceAssessmentTestForm({
  accessToken,
  onSuccess,
}: {
  accessToken: string
  onSuccess: () => void
}) {
  const [onIceSkatingSeconds, setOnIceSkatingSeconds] = useState('')
  const [puckHandlingSeconds, setPuckHandlingSeconds] = useState('')

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await assessmentApi.submitOnIceTest(
        {
          on_ice_skating_seconds: Number(onIceSkatingSeconds),
          puck_handling_seconds: Number(puckHandlingSeconds),
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
          label="Катание 20 м, секунды"
          type="number"
          numeric
          min={0}
          step="any"
          value={onIceSkatingSeconds}
          onChange={(event) => setOnIceSkatingSeconds(event.target.value)}
          required
        />
        <TextField
          label="Слалом с шайбой, секунды"
          type="number"
          numeric
          min={0}
          step="any"
          value={puckHandlingSeconds}
          onChange={(event) => setPuckHandlingSeconds(event.target.value)}
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
