import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import { LockedSkillChip, SkillChip } from '../../components/ui/SkillChip'
import * as skillsApi from '../../api/skills'
import * as usersApi from '../../api/users'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { SkillOption } from '../../types/skill'
import { maxSkillPreferencesForLevel } from '../../utils/skillPreferenceLimit'

export function SkillsStep() {
  const { accessToken, user, markAssessmentComplete } = useAuth()
  const navigate = useNavigate()

  const maxAllowed = user !== null ? maxSkillPreferencesForLevel(user.level) : null

  const [skills, setSkills] = useState<SkillOption[] | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [loadError, setLoadError] = useState<string | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    skillsApi
      .listSkills(accessToken)
      .then((result) => {
        if (!cancelled) {
          setSkills(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить навыки.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  function toggleSkill(id: string) {
    setSelectedIds((previous) => {
      const next = new Set(previous)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  async function handleDone() {
    if (accessToken === null) {
      return
    }
    setSubmitError(null)
    setIsSubmitting(true)
    try {
      await usersApi.replaceSkillPreferences(Array.from(selectedIds), accessToken)
      markAssessmentComplete()
      navigate('/', { replace: true })
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор. Попробуйте ещё раз.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold">Какие навыки хотите развивать?</h2>
      <p className="text-sm text-text-secondary">
        Можно выбрать несколько — это определит приоритет упражнений в тренировках.
      </p>

      {skills === null && loadError === null && <p className="text-sm text-text-secondary">Загрузка...</p>}
      <FormError message={loadError} />

      {/* maxAllowed is null at level 25+ (unlimited) -- omitted entirely
          rather than showing "X из ∞". */}
      {maxAllowed !== null && (
        <p className="text-sm text-text-secondary">
          Выбрано {selectedIds.size} из {maxAllowed}
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
            const isSelected = selectedIds.has(skill.id)
            const limitReached = maxAllowed !== null && selectedIds.size >= maxAllowed
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

      <FormError message={submitError} />
      <Button
        onClick={handleDone}
        disabled={skills === null}
        isLoading={isSubmitting}
        className="self-end"
      >
        Готово
      </Button>
    </div>
  )
}
