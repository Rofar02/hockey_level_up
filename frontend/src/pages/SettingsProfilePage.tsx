import { useState } from 'react'
import type { CSSProperties, FormEvent } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { SelectField } from '../components/ui/SelectField'
import { TextField } from '../components/ui/TextField'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import {
  AVATAR_RING_ACCENTS,
  AVATAR_RING_ACCENT_LABELS,
  JERSEY_COLORS,
  JERSEY_COLOR_LABELS,
  POSITIONS,
  POSITION_LABELS,
} from '../types/user'
import type { AvatarRingAccent, JerseyColor, Position } from '../types/user'
import { LEVEL_AVATAR_RING_CHOICE, LEVEL_JERSEY_COLOR_CHOICE, hasAvatarRingChoice, hasJerseyColorChoice } from '../utils/levelUnlocks'

// Flat swatch previews, not a re-derivation of avatarTier.ts's own
// border/box-shadow styling -- that module is tuned for a ring (a border
// around a photo), this is just "which color am I picking" at a glance.
const AVATAR_RING_SWATCH_STYLE: Record<AvatarRingAccent, CSSProperties> = {
  ice: { background: '#D7EFFF' },
  persimmon: { background: '#FF5C34' },
  mix: { background: 'linear-gradient(135deg, #D7EFFF, #FF5C34)' },
}

const JERSEY_COLOR_SWATCH_STYLE: Record<JerseyColor, CSSProperties> = {
  white: { background: '#F5F7FA' },
  ice: { background: '#D7EFFF' },
  persimmon: { background: '#FF5C34' },
  gold: { background: '#FFC94A' },
}

// Same convention RegisterPage's own PhysicalStep uses for these same
// fields -- empty/unparseable clears the field rather than erroring
// client-side, the backend's own gt=0 validation is the real gate.
function toOptionalNumber(value: string): number | null {
  if (value.trim() === '') {
    return null
  }
  const parsed = Number(value)
  return Number.isNaN(parsed) ? null : parsed
}

export function SettingsProfilePage() {
  const { user, accessToken, updateUser } = useAuth()

  const [lastName, setLastName] = useState(user?.last_name ?? '')
  const [firstName, setFirstName] = useState(user?.first_name ?? '')
  const [patronymic, setPatronymic] = useState(user?.patronymic ?? '')
  const [jerseyNumber, setJerseyNumber] = useState(
    user?.jersey_number != null ? String(user.jersey_number) : '',
  )
  // Registration's PhysicalStep explicitly tells the athlete these four are
  // skippable there and fillable "later in настройках" -- this is that
  // later (previously the profile form had no way to touch them at all).
  const [height, setHeight] = useState(user?.height != null ? String(user.height) : '')
  const [weight, setWeight] = useState(user?.weight != null ? String(user.weight) : '')
  const [age, setAge] = useState(user?.age != null ? String(user.age) : '')
  const [position, setPosition] = useState<Position | ''>(user?.position ?? '')
  const [yearsOfExperience, setYearsOfExperience] = useState(
    user?.years_of_experience != null ? String(user.years_of_experience) : '',
  )
  const [isSavingProfile, setIsSavingProfile] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileSaved, setProfileSaved] = useState(false)

  const [avatarRingAccent, setAvatarRingAccent] = useState(user?.avatar_ring_accent ?? null)
  const [isSavingAvatarRing, setIsSavingAvatarRing] = useState(false)
  const [avatarRingError, setAvatarRingError] = useState<string | null>(null)

  const [jerseyColor, setJerseyColor] = useState(user?.jersey_color ?? null)
  const [isSavingJerseyColor, setIsSavingJerseyColor] = useState(false)
  const [jerseyColorError, setJerseyColorError] = useState<string | null>(null)

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
    const heightValue = toOptionalNumber(height)
    const weightValue = toOptionalNumber(weight)
    const ageValue = toOptionalNumber(age)
    const yearsOfExperienceValue = toOptionalNumber(yearsOfExperience)
    const positionValue = position === '' ? null : position

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
    if (heightValue !== user.height) {
      updates.height = heightValue
    }
    if (weightValue !== user.weight) {
      updates.weight = weightValue
    }
    if (ageValue !== user.age) {
      updates.age = ageValue
    }
    if (positionValue !== user.position) {
      updates.position = positionValue
    }
    if (yearsOfExperienceValue !== user.years_of_experience) {
      updates.years_of_experience = yearsOfExperienceValue
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

  // Save-on-tap, same convention as SettingsEquipmentPage's
  // handleGymAccessSelect/SettingsTrainingPage's handleSeasonPeriodSelect --
  // a single swatch pick has nothing else to batch with, so a separate
  // "Сохранить" step would just be an extra tap for no reason.
  async function handleAvatarRingSelect(value: AvatarRingAccent) {
    if (accessToken === null || value === avatarRingAccent) {
      return
    }
    const previous = avatarRingAccent
    setAvatarRingError(null)
    setIsSavingAvatarRing(true)
    setAvatarRingAccent(value)
    try {
      const updated = await usersApi.updateProfile({ avatar_ring_accent: value }, accessToken)
      updateUser(updated)
    } catch (err) {
      setAvatarRingAccent(previous)
      setAvatarRingError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSavingAvatarRing(false)
    }
  }

  async function handleJerseyColorSelect(value: JerseyColor) {
    if (accessToken === null || value === jerseyColor) {
      return
    }
    const previous = jerseyColor
    setJerseyColorError(null)
    setIsSavingJerseyColor(true)
    setJerseyColor(value)
    try {
      const updated = await usersApi.updateProfile({ jersey_color: value }, accessToken)
      updateUser(updated)
    } catch (err) {
      setJerseyColor(previous)
      setJerseyColorError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSavingJerseyColor(false)
    }
  }

  const userLevel = user?.level ?? 1

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-8 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
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
          <div className="grid grid-cols-2 gap-4">
            <TextField
              label="Рост, см (необязательно)"
              name="height"
              type="number"
              numeric
              min={0}
              value={height}
              onChange={(event) => setHeight(event.target.value)}
            />
            <TextField
              label="Вес, кг (необязательно)"
              name="weight"
              type="number"
              numeric
              min={0}
              value={weight}
              onChange={(event) => setWeight(event.target.value)}
            />
            <TextField
              label="Возраст (необязательно)"
              name="age"
              type="number"
              numeric
              min={0}
              value={age}
              onChange={(event) => setAge(event.target.value)}
            />
            <TextField
              label="Стаж в хоккее, лет (необязательно)"
              name="years_of_experience"
              type="number"
              numeric
              min={0}
              step="0.5"
              value={yearsOfExperience}
              onChange={(event) => setYearsOfExperience(event.target.value)}
            />
          </div>
          <SelectField
            label="Позиция (необязательно)"
            name="position"
            placeholder="Не выбрано"
            value={position}
            onChange={(event) => setPosition(event.target.value as Position | '')}
            options={POSITIONS.map((value) => ({ value, label: POSITION_LABELS[value] }))}
          />
          <FormError message={profileError} />
          {profileSaved && <p className="text-sm text-accent-ice">Сохранено.</p>}
          <Button type="submit" isLoading={isSavingProfile} className="self-start">
            Сохранить
          </Button>
        </form>

        <section className="flex flex-col gap-4">
          <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
            <i className="ti ti-circles text-accent-ice" aria-hidden="true" />
            Кольцо аватарки
            <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
          </h2>
          {hasAvatarRingChoice(userLevel) ? (
            <>
              <div className="flex gap-3">
                {AVATAR_RING_ACCENTS.map((accent) => (
                  <button
                    key={accent}
                    type="button"
                    onClick={() => handleAvatarRingSelect(accent)}
                    disabled={isSavingAvatarRing}
                    className={`flex flex-1 flex-col items-center gap-2 rounded-md border p-3 transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      avatarRingAccent === accent
                        ? 'border-accent-ice bg-accent-ice/10'
                        : 'border-white/10 hover:border-white/20'
                    }`}
                  >
                    <span className="h-8 w-8 rounded-full" style={AVATAR_RING_SWATCH_STYLE[accent]} />
                    <span className="text-xs text-text-secondary">{AVATAR_RING_ACCENT_LABELS[accent]}</span>
                  </button>
                ))}
              </div>
              <FormError message={avatarRingError} />
            </>
          ) : (
            <p className="flex items-center gap-1.5 text-xs text-[#8A94A6]">
              <i className="ti ti-lock text-xs" aria-hidden="true" />
              Доступно с уровня {LEVEL_AVATAR_RING_CHOICE}
            </p>
          )}
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
            <i className="ti ti-palette text-accent-ice" aria-hidden="true" />
            Цвет номера
            <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
          </h2>
          {hasJerseyColorChoice(userLevel) ? (
            <>
              <div className="flex gap-3">
                {JERSEY_COLORS.map((color) => (
                  <button
                    key={color}
                    type="button"
                    onClick={() => handleJerseyColorSelect(color)}
                    disabled={isSavingJerseyColor}
                    className={`flex flex-1 flex-col items-center gap-2 rounded-md border p-3 transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                      jerseyColor === color
                        ? 'border-accent-ice bg-accent-ice/10'
                        : 'border-white/10 hover:border-white/20'
                    }`}
                  >
                    <span className="h-8 w-8 rounded-full" style={JERSEY_COLOR_SWATCH_STYLE[color]} />
                    <span className="text-xs text-text-secondary">{JERSEY_COLOR_LABELS[color]}</span>
                  </button>
                ))}
              </div>
              <FormError message={jerseyColorError} />
            </>
          ) : (
            <p className="flex items-center gap-1.5 text-xs text-[#8A94A6]">
              <i className="ti ti-lock text-xs" aria-hidden="true" />
              Доступно с уровня {LEVEL_JERSEY_COLOR_CHOICE}
            </p>
          )}
        </section>
      </div>
    </div>
  )
}
