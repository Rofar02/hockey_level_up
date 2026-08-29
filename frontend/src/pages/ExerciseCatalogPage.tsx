import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { TabButton } from '../components/ui/TabButton'
import { ExerciseTechnique } from '../components/ExerciseTechnique'
import * as exercisesApi from '../api/exercises'
import * as progressApi from '../api/progress'
import * as skillsApi from '../api/skills'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { EXERCISE_CATEGORY_LABELS, TARGET_STAT_LABELS } from '../types/exercise'
import type { ExerciseCategory, ExerciseRead } from '../types/exercise'
import type { UserStatRead } from '../types/progress'
import type { SkillSummaryRead, SkillTagRead } from '../types/skill'
import { getExerciseLockState } from '../utils/exerciseDifficultyGate'
import { hasExerciseDescription } from '../utils/exerciseTechnique'

type CategoryFilter = ExerciseCategory | 'all'

// Read-only exercise browser (item 5 of the 2026-08-28 roadmap) -- viewing
// only, deliberately: which exercises land in a session is always the
// deterministic core's call, never something the player picks by hand here.
// Grouped by skill (an exercise tagged for more than one shows up under
// each), and only exercises with real technique text -- an untagged or
// stub catalog entry (no description) has nothing useful to show and would
// just read as broken.
export function ExerciseCatalogPage() {
  const { accessToken, user } = useAuth()

  const [exercises, setExercises] = useState<ExerciseRead[] | null>(null)
  const [skills, setSkills] = useState<SkillSummaryRead[] | null>(null)
  const [tags, setTags] = useState<SkillTagRead[] | null>(null)
  const [stats, setStats] = useState<UserStatRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>('all')
  const [selectedExercise, setSelectedExercise] = useState<ExerciseRead | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([
      exercisesApi.listExercises({}, accessToken),
      skillsApi.listSkills(accessToken),
      exercisesApi.listAllExerciseSkillTags(accessToken),
      progressApi.getMyStats(accessToken),
    ])
      .then(([exercisesResult, skillsResult, tagsResult, statsResult]) => {
        if (cancelled) {
          return
        }
        setExercises(exercisesResult)
        setSkills(skillsResult)
        setTags(tagsResult)
        setStats(statsResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить каталог.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  const isLoading = exercises === null || skills === null || tags === null || stats === null

  const exercisesById = new Map((exercises ?? []).map((exercise) => [exercise.id, exercise]))
  const visibleExerciseIds = new Set(
    (exercises ?? [])
      .filter((exercise) => hasExerciseDescription(exercise))
      .filter((exercise) => categoryFilter === 'all' || exercise.category === categoryFilter)
      .map((exercise) => exercise.id),
  )

  // Skill catalog order (listSkills' own order), each with only the
  // visible exercises tagged for it -- skills with none are dropped rather
  // than shown as an empty section.
  const groups = (skills ?? [])
    .map((skill) => {
      const groupExercises = (tags ?? [])
        .filter((tag) => tag.skill_id === skill.id && visibleExerciseIds.has(tag.exercise_id))
        .map((tag) => exercisesById.get(tag.exercise_id))
        .filter((exercise): exercise is ExerciseRead => exercise !== undefined)
      return { skill, exercises: groupExercises }
    })
    .filter((group) => group.exercises.length > 0)

  // All skills a given exercise trains, not just the one it's listed under
  // in this render -- an exercise tagged for two skills should say so on
  // its card regardless of which group's list it's currently sitting in.
  function skillNamesFor(exerciseId: string): string[] {
    return (tags ?? [])
      .filter((tag) => tag.exercise_id === exerciseId)
      .map((tag) => skills?.find((skill) => skill.id === tag.skill_id)?.name)
      .filter((name): name is string => name !== undefined)
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Каталог упражнений</h1>
          <p className="text-sm text-[#8A94A6]">
            Только для просмотра — какие упражнения попадут в тренировку, решает ядро приложения.
          </p>
        </div>

        <div className="flex border-b border-white/10">
          <TabButton active={categoryFilter === 'all'} onClick={() => setCategoryFilter('all')}>
            Все
          </TabButton>
          <TabButton active={categoryFilter === 'on_ice'} onClick={() => setCategoryFilter('on_ice')}>
            {EXERCISE_CATEGORY_LABELS.on_ice}
          </TabButton>
          <TabButton active={categoryFilter === 'off_ice'} onClick={() => setCategoryFilter('off_ice')}>
            {EXERCISE_CATEGORY_LABELS.off_ice}
          </TabButton>
        </div>

        <FormError message={loadError} />
        {isLoading && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {!isLoading && groups.length === 0 && (
          <EmptyState
            icon="ti-book-2"
            title="Нет упражнений с описанием техники"
            hint="Попробуйте другой фильтр."
          />
        )}

        {!isLoading && groups.length > 0 && (
          <div className="flex flex-col gap-5">
            {groups.map(({ skill, exercises: groupExercises }) => (
              <div key={skill.id} className="flex flex-col gap-2">
                <div className="flex items-center gap-2 px-1">
                  <span className="h-px w-4 shrink-0 bg-accent-ice/60" aria-hidden="true" />
                  <span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">
                    {skill.name}
                  </span>
                  <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
                </div>
                <div className="flex flex-col gap-2">
                  {groupExercises.map((exercise) => {
                    const lockState = getExerciseLockState(
                      exercise,
                      user?.level ?? 1,
                      stats ?? [],
                      TARGET_STAT_LABELS,
                    )
                    return (
                      <button
                        key={exercise.id}
                        type="button"
                        onClick={() => setSelectedExercise(exercise)}
                        className={`flex flex-col items-start gap-1.5 p-4 text-left transition-colors hover:border-white/20 ${CARD_CLASS} ${
                          lockState.locked ? 'opacity-60' : ''
                        }`}
                      >
                        <span className="flex items-center gap-1.5 text-sm font-medium text-[#F5F7FA]">
                          {lockState.locked && <i className="ti ti-lock text-xs text-[#8A94A6]" aria-hidden="true" />}
                          {exercise.name}
                        </span>
                        <div className="flex flex-wrap gap-1">
                          {skillNamesFor(exercise.id).map((name) => (
                            <span
                              key={name}
                              className="rounded bg-accent-ice/10 px-1.5 py-0.5 text-[10px] font-medium text-accent-ice"
                            >
                              {name}
                            </span>
                          ))}
                        </div>
                        {/* Locked -- the real path to unlocking it (same
                            "Доступно с уровня N" wording LockedSkillChip
                            already uses elsewhere) takes the technique
                            blurb's place, not a spot alongside it -- it's
                            the more actionable thing to tell the player
                            right now. */}
                        {lockState.locked ? (
                          <p className="text-xs text-[#8A94A6]">
                            {lockState.reason === 'level' && `Доступно с уровня ${lockState.requiredLevel}`}
                            {lockState.reason === 'stat' &&
                              `Нужна ${lockState.statLabel} от ${lockState.requiredValue}`}
                            {lockState.reason === 'unclassified' && 'Пока недоступно'}
                          </p>
                        ) : (
                          exercise.description !== null && (
                            <p className="line-clamp-2 text-xs text-[#8A94A6]">{exercise.description}</p>
                          )
                        )}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {selectedExercise !== null && (
        <Modal title={selectedExercise.name} onClose={() => setSelectedExercise(null)}>
          <ExerciseTechnique exercise={selectedExercise} />
        </Modal>
      )}
    </div>
  )
}
