import type { FormEvent } from 'react'
import { Button } from '../../components/ui/Button'
import { SelectField } from '../../components/ui/SelectField'
import { TextField } from '../../components/ui/TextField'
import { POSITIONS, POSITION_LABELS } from '../../types/user'

// Step 2/3. Jersey number's actual integer/range check still happens once,
// at final submit in RegisterPage (same as before this split) -- this step
// only relies on the number input's own min/max/required for its own
// "Далее" gate, not a duplicate of that logic.
export function PlayerStep({
  lastName,
  setLastName,
  firstName,
  setFirstName,
  jerseyNumber,
  setJerseyNumber,
  position,
  setPosition,
  onNext,
  onBack,
}: {
  lastName: string
  setLastName: (value: string) => void
  firstName: string
  setFirstName: (value: string) => void
  jerseyNumber: string
  setJerseyNumber: (value: string) => void
  position: string
  setPosition: (value: string) => void
  onNext: () => void
  onBack: () => void
}) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    onNext()
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Игрок</h2>
      <div className="grid grid-cols-2 gap-4">
        <TextField
          label="Фамилия"
          name="last_name"
          autoComplete="family-name"
          value={lastName}
          onChange={(event) => setLastName(event.target.value)}
          maxLength={100}
          required
        />
        <TextField
          label="Имя"
          name="first_name"
          autoComplete="given-name"
          value={firstName}
          onChange={(event) => setFirstName(event.target.value)}
          maxLength={100}
          required
        />
      </div>
      <TextField
        label="Игровой номер"
        name="jersey_number"
        type="number"
        numeric
        min={0}
        max={99}
        value={jerseyNumber}
        onChange={(event) => setJerseyNumber(event.target.value)}
        required
      />
      <SelectField
        label="Позиция"
        name="position"
        placeholder="Не выбрано"
        value={position}
        onChange={(event) => setPosition(event.target.value)}
        options={POSITIONS.map((value) => ({ value, label: POSITION_LABELS[value] }))}
      />
      <div className="flex items-center justify-between">
        <Button type="button" variant="neutral" onClick={onBack}>
          Назад
        </Button>
        <Button type="submit">Далее</Button>
      </div>
    </form>
  )
}
