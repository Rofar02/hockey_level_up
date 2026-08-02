import { useState } from 'react'
import { Button } from '../../components/ui/Button'
import { ChoiceCard } from '../../components/ui/ChoiceCard'
import { FormError } from '../../components/ui/FormError'
import * as usersApi from '../../api/users'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { EQUIPMENT_CHOICES } from '../../types/user'
import type { EquipmentAccess } from '../../types/user'

export function EquipmentStep({ onNext }: { onNext: () => void }) {
  const { accessToken } = useAuth()
  const [selected, setSelected] = useState<EquipmentAccess | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleNext() {
    if (selected === null || accessToken === null) {
      return
    }
    setError(null)
    setIsSubmitting(true)
    try {
      await usersApi.updateEquipmentAccess(selected, accessToken)
      onNext()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold">Какое оборудование у вас есть?</h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {EQUIPMENT_CHOICES.map((option) => (
          <ChoiceCard
            key={option.value}
            title={option.title}
            description={option.description}
            selected={selected === option.value}
            disabled={isSubmitting}
            onClick={() => setSelected(option.value)}
          />
        ))}
      </div>
      {isSubmitting && <p className="text-sm text-text-secondary">Загрузка...</p>}
      <FormError message={error} />
      <Button onClick={handleNext} disabled={selected === null} isLoading={isSubmitting} className="self-end">
        Далее
      </Button>
    </div>
  )
}
