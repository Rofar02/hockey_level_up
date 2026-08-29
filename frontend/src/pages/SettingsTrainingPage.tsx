import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { ChoiceCard } from '../components/ui/ChoiceCard'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { LockedSkillChip, SkillChip } from '../components/ui/SkillChip'
import { TextField } from '../components/ui/TextField'
import * as skillsApi from '../api/skills'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { SkillOption } from '../types/skill'
import { COACH_PERSONALITY_CHOICES, SEASON_PERIOD_CHOICES } from '../types/user'
import type { CoachPersonality, SeasonPeriod } from '../types/user'
import { maxSkillPreferencesForLevel } from '../utils/skillPreferenceLimit'
import { toIsoDate } from '../utils/date'

export function SettingsTrainingPage() {
  const { user, accessToken, updateUser } = useAuth()
  const maxSkillPreferences = user !== null ? maxSkillPreferencesForLevel(user.level) : null

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

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-8 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink to="/settings" />
          <h1 className="text-xl font-semibold">Тренировочный процесс</h1>
        </div>

        <section className="flex flex-col gap-4">
          <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
            <i className="ti ti-calendar text-accent-ice" aria-hidden="true" />
            Период сезона
            <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
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
            <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
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
            <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
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
            <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
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
      </div>
    </div>
  )
}
