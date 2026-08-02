import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { ChoiceCard } from '../components/ui/ChoiceCard'
import { FormError } from '../components/ui/FormError'
import { SkillChip } from '../components/ui/SkillChip'
import { TextField } from '../components/ui/TextField'
import { AssessmentTestForm } from './onboarding/AssessmentTestForm'
import * as assessmentApi from '../api/assessment'
import * as skillsApi from '../api/skills'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { AssessmentStatus } from '../types/assessment'
import type { SkillOption } from '../types/skill'
import { EQUIPMENT_CHOICES } from '../types/user'
import type { EquipmentAccess } from '../types/user'

export function SettingsPage() {
  const { user, accessToken, logout, updateUser } = useAuth()
  const navigate = useNavigate()

  const [lastName, setLastName] = useState(user?.last_name ?? '')
  const [firstName, setFirstName] = useState(user?.first_name ?? '')
  const [patronymic, setPatronymic] = useState(user?.patronymic ?? '')
  const [jerseyNumber, setJerseyNumber] = useState(
    user?.jersey_number != null ? String(user.jersey_number) : '',
  )
  const [isSavingProfile, setIsSavingProfile] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileSaved, setProfileSaved] = useState(false)

  const [equipment, setEquipment] = useState<EquipmentAccess | null>(user?.equipment_access ?? null)
  const [isSavingEquipment, setIsSavingEquipment] = useState(false)
  const [equipmentError, setEquipmentError] = useState<string | null>(null)

  const [skills, setSkills] = useState<SkillOption[] | null>(null)
  const [selectedSkillIds, setSelectedSkillIds] = useState<Set<string>>(new Set())
  const [skillsLoadError, setSkillsLoadError] = useState<string | null>(null)
  const [skillsSaveError, setSkillsSaveError] = useState<string | null>(null)

  const [assessmentStatus, setAssessmentStatus] = useState<AssessmentStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [isDismissing, setIsDismissing] = useState(false)
  const [showTestForm, setShowTestForm] = useState(false)
  const [testSuccess, setTestSuccess] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([skillsApi.listSkills(accessToken), usersApi.getSkillPreferences(accessToken)])
      .then(([allSkills, preferences]) => {
        if (cancelled) {
          return
        }
        setSkills(allSkills)
        setSelectedSkillIds(new Set(preferences.map((preference) => preference.skill_id)))
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setSkillsLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить навыки.')
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

  async function handleEquipmentSelect(value: EquipmentAccess) {
    if (accessToken === null || value === equipment) {
      return
    }
    const previous = equipment
    setEquipmentError(null)
    setIsSavingEquipment(true)
    setEquipment(value)
    try {
      const updated = await usersApi.updateEquipmentAccess(value, accessToken)
      updateUser(updated)
    } catch (err) {
      setEquipment(previous)
      setEquipmentError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSavingEquipment(false)
    }
  }

  async function toggleSkill(id: string) {
    if (accessToken === null) {
      return
    }
    const previous = selectedSkillIds
    const next = new Set(previous)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    setSkillsSaveError(null)
    setSelectedSkillIds(next)
    try {
      await usersApi.replaceSkillPreferences(Array.from(next), accessToken)
    } catch (err) {
      setSelectedSkillIds(previous)
      setSkillsSaveError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    }
  }

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

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="mx-auto flex min-h-svh max-w-2xl flex-col gap-8 px-4 py-8">
      <div className="flex flex-col gap-2">
        <BackLink />
        <h1 className="text-xl font-semibold">Настройки</h1>
      </div>

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-medium text-text-secondary">Профиль</h2>
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
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-medium text-text-secondary">Оборудование</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {EQUIPMENT_CHOICES.map((option) => (
            <ChoiceCard
              key={option.value}
              title={option.title}
              description={option.description}
              selected={equipment === option.value}
              disabled={isSavingEquipment}
              onClick={() => handleEquipmentSelect(option.value)}
            />
          ))}
        </div>
        <FormError message={equipmentError} />
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-medium text-text-secondary">Навыки для развития</h2>
        {skills === null && skillsLoadError === null && (
          <p className="text-sm text-text-secondary">Загрузка...</p>
        )}
        <FormError message={skillsLoadError} />
        {skills !== null && (
          <div className="flex flex-wrap gap-2">
            {skills.map((skill) => (
              <SkillChip
                key={skill.id}
                label={skill.name}
                selected={selectedSkillIds.has(skill.id)}
                onClick={() => toggleSkill(skill.id)}
              />
            ))}
          </div>
        )}
        <FormError message={skillsSaveError} />
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="text-sm font-medium text-text-secondary">Оценка физподготовки</h2>
        {assessmentStatus === null && statusError === null && (
          <p className="text-sm text-text-secondary">Загрузка...</p>
        )}
        <FormError message={statusError} />

        {assessmentStatus?.suggested_reassessment === true && (
          <div className="flex flex-col gap-3 rounded-md border border-accent-persimmon/40 bg-accent-persimmon/10 p-4">
            <p className="text-sm text-text-primary">
              Похоже, ваш уровень подготовки изменился. Стоит пройти тест заново, чтобы точнее
              откалибровать характеристики.
            </p>
            <div className="flex gap-3">
              <Button onClick={() => setShowTestForm(true)} disabled={showTestForm}>
                Пройти тест заново
              </Button>
              <Button variant="neutral" onClick={handleDismissReassessment} isLoading={isDismissing}>
                Не сейчас
              </Button>
            </div>
          </div>
        )}

        {assessmentStatus?.suggested_reassessment === false && !showTestForm && (
          <Button variant="neutral" onClick={() => setShowTestForm(true)} className="self-start">
            Пройти тест заново
          </Button>
        )}

        {testSuccess && <p className="text-sm text-accent-ice">Результаты сохранены.</p>}

        {showTestForm && accessToken !== null && (
          <AssessmentTestForm accessToken={accessToken} onSuccess={handleTestSuccess} />
        )}
      </section>

      <Button variant="neutral" onClick={handleLogout} className="mt-4 self-start">
        Выйти из аккаунта
      </Button>
    </div>
  )
}
