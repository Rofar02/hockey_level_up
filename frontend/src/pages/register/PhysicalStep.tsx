import type { FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import { Checkbox } from '../../components/ui/Checkbox'
import { FormError } from '../../components/ui/FormError'
import { TextField } from '../../components/ui/TextField'

// Step 3/3, the final one -- its submit IS the real registration submit
// (RegisterPage's handleSubmit, unchanged from before this split). Every
// field here is optional in the real schema already, so there's nothing to
// gate on before submit besides the existing privacy-consent checkbox.
export function PhysicalStep({
  height,
  setHeight,
  weight,
  setWeight,
  age,
  setAge,
  yearsOfExperience,
  setYearsOfExperience,
  privacyConsent,
  setPrivacyConsent,
  error,
  isSubmitting,
  onSubmit,
  onBack,
}: {
  height: string
  setHeight: (value: string) => void
  weight: string
  setWeight: (value: string) => void
  age: string
  setAge: (value: string) => void
  yearsOfExperience: string
  setYearsOfExperience: (value: string) => void
  privacyConsent: boolean
  setPrivacyConsent: (value: boolean) => void
  error: string | null
  isSubmitting: boolean
  onSubmit: (event: FormEvent) => void
  onBack: () => void
}) {
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Физические данные</h2>
      <p className="text-sm text-text-secondary">Необязательно — можно пропустить и заполнить позже в настройках.</p>

      <div className="grid grid-cols-2 gap-4">
        <TextField
          label="Рост, см"
          name="height"
          type="number"
          numeric
          min={0}
          value={height}
          onChange={(event) => setHeight(event.target.value)}
        />
        <TextField
          label="Вес, кг"
          name="weight"
          type="number"
          numeric
          min={0}
          value={weight}
          onChange={(event) => setWeight(event.target.value)}
        />
        <TextField
          label="Возраст"
          name="age"
          type="number"
          numeric
          min={0}
          value={age}
          onChange={(event) => setAge(event.target.value)}
        />
        <TextField
          label="Стаж в хоккее, лет"
          name="years_of_experience"
          type="number"
          numeric
          min={0}
          step="0.5"
          value={yearsOfExperience}
          onChange={(event) => setYearsOfExperience(event.target.value)}
        />
      </div>

      <label className="flex cursor-pointer items-start gap-2.5">
        <Checkbox checked={privacyConsent} onClick={() => setPrivacyConsent(!privacyConsent)} />
        <span className="text-sm text-text-secondary">
          Я согласен с{' '}
          <Link
            to="/privacy"
            target="_blank"
            rel="noreferrer"
            className="text-accent-ice hover:underline"
            onClick={(event) => event.stopPropagation()}
          >
            Политикой обработки персональных данных
          </Link>
        </span>
      </label>

      <FormError message={error} />
      <div className="flex items-center justify-between">
        <Button type="button" variant="neutral" onClick={onBack} disabled={isSubmitting}>
          Назад
        </Button>
        <Button type="submit" isLoading={isSubmitting} disabled={!privacyConsent}>
          Зарегистрироваться
        </Button>
      </div>
    </form>
  )
}
