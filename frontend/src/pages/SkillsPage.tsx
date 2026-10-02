import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { FaceoffProgressRing } from '../components/ui/FaceoffProgressRing'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { LockedSkillChip } from '../components/ui/SkillChip'
import { SkillDetailModal } from '../components/SkillDetailModal'
import * as skillsApi from '../api/skills'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { SkillDetailRead, SkillSummaryRead } from '../types/skill'

// A skill's value is a weighted sum of its underlying stats' effective
// values (weights sum to <=1.0, validated server-side), each individually
// hard-capped at 100 (app/events/handlers/block_completed.py's
// STAT_HARD_CAP) -- so 100 is the real ceiling every skill's value is
// bounded by, not a guess.
const SKILL_VALUE_CAP = 100

// Skills with a still-open next milestone sort first, closest (smallest
// points_remaining) at the very top -- "almost there" is the motivating
// view. Fully-maxed skills (next_milestone === null) sink to the bottom.
function sortByClosestMilestone(skills: SkillSummaryRead[]): SkillSummaryRead[] {
  return [...skills].sort((a, b) => {
    const aRemaining = a.next_milestone?.points_remaining ?? Infinity
    const bRemaining = b.next_milestone?.points_remaining ?? Infinity
    return aRemaining - bRemaining
  })
}

// Every skill with its progress to the next threshold, priorities first in
// colour -- used to be the "Навыки" tab of a modal on the profile.
export function SkillsPage() {
  const { user, accessToken } = useAuth()
  const [skills, setSkills] = useState<SkillSummaryRead[] | null>(null)
  const [preferredSkillIds, setPreferredSkillIds] = useState<Set<string>>(new Set())
  const [loadError, setLoadError] = useState<string | null>(null)

  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [skillDetails, setSkillDetails] = useState<Record<string, SkillDetailRead>>({})
  const [loadingDetailId, setLoadingDetailId] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([skillsApi.listSkills(accessToken), usersApi.getSkillPreferences(accessToken)])
      .then(([skillsResult, preferences]) => {
        if (!cancelled) {
          setSkills(skillsResult)
          setPreferredSkillIds(new Set(preferences.map((preference) => preference.skill_id)))
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

  async function openSkill(skillId: string) {
    setSelectedSkillId(skillId)
    if (skillDetails[skillId] !== undefined || accessToken === null) {
      return
    }
    setDetailError(null)
    setLoadingDetailId(skillId)
    try {
      const detail = await skillsApi.getSkillDetail(skillId, accessToken)
      setSkillDetails((previous) => ({ ...previous, [skillId]: detail }))
    } catch (err) {
      setDetailError(err instanceof ApiError ? err.message : 'Не удалось загрузить детали навыка.')
    } finally {
      setLoadingDetailId(null)
    }
  }

  const level = user?.level ?? 1
  const unlocked = skills !== null ? sortByClosestMilestone(skills.filter((skill) => skill.required_level <= level)) : []
  const locked =
    skills !== null
      ? skills.filter((skill) => skill.required_level > level).sort((a, b) => a.required_level - b.required_level)
      : []
  const selectedSkill = skills?.find((skill) => skill.id === selectedSkillId)

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-4 px-4 py-6">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Навыки</h1>
          <p className="text-sm text-[#8A94A6]">
            Приоритетные навыки — те, что вы выбрали в настройках, — чаще получают подходящие упражнения. Остальные
            тоже растут, от общей подготовки, просто медленнее.
          </p>
        </div>

        <FormError message={loadError} />
        {skills === null && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        <div className="flex flex-col gap-2">
          {unlocked.map((skill) => {
            // Past the last seeded milestone next_milestone is null -- the
            // cap keeps the percent honest instead of pinning it at 100%.
            const barMax = skill.next_milestone?.threshold ?? SKILL_VALUE_CAP
            const isPreferred = preferredSkillIds.has(skill.id)
            const percent = barMax > 0 ? Math.max(0, Math.min(100, (skill.value / barMax) * 100)) : 100
            return (
              <button
                key={skill.id}
                type="button"
                onClick={() => void openSkill(skill.id)}
                className={`flex w-full items-center gap-3 rounded-md border p-3 text-left transition-colors ${
                  isPreferred
                    ? 'border-accent-persimmon/40 bg-accent-persimmon/5 hover:border-accent-persimmon/60'
                    : 'border-white/10 bg-dark-card hover:border-white/20'
                }`}
              >
                <FaceoffProgressRing
                  value={skill.value}
                  max={barMax}
                  accent={isPreferred ? 'persimmon' : 'ice'}
                  size={44}
                  centerValue={`${Math.round(percent)}%`}
                />
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="flex min-w-0 items-center gap-1.5">
                    {isPreferred && <i className="ti ti-star shrink-0 text-xs text-accent-persimmon" aria-hidden="true" />}
                    <span className="truncate text-sm font-medium text-[#F5F7FA]">{skill.name}</span>
                  </span>
                  {skill.next_milestone !== null &&
                    (skill.next_milestone.points_remaining < 1 ? (
                      <span className="truncate text-xs text-accent-persimmon">
                        почти порог «{skill.next_milestone.title}»
                      </span>
                    ) : (
                      <span className="truncate text-xs text-[#8A94A6]">
                        {Math.round(skill.next_milestone.points_remaining)} до «{skill.next_milestone.title}»
                      </span>
                    ))}
                </span>
                {isPreferred && <span className="shrink-0 text-xs font-medium text-accent-persimmon">Приоритет</span>}
              </button>
            )
          })}
          {locked.map((skill) => (
            <LockedSkillChip key={skill.id} label={skill.name} requiredLevel={skill.required_level} />
          ))}
        </div>
      </div>

      {selectedSkillId !== null && (
        <SkillDetailModal
          skillName={selectedSkill?.name ?? ''}
          detail={skillDetails[selectedSkillId]}
          isLoading={loadingDetailId === selectedSkillId}
          error={detailError}
          onClose={() => setSelectedSkillId(null)}
        />
      )}
    </div>
  )
}
