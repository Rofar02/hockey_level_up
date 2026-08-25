import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { ChoiceCard } from '../components/ui/ChoiceCard'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { SelectField } from '../components/ui/SelectField'
import { LockedSkillChip, SkillChip } from '../components/ui/SkillChip'
import { Switch } from '../components/ui/Switch'
import { TextField } from '../components/ui/TextField'
import { AssessmentTestForm } from './onboarding/AssessmentTestForm'
import { OnIceAssessmentTestForm } from './onboarding/OnIceAssessmentTestForm'
import * as assessmentApi from '../api/assessment'
import * as exercisesApi from '../api/exercises'
import * as pushApi from '../api/push'
import * as skillsApi from '../api/skills'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { getActivePushSubscription, isIos, isPushSupported, isStandalone, subscribeToPush } from '../push'
import type { AssessmentStatus, OnIceAssessmentStatus } from '../types/assessment'
import { EQUIPMENT_ITEM_LABELS, GYM_COVERED_ITEMS, PERSONAL_GEAR_ITEMS } from '../types/exercise'
import type { EquipmentItem, ExerciseEquipmentRequirement } from '../types/exercise'
import type { SkillOption } from '../types/skill'
import { COACH_PERSONALITY_CHOICES, REMINDER_PREFERENCE_LABELS, SEASON_PERIOD_CHOICES } from '../types/user'
import type { CoachPersonality, ReminderPreference, SeasonPeriod } from '../types/user'
import {
  TYPICAL_HOME_PRESET,
  applyGymCoveredPreset,
  countAvailableExercises,
} from '../utils/equipmentAvailability'
import { maxSkillPreferencesForLevel } from '../utils/skillPreferenceLimit'
import { toIsoDate } from '../utils/date'

export function SettingsPage() {
  const { user, accessToken, logout, updateUser } = useAuth()
  const navigate = useNavigate()

  const maxSkillPreferences = user !== null ? maxSkillPreferencesForLevel(user.level) : null

  const [lastName, setLastName] = useState(user?.last_name ?? '')
  const [firstName, setFirstName] = useState(user?.first_name ?? '')
  const [patronymic, setPatronymic] = useState(user?.patronymic ?? '')
  const [jerseyNumber, setJerseyNumber] = useState(
    user?.jersey_number != null ? String(user.jersey_number) : '',
  )
  const [isSavingProfile, setIsSavingProfile] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileSaved, setProfileSaved] = useState(false)

  const [hasGymAccess, setHasGymAccess] = useState(user?.has_gym_access ?? false)
  const [isSavingGymAccess, setIsSavingGymAccess] = useState(false)
  const [gymAccessError, setGymAccessError] = useState<string | null>(null)

  const [ownedItems, setOwnedItems] = useState<Set<EquipmentItem> | null>(null)
  const [ownedItemsLoadError, setOwnedItemsLoadError] = useState<string | null>(null)
  const [ownedItemsSaveError, setOwnedItemsSaveError] = useState<string | null>(null)
  const [equipmentRequirements, setEquipmentRequirements] = useState<ExerciseEquipmentRequirement[] | null>(null)

  const [seasonPeriod, setSeasonPeriod] = useState<SeasonPeriod | null>(user?.season_period ?? null)
  const [isSavingSeasonPeriod, setIsSavingSeasonPeriod] = useState(false)
  const [seasonPeriodError, setSeasonPeriodError] = useState<string | null>(null)

  const [coachPersonality, setCoachPersonality] = useState<CoachPersonality | null>(
    user?.coach_personality ?? null,
  )
  const [isSavingCoachPersonality, setIsSavingCoachPersonality] = useState(false)
  const [coachPersonalityError, setCoachPersonalityError] = useState<string | null>(null)

  const [tournamentDate, setTournamentDate] = useState<string | null>(user?.tournament_date ?? null)
  const [isSavingTournamentDate, setIsSavingTournamentDate] = useState(false)
  const [tournamentDateError, setTournamentDateError] = useState<string | null>(null)
  const todayIso = toIsoDate(new Date())

  const [skills, setSkills] = useState<SkillOption[] | null>(null)
  const [selectedSkillIds, setSelectedSkillIds] = useState<Set<string>>(new Set())
  const [skillsLoadError, setSkillsLoadError] = useState<string | null>(null)
  const [skillsSaveError, setSkillsSaveError] = useState<string | null>(null)

  const [assessmentStatus, setAssessmentStatus] = useState<AssessmentStatus | null>(null)
  const [statusError, setStatusError] = useState<string | null>(null)
  const [isDismissing, setIsDismissing] = useState(false)
  const [showTestForm, setShowTestForm] = useState(false)
  const [testSuccess, setTestSuccess] = useState(false)

  const [onIceStatus, setOnIceStatus] = useState<OnIceAssessmentStatus | null>(null)
  const [onIceStatusError, setOnIceStatusError] = useState<string | null>(null)
  const [showOnIceTestForm, setShowOnIceTestForm] = useState(false)
  const [onIceTestSuccess, setOnIceTestSuccess] = useState(false)

  const [pushSupported] = useState(() => isPushSupported())
  // Unsupported for the fixable reason (iOS Safari, not installed to the
  // home screen) vs. every other unsupported case, which has no fix to
  // point the user at -- see push.ts for why standalone gates PushManager.
  const [needsIosHomeScreenInstall] = useState(
    () => !isPushSupported() && isIos() && !isStandalone(),
  )
  const [pushPermission, setPushPermission] = useState<NotificationPermission | null>(() =>
    isPushSupported() ? Notification.permission : null,
  )
  const [pushSubscribed, setPushSubscribed] = useState(false)
  const [pushStatusChecked, setPushStatusChecked] = useState(false)
  const [isPushBusy, setIsPushBusy] = useState(false)
  const [pushError, setPushError] = useState<string | null>(null)
  const [isSendingTestPush, setIsSendingTestPush] = useState(false)
  const [testPushSuccess, setTestPushSuccess] = useState(false)
  const [reminderPreference, setReminderPreference] = useState<Exclude<ReminderPreference, 'none'>>(
    user?.reminder_preference !== undefined && user.reminder_preference !== 'none'
      ? user.reminder_preference
      : 'morning',
  )

  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    usersApi
      .getMyEquipmentItems(accessToken)
      .then((items) => {
        if (!cancelled) {
          setOwnedItems(new Set(items))
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setOwnedItemsLoadError(
            err instanceof ApiError ? err.message : 'Не удалось загрузить инвентарь.',
          )
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
    exercisesApi
      .listExerciseEquipmentRequirements(accessToken)
      .then((result) => {
        if (!cancelled) {
          setEquipmentRequirements(result)
        }
      })
      .catch(() => {
        // Best-effort -- the toggles still work without a live counter.
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

  useEffect(() => {
    if (!pushSupported) {
      return
    }
    // The server has no record of "is this browser currently subscribed" --
    // permission can be revoked from OS/browser settings behind the app's
    // back, so the only trustworthy source is the browser's own state.
    let cancelled = false
    getActivePushSubscription()
      .then((subscription) => {
        if (!cancelled) {
          setPushSubscribed(subscription !== null)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPushStatusChecked(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [pushSupported])

  async function handlePushToggle() {
    if (accessToken === null || isPushBusy) {
      return
    }
    setPushError(null)
    setTestPushSuccess(false)
    setIsPushBusy(true)
    try {
      if (pushSubscribed) {
        const subscription = await getActivePushSubscription()
        if (subscription !== null) {
          await pushApi.deletePushSubscription(subscription.endpoint, accessToken)
          await subscription.unsubscribe()
        }
        setPushSubscribed(false)
        try {
          const updated = await usersApi.updateProfile(
            { reminder_preference: 'none' },
            accessToken,
          )
          updateUser(updated)
        } catch {
          // Best-effort -- the browser subscription is already gone either
          // way, so a stale server-side preference is harmless until the
          // next successful save.
        }
        return
      }

      if (Notification.permission === 'denied') {
        setPushError('Уведомления заблокированы в настройках браузера.')
        return
      }
      const permission = await Notification.requestPermission()
      setPushPermission(permission)
      if (permission !== 'granted') {
        setPushError('Уведомления заблокированы в настройках браузера.')
        return
      }

      const { public_key: vapidPublicKey } = await pushApi.getVapidPublicKey(accessToken)
      const subscription = await subscribeToPush(vapidPublicKey)
      const json = subscription.toJSON()
      if (json.endpoint === undefined || json.keys === undefined) {
        throw new Error('Некорректная push-подписка браузера.')
      }
      await pushApi.savePushSubscription(
        { endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth } },
        accessToken,
      )
      const updated = await usersApi.updateProfile(
        {
          reminder_preference: reminderPreference,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        },
        accessToken,
      )
      updateUser(updated)
      setPushSubscribed(true)
    } catch (err) {
      setPushError(
        err instanceof ApiError ? err.message : 'Не удалось изменить настройку уведомлений.',
      )
    } finally {
      setIsPushBusy(false)
    }
  }

  async function handleReminderPreferenceChange(value: Exclude<ReminderPreference, 'none'>) {
    if (accessToken === null || value === reminderPreference) {
      return
    }
    const previous = reminderPreference
    setReminderPreference(value)
    setPushError(null)
    try {
      const updated = await usersApi.updateProfile({ reminder_preference: value }, accessToken)
      updateUser(updated)
    } catch (err) {
      setReminderPreference(previous)
      setPushError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор.')
    }
  }

  async function handleSendTestPush() {
    if (accessToken === null) {
      return
    }
    setPushError(null)
    setTestPushSuccess(false)
    setIsSendingTestPush(true)
    try {
      await pushApi.sendTestPushNotification(accessToken)
      setTestPushSuccess(true)
    } catch (err) {
      setPushError(
        err instanceof ApiError ? err.message : 'Не удалось отправить тестовое уведомление.',
      )
    } finally {
      setIsSendingTestPush(false)
    }
  }

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

  async function handleGymAccessSelect(value: boolean) {
    if (accessToken === null || value === hasGymAccess) {
      return
    }
    const previous = hasGymAccess
    setGymAccessError(null)
    setIsSavingGymAccess(true)
    setHasGymAccess(value)
    try {
      const updated = await usersApi.updateProfile({ has_gym_access: value }, accessToken)
      updateUser(updated)
    } catch (err) {
      setHasGymAccess(previous)
      setGymAccessError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSavingGymAccess(false)
    }
  }

  async function toggleOwnedItem(item: EquipmentItem) {
    if (accessToken === null || ownedItems === null) {
      return
    }
    const previous = ownedItems
    const next = new Set(previous)
    if (next.has(item)) {
      next.delete(item)
    } else {
      next.add(item)
    }
    setOwnedItemsSaveError(null)
    setOwnedItems(next)
    try {
      await usersApi.replaceMyEquipmentItems(Array.from(next), accessToken)
    } catch (err) {
      setOwnedItems(previous)
      setOwnedItemsSaveError(
        err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.',
      )
    }
  }

  async function applyHomePreset() {
    if (accessToken === null) {
      return
    }
    const previousGymAccess = hasGymAccess
    const previousItems = ownedItems
    const nextItems = applyGymCoveredPreset(TYPICAL_HOME_PRESET, ownedItems ?? new Set())
    setGymAccessError(null)
    setOwnedItemsSaveError(null)
    setHasGymAccess(false)
    setOwnedItems(nextItems)
    try {
      if (hasGymAccess) {
        const updated = await usersApi.updateProfile({ has_gym_access: false }, accessToken)
        updateUser(updated)
      }
      await usersApi.replaceMyEquipmentItems(Array.from(nextItems), accessToken)
    } catch (err) {
      setHasGymAccess(previousGymAccess)
      setOwnedItems(previousItems)
      setOwnedItemsSaveError(
        err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.',
      )
    }
  }

  async function handleSeasonPeriodSelect(value: SeasonPeriod) {
    if (accessToken === null || value === seasonPeriod) {
      return
    }
    const previous = seasonPeriod
    setSeasonPeriodError(null)
    setIsSavingSeasonPeriod(true)
    setSeasonPeriod(value)
    try {
      const updated = await usersApi.updateProfile({ season_period: value }, accessToken)
      updateUser(updated)
    } catch (err) {
      setSeasonPeriod(previous)
      setSeasonPeriodError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSavingSeasonPeriod(false)
    }
  }

  async function handleCoachPersonalitySelect(value: CoachPersonality) {
    if (accessToken === null || value === coachPersonality) {
      return
    }
    const previous = coachPersonality
    setCoachPersonalityError(null)
    setIsSavingCoachPersonality(true)
    setCoachPersonality(value)
    try {
      const updated = await usersApi.updateProfile({ coach_personality: value }, accessToken)
      updateUser(updated)
    } catch (err) {
      setCoachPersonality(previous)
      setCoachPersonalityError(
        err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.',
      )
    } finally {
      setIsSavingCoachPersonality(false)
    }
  }

  async function handleTournamentDateChange(value: string) {
    if (accessToken === null) {
      return
    }
    const previous = tournamentDate
    const next = value === '' ? null : value
    setTournamentDateError(null)
    setIsSavingTournamentDate(true)
    setTournamentDate(next)
    try {
      const updated = await usersApi.updateProfile({ tournament_date: next }, accessToken)
      updateUser(updated)
    } catch (err) {
      setTournamentDate(previous)
      setTournamentDateError(err instanceof ApiError ? err.message : 'Не удалось сохранить дату. Попробуйте ещё раз.')
    } finally {
      setIsSavingTournamentDate(false)
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

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  function openDeleteModal() {
    setDeletePassword('')
    setDeleteError(null)
    setShowDeleteModal(true)
  }

  async function handleDeleteAccount(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null) {
      return
    }
    setDeleteError(null)
    setIsDeleting(true)
    try {
      await usersApi.deleteAccount(deletePassword, accessToken)
      logout()
      navigate('/login', { replace: true })
    } catch (err) {
      setDeleteError(
        err instanceof ApiError ? err.message : 'Не удалось удалить аккаунт. Попробуйте ещё раз.',
      )
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-8 px-4 py-8">
      <div className="flex flex-col gap-2">
        <BackLink />
        <h1 className="text-xl font-semibold">Настройки</h1>
      </div>

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
          <i className="ti ti-user text-accent-ice" aria-hidden="true" />
          Профиль
        </h2>
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
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
          <i className="ti ti-barbell text-accent-ice" aria-hidden="true" />
          Оборудование
        </h2>
        <div className="flex flex-wrap gap-3">
          <Button
            type="button"
            variant="neutral"
            onClick={() => handleGymAccessSelect(true)}
            disabled={isSavingGymAccess}
          >
            Зал
          </Button>
          <Button type="button" variant="neutral" onClick={applyHomePreset} disabled={isSavingGymAccess}>
            Типичный домашний набор
          </Button>
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <ChoiceCard
            title="Тренажёрный зал"
            description="Полный доступ к тренажёрам и свободным весам"
            selected={hasGymAccess}
            disabled={isSavingGymAccess}
            onClick={() => handleGymAccessSelect(true)}
          />
          <ChoiceCard
            title="Свой инвентарь"
            description="Отметьте ниже, что есть — пусто тоже подходит, тренировки без инвентаря"
            selected={!hasGymAccess}
            disabled={isSavingGymAccess}
            onClick={() => handleGymAccessSelect(false)}
          />
        </div>
        <FormError message={gymAccessError} />

        <FormError message={ownedItemsLoadError} />
        {!hasGymAccess && ownedItems !== null && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {GYM_COVERED_ITEMS.map((item) => (
              <label key={item} className="flex items-center gap-2 text-sm text-text-primary">
                <input
                  type="checkbox"
                  checked={ownedItems.has(item)}
                  onChange={() => toggleOwnedItem(item)}
                  className="h-4 w-4"
                />
                {EQUIPMENT_ITEM_LABELS[item]}
              </label>
            ))}
          </div>
        )}

        {ownedItems !== null && (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-[#8A94A6]">
              Своё снаряжение — не покрывается доступом в зал, отмечайте отдельно.
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {PERSONAL_GEAR_ITEMS.map((item) => (
                <label key={item} className="flex items-center gap-2 text-sm text-text-primary">
                  <input
                    type="checkbox"
                    checked={ownedItems.has(item)}
                    onChange={() => toggleOwnedItem(item)}
                    className="h-4 w-4"
                  />
                  {EQUIPMENT_ITEM_LABELS[item]}
                </label>
              ))}
            </div>
          </div>
        )}
        <FormError message={ownedItemsSaveError} />

        {equipmentRequirements !== null && ownedItems !== null && (
          <p className="text-sm text-accent-ice">
            Доступно {countAvailableExercises(equipmentRequirements, hasGymAccess, ownedItems)} из{' '}
            {equipmentRequirements.length} упражнений
          </p>
        )}
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
          <i className="ti ti-calendar text-accent-ice" aria-hidden="true" />
          Период сезона
        </h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {SEASON_PERIOD_CHOICES.map((option) => (
            <ChoiceCard
              key={option.value}
              title={option.title}
              description={option.description}
              selected={seasonPeriod === option.value}
              disabled={isSavingSeasonPeriod}
              onClick={() => handleSeasonPeriodSelect(option.value)}
            />
          ))}
        </div>
        <FormError message={seasonPeriodError} />
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
          <i className="ti ti-message-chatbot text-accent-ice" aria-hidden="true" />
          Личность тренера
        </h2>
        <p className="text-xs text-[#8A94A6]">Влияет на тон напоминаний о тренировках</p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {COACH_PERSONALITY_CHOICES.map((option) => (
            <ChoiceCard
              key={option.value}
              title={option.title}
              description={option.description}
              selected={coachPersonality === option.value}
              disabled={isSavingCoachPersonality}
              onClick={() => handleCoachPersonalitySelect(option.value)}
            />
          ))}
        </div>
        <FormError message={coachPersonalityError} />
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
          <i className="ti ti-trophy text-accent-ice" aria-hidden="true" />
          Дата турнира
        </h2>
        <p className="text-xs text-[#8A94A6]">
          За 3 недели до этой даты объём тренировок начнёт снижаться, в последнюю неделю — резко.
        </p>
        <TextField
          label="Дата"
          type="date"
          min={todayIso}
          value={tournamentDate ?? ''}
          disabled={isSavingTournamentDate}
          onChange={(event) => handleTournamentDateChange(event.target.value)}
        />
        <FormError message={tournamentDateError} />
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
          <i className="ti ti-target text-accent-ice" aria-hidden="true" />
          Навыки для развития
        </h2>
        {skills === null && skillsLoadError === null && (
          <p className="text-sm text-[#8A94A6]">Загрузка...</p>
        )}
        <FormError message={skillsLoadError} />
        {/* maxSkillPreferences is null at level 25+ (unlimited) -- omitted
            entirely rather than showing "X из ∞". */}
        {maxSkillPreferences !== null && (
          <p className="text-sm text-[#8A94A6]">
            Выбрано {selectedSkillIds.size} из {maxSkillPreferences}
          </p>
        )}
        {skills !== null && (
          <div className="flex flex-wrap gap-2">
            {skills.map((skill) => {
              // Locked skills are still shown (not filtered out) -- with a
              // lock icon and unlock level instead of a toggle, independent
              // of the slot-limit check below.
              if (skill.required_level > (user?.level ?? 1)) {
                return (
                  <LockedSkillChip
                    key={skill.id}
                    label={skill.name}
                    requiredLevel={skill.required_level}
                  />
                )
              }
              const isSelected = selectedSkillIds.has(skill.id)
              const limitReached =
                maxSkillPreferences !== null && selectedSkillIds.size >= maxSkillPreferences
              return (
                <SkillChip
                  key={skill.id}
                  label={skill.name}
                  selected={isSelected}
                  disabled={!isSelected && limitReached}
                  onClick={() => toggleSkill(skill.id)}
                />
              )
            })}
          </div>
        )}
        <FormError message={skillsSaveError} />
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
          <i className="ti ti-clipboard-list text-accent-ice" aria-hidden="true" />
          Оценка физподготовки
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

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
          <i className="ti ti-bell text-accent-ice" aria-hidden="true" />
          Уведомления
        </h2>
        {!pushSupported && needsIosHomeScreenInstall && (
          <p className="text-sm text-text-secondary">
            Добавьте приложение на домашний экран (Поделиться → «На экран «Домой»»), чтобы получать
            уведомления.
          </p>
        )}
        {!pushSupported && !needsIosHomeScreenInstall && (
          <p className="text-sm text-text-secondary">
            Этот браузер не поддерживает push-уведомления.
          </p>
        )}
        {pushSupported && (
          <>
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-medium text-text-primary">Напоминания о тренировках</p>
                <p className="text-sm text-text-secondary">Push-уведомления в этом браузере</p>
              </div>
              <Switch
                checked={pushSubscribed}
                disabled={isPushBusy || !pushStatusChecked}
                onClick={handlePushToggle}
              />
            </div>
            {pushPermission === 'denied' && (
              <p className="text-sm text-text-secondary">
                Уведомления заблокированы в настройках браузера.
              </p>
            )}
            <FormError message={pushError} />
            {pushSubscribed && (
              <>
                <SelectField
                  label="Когда напоминать"
                  value={reminderPreference}
                  onChange={(event) =>
                    handleReminderPreferenceChange(
                      event.target.value as Exclude<ReminderPreference, 'none'>,
                    )
                  }
                  options={Object.entries(REMINDER_PREFERENCE_LABELS).map(([value, label]) => ({
                    value,
                    label,
                  }))}
                />
                <Button
                  variant="neutral"
                  onClick={handleSendTestPush}
                  isLoading={isSendingTestPush}
                  className="self-start"
                >
                  Отправить тестовое уведомление
                </Button>
                {testPushSuccess && (
                  <p className="text-sm text-accent-ice">Уведомление отправлено.</p>
                )}
              </>
            )}
          </>
        )}
      </section>

      {user?.is_admin === true && (
        <Link
          to="/admin"
          className="self-start rounded px-4 py-2.5 font-medium text-accent-ice transition-colors hover:underline"
        >
          Админ-панель
        </Link>
      )}

      <Button variant="neutral" onClick={handleLogout} className="mt-4 self-start">
        Выйти из аккаунта
      </Button>

      <section className="flex flex-col gap-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
          <i className="ti ti-alert-triangle text-accent-persimmon" aria-hidden="true" />
          Удаление аккаунта
        </h2>
        <div className="flex flex-col gap-3 rounded-md border border-accent-persimmon/40 bg-accent-persimmon/10 p-4">
          <p className="text-sm text-[#F5F7FA]">
            Аккаунт и все связанные данные — тренировки, прогресс, статистика, навыки — будут
            удалены безвозвратно. Это действие нельзя отменить.
          </p>
          <Button
            variant="neutral"
            onClick={openDeleteModal}
            className="self-start border-accent-persimmon/60 text-accent-persimmon hover:bg-accent-persimmon/10"
          >
            Удалить аккаунт
          </Button>
        </div>
      </section>
      </div>

      {showDeleteModal && (
        <Modal title="Удалить аккаунт?" onClose={() => setShowDeleteModal(false)}>
          <form onSubmit={handleDeleteAccount} className="flex flex-col gap-4">
            <p className="text-sm text-text-secondary">
              Это действие необратимо. Введите пароль, чтобы подтвердить удаление аккаунта и
              всех связанных данных.
            </p>
            <TextField
              label="Пароль"
              name="delete_password"
              type="password"
              autoComplete="current-password"
              value={deletePassword}
              onChange={(event) => setDeletePassword(event.target.value)}
              required
            />
            <FormError message={deleteError} />
            <div className="flex gap-3">
              <Button type="submit" isLoading={isDeleting}>
                Удалить аккаунт
              </Button>
              <Button
                type="button"
                variant="neutral"
                onClick={() => setShowDeleteModal(false)}
                disabled={isDeleting}
              >
                Отмена
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
