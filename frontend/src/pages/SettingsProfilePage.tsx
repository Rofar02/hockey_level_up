import { useState } from 'react'
import type { FormEvent } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { TextField } from '../components/ui/TextField'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

export function SettingsProfilePage() {
  const { user, accessToken, updateUser } = useAuth()

  const [lastName, setLastName] = useState(user?.last_name ?? '')
  const [firstName, setFirstName] = useState(user?.first_name ?? '')
  const [patronymic, setPatronymic] = useState(user?.patronymic ?? '')
  const [jerseyNumber, setJerseyNumber] = useState(
    user?.jersey_number != null ? String(user.jersey_number) : '',
  )
  const [isSavingProfile, setIsSavingProfile] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileSaved, setProfileSaved] = useState(false)

  async function handleProfileSave(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null || user === null) {
      return
    }
    setProfileError(null)
    setProfileSaved(false)

    let jerseyValue: number | null = null
    if (jerseyNumber.trim() !== '') {
      const parsed = Number(jerseyNumber)
      if (!Number.isInteger(parsed) || parsed < 0 || parsed > 99) {
        setProfileError('Номер должен быть целым числом от 0 до 99.')
        return
      }
      jerseyValue = parsed
    }
    const patronymicValue = patronymic.trim() === '' ? null : patronymic

    // Only PATCH fields that actually changed from the last-known user.
    const updates: usersApi.UserProfileUpdate = {}
    if (lastName !== user.last_name) {
      updates.last_name = lastName
    }
    if (firstName !== user.first_name) {
      updates.first_name = firstName
    }
    if (patronymicValue !== user.patronymic) {
      updates.patronymic = patronymicValue
    }
    if (jerseyValue !== user.jersey_number) {
      updates.jersey_number = jerseyValue
    }

    if (Object.keys(updates).length === 0) {
      setProfileSaved(true)
      return
    }

    setIsSavingProfile(true)
    try {
      const updated = await usersApi.updateProfile(updates, accessToken)
      updateUser(updated)
      setProfileSaved(true)
    } catch (err) {
      setProfileError(err instanceof ApiError ? err.message : 'Не удалось сохранить. Попробуйте ещё раз.')
    } finally {
      setIsSavingProfile(false)
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink to="/settings" />
          <h1 className="text-xl font-semibold">Профиль</h1>
        </div>

        <form onSubmit={handleProfileSave} className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-4">
            <TextField
              label="Фамилия"
              name="last_name"
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
              maxLength={100}
              required
            />
            <TextField
              label="Имя"
              name="first_name"
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
              maxLength={100}
              required
            />
          </div>
          <TextField
            label="Отчество (необязательно)"
            name="patronymic"
            value={patronymic}
            onChange={(event) => setPatronymic(event.target.value)}
            maxLength={100}
          />
          <TextField
            label="Номер (необязательно)"
            name="jersey_number"
            type="number"
            numeric
            min={0}
            max={99}
            value={jerseyNumber}
            onChange={(event) => setJerseyNumber(event.target.value)}
          />
          <FormError message={profileError} />
          {profileSaved && <p className="text-sm text-accent-ice">Сохранено.</p>}
          <Button type="submit" isLoading={isSavingProfile} className="self-start">
            Сохранить
          </Button>
        </form>
      </div>
    </div>
  )
}
