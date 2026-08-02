import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import { Modal } from '../components/ui/Modal'
import { ProgressBar } from '../components/ui/ProgressBar'
import * as progressApi from '../api/progress'
import * as skillsApi from '../api/skills'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { TARGET_STATS, TARGET_STAT_LABELS } from '../types/exercise'
import type { TargetStat } from '../types/exercise'
import type { UserStatRead } from '../types/progress'
import type { SkillDetailRead, SkillSummaryRead } from '../types/skill'
import { POSITION_LABELS } from '../types/user'

const STAT_SCALE_MAX = 100

// Static, curated copy -- not content that grows or changes per-user, so no
// need to route it through the backend.
const STAT_DESCRIPTIONS: Record<TargetStat, string> = {
  strength:
    'Базовая мышечная мощность корпуса и ног. Даёт основу для взрывных движений — старт, бросок — и устойчивость в силовых единоборствах.',
  agility:
    'Скорость реакции, координация и контроль тела в движении. Определяет качество катания, смены направления и работы с шайбой.',
  intellect:
    'Понимание игры: чтение ситуаций, принятие решений, позиционирование. Растёт медленнее физических характеристик и во многом опирается на игровой опыт.',
  endurance:
    'Способность поддерживать интенсивность на протяжении всей игры без потери скорости и силы действий.',
}

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

export function ProfilePage() {
  const { user, accessToken } = useAuth()

  const [stats, setStats] = useState<UserStatRead[] | null>(null)
  const [skills, setSkills] = useState<SkillSummaryRead[] | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [skillsExpanded, setSkillsExpanded] = useState(false)

  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [skillDetails, setSkillDetails] = useState<Record<string, SkillDetailRead>>({})
  const [loadingDetailId, setLoadingDetailId] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const [selectedStatType, setSelectedStatType] = useState<TargetStat | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([progressApi.getMyStats(accessToken), skillsApi.listSkills(accessToken)])
      .then(([statsResult, skillsResult]) => {
        if (cancelled) {
          return
        }
        setStats(statsResult)
        setSkills(skillsResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить профиль.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function openSkillModal(skillId: string) {
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

  const statsByType = new Map(stats?.map((stat) => [stat.stat_type, stat]))
  const overallRating =
    stats !== null && stats.length > 0
      ? Math.round(stats.reduce((sum, stat) => sum + stat.effective_value, 0) / stats.length)
      : null
  const sortedSkills = skills !== null ? sortByClosestMilestone(skills) : null
  const selectedSkill = sortedSkills?.find((skill) => skill.id === selectedSkillId)
  const selectedStat = selectedStatType !== null ? statsByType.get(selectedStatType) : undefined

  return (
    <div className="mx-auto flex min-h-svh max-w-2xl flex-col gap-6 px-4 py-8">
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <BackLink />
          <Link
            to="/settings"
            aria-label="Настройки"
            className="text-text-secondary transition-colors hover:text-text-primary"
          >
            <i className="ti ti-settings text-xl" aria-hidden="true" />
          </Link>
        </div>
        <h1 className="text-xl font-semibold">Профиль</h1>
      </div>

      <FormError message={loadError} />
      {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoading && stats !== null && (
        <div className="overflow-hidden rounded-md border border-white/5 bg-dark-card">
          <div className="h-1 bg-accent-ice" />
          <div className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-mono text-3xl font-bold leading-none text-text-primary">
                  {overallRating ?? '—'}
                </p>
                <p className="mt-1 text-xs tracking-wide text-text-secondary">ОБЩИЙ РЕЙТИНГ</p>
              </div>
              <div className="text-right">
                <p className="font-medium text-text-primary">{user?.username}</p>
                {user?.position != null && (
                  <span className="mt-1 inline-block rounded border border-white/15 px-2 py-0.5 text-xs text-text-secondary">
                    {POSITION_LABELS[user.position]}
                  </span>
                )}
              </div>
            </div>

            <div className="mt-4 flex flex-col gap-2">
              {TARGET_STATS.map((statType) => {
                const stat = statsByType.get(statType)
                if (stat === undefined) {
                  return null
                }
                return (
                  <button
                    key={statType}
                    type="button"
                    onClick={() => setSelectedStatType(statType)}
                    className="flex w-full flex-col rounded text-left transition-colors hover:bg-white/5"
                  >
                    <div className="flex items-center gap-3">
                      <span className="w-24 shrink-0 text-sm text-text-secondary">
                        {TARGET_STAT_LABELS[statType]}
                      </span>
                      <ProgressBar value={stat.effective_value} max={STAT_SCALE_MAX} />
                      <span className="w-8 shrink-0 text-right font-mono text-sm text-text-primary">
                        {Math.round(stat.effective_value)}
                      </span>
                    </div>
                    {stat.decay_active && (
                      <p className="mt-1 flex items-center gap-1 pl-[108px] text-xs text-text-secondary">
                        <i className="ti ti-trending-down" aria-hidden="true" />
                        затухает, {Math.round(stat.idle_days)} дней без нагрузки
                      </p>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {!isLoading && sortedSkills !== null && (
        <div className="overflow-hidden rounded-md border border-white/5 bg-dark-card">
          <button
            type="button"
            onClick={() => setSkillsExpanded((value) => !value)}
            className="flex w-full items-center justify-between p-4 text-left"
          >
            <span className="font-medium text-text-primary">Навыки</span>
            <i
              className={`ti ${skillsExpanded ? 'ti-chevron-down' : 'ti-chevron-right'} text-text-secondary`}
              aria-hidden="true"
            />
          </button>

          {skillsExpanded && (
            <div className="flex flex-col gap-3 border-t border-white/5 p-4">
              {sortedSkills.map((skill) => {
                const barMax = skill.next_milestone?.threshold ?? skill.value
                return (
                  <button
                    key={skill.id}
                    type="button"
                    onClick={() => openSkillModal(skill.id)}
                    className="flex w-full flex-col gap-2 rounded-md border border-white/5 bg-dark-bg p-5 text-left transition-colors hover:border-white/20"
                  >
                    <p className="font-medium text-text-primary">{skill.name}</p>
                    <ProgressBar value={skill.value} max={barMax} />
                    <p className="text-xs text-text-secondary">
                      {skill.next_milestone !== null
                        ? `${Math.round(skill.next_milestone.points_remaining)} до «${skill.next_milestone.title}»`
                        : 'Все пороги пройдены'}
                    </p>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {selectedSkillId !== null && (
        <SkillDetailModal
          skillName={selectedSkill?.name ?? ''}
          detail={skillDetails[selectedSkillId]}
          isLoading={loadingDetailId === selectedSkillId}
          error={detailError}
          onClose={() => setSelectedSkillId(null)}
        />
      )}

      {selectedStatType !== null && selectedStat !== undefined && (
        <StatDetailModal
          statType={selectedStatType}
          stat={selectedStat}
          onClose={() => setSelectedStatType(null)}
        />
      )}
    </div>
  )
}

function SkillDetailModal({
  skillName,
  detail,
  isLoading,
  error,
  onClose,
}: {
  skillName: string
  detail: SkillDetailRead | undefined
  isLoading: boolean
  error: string | null
  onClose: () => void
}) {
  return (
    <Modal title={skillName} onClose={onClose}>
      {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}
      <FormError message={error} />

      {detail !== undefined && (
        <div className="flex flex-col gap-4">
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
              Вклад характеристик
            </p>
            <div className="flex flex-col gap-1.5">
              {detail.stat_breakdown.map((item) => (
                <div key={item.stat_type} className="flex items-center justify-between text-sm">
                  <span>{TARGET_STAT_LABELS[item.stat_type]}</span>
                  <span className="font-mono text-text-secondary">+{item.contribution.toFixed(1)}</span>
                </div>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
              Пороги
            </p>
            <div className="flex flex-col gap-2.5">
              {detail.milestones.map((milestone) => (
                <div key={milestone.id} className="flex items-start gap-2">
                  <i
                    className={`ti mt-0.5 ${
                      milestone.achieved ? 'ti-lock-open text-accent-ice' : 'ti-lock text-text-secondary'
                    }`}
                    aria-hidden="true"
                  />
                  <div>
                    <p
                      className={`text-sm ${
                        milestone.achieved ? 'text-text-primary' : 'text-text-secondary'
                      }`}
                    >
                      {milestone.threshold} — {milestone.title}
                    </p>
                    <p className="text-xs text-text-secondary">{milestone.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}

function StatDetailModal({
  statType,
  stat,
  onClose,
}: {
  statType: TargetStat
  stat: UserStatRead
  onClose: () => void
}) {
  return (
    <Modal title={TARGET_STAT_LABELS[statType]} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <p className="text-sm text-text-secondary">{STAT_DESCRIPTIONS[statType]}</p>
        <div>
          <p className="font-mono text-3xl font-bold leading-none text-text-primary">
            {Math.round(stat.effective_value)}
          </p>
          {stat.decay_active && (
            <p className="mt-2 flex items-center gap-1 text-xs text-text-secondary">
              <i className="ti ti-trending-down" aria-hidden="true" />
              затухает, {Math.round(stat.idle_days)} дней без нагрузки
            </p>
          )}
        </div>
      </div>
    </Modal>
  )
}
