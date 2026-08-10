import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { ProgressBar } from '../components/ui/ProgressBar'
import { SkillDetailModal } from '../components/SkillDetailModal'
import { API_BASE_URL, ApiError } from '../api/client'
import * as leaderboardApi from '../api/leaderboard'
import * as progressApi from '../api/progress'
import * as scheduleApi from '../api/schedule'
import * as skillsApi from '../api/skills'
import * as trainingBlockApi from '../api/trainingBlock'
import { useAuth } from '../hooks/useAuth'
import { TARGET_STATS, TARGET_STAT_DESCRIPTIONS, TARGET_STAT_LABELS } from '../types/exercise'
import type { TargetStat } from '../types/exercise'
import type { LeaderboardMeRead } from '../types/leaderboard'
import type { TrainingStreakRead, UserStatRead } from '../types/progress'
import { DAY_SESSION_TYPE_LABELS } from '../types/schedule'
import type { DayPlanRead, WeeklyPlanRead } from '../types/schedule'
import type { SkillDetailRead, SkillSummaryRead } from '../types/skill'
import { BLOCK_PHASE_LABELS } from '../types/trainingBlock'
import type { BlockPhase, TrainingBlockRead } from '../types/trainingBlock'
import { POSITION_LABELS } from '../types/user'
import { getAvatarTierStyle } from '../utils/avatarTier'
import { getDisplayName } from '../utils/displayName'
import { WEEKDAY_LABELS, formatShortDate, parseIsoDate, toIsoDate } from '../utils/date'
import { loadOptional } from '../utils/loadOptional'

const STAT_ABBREVIATIONS: Record<TargetStat, string> = {
  strength: 'СИЛ',
  agility: 'ЛОВ',
  intellect: 'ИНТ',
  endurance: 'ВЫН',
  on_ice_skating: 'ЛЁД',
  puck_handling: 'ШАЙ',
}

const MONTH_LABELS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
]

// DRAFT copy for product review -- no player-facing phase explanation exists
// in the backend/content layer (checked docs, reference-article content,
// TrainingBlock schemas), so this was written here, not sourced. Grounded in
// the real mechanics from app/core/training_block.py (intensification biases
// toward difficulty>=4, deload biases toward difficulty<=2 and shrinks the
// main block to 1-2 exercises) but the wording itself needs a copy pass
// before shipping.
const BLOCK_PHASE_DESCRIPTIONS: Record<BlockPhase, string> = {
  accumulation:
    'Базовый этап блока: набираем общий объём тренировок без резких скачков сложности.',
  intensification:
    'Сложность упражнений заметно растёт — это самая требовательная неделя блока. Следите за техникой.',
  deload:
    'Разгрузочная неделя перед новым блоком: упражнения проще, а нагрузки в основной части меньше. Время на восстановление.',
}

// Rest-day hint on TodayCard: during intensification (the highest-load
// week, see BLOCK_PHASE_DESCRIPTIONS above) light movement speeds recovery
// more than full inactivity, so that phase gets a more specific nudge.
// Accumulation/deload weeks, or no active block at all, get the same
// simple text -- no phase-specific tuning needed there.
function getRestDayHint(phase: BlockPhase | null): string {
  if (phase === 'intensification') {
    return 'День отдыха. Лёгкая прогулка 20-30 минут поможет мышцам быстрее восстановиться после высокой нагрузки этой недели.'
  }
  return 'День отдыха. Дайте телу восстановиться.'
}

// Card surface shared by every dashboard tile below: dark-card fill with a
// thin icy top border, per the HomePage palette (see IceGlowBackground for
// the matching bg tones).
const CARD_CLASS = 'rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-card'

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

function addMonths(date: Date, months: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + months, 1)
}

// Monday-start grid padded with nulls to a full number of weeks.
function buildMonthGrid(monthStart: Date): (Date | null)[] {
  const daysInMonth = new Date(monthStart.getFullYear(), monthStart.getMonth() + 1, 0).getDate()
  const leadingBlanks = (monthStart.getDay() + 6) % 7
  const cells: (Date | null)[] = []
  for (let i = 0; i < leadingBlanks; i++) {
    cells.push(null)
  }
  for (let day = 1; day <= daysInMonth; day++) {
    cells.push(new Date(monthStart.getFullYear(), monthStart.getMonth(), day))
  }
  while (cells.length % 7 !== 0) {
    cells.push(null)
  }
  return cells
}

function isSessionDayCompleted(day: DayPlanRead): boolean {
  const blocks = day.training_session?.blocks
  return blocks !== undefined && blocks.length > 0 && blocks.every((block) => block.completed_at !== null)
}

// TODO: there is no per-day activity history endpoint yet -- only
// TrainingStreak.last_activity_date (a single date) and the *current*
// week's WeeklyPlanRead are available on the frontend. Days inside the
// loaded current week are marked accurately from real block completion;
// every other day can only be checked against last_activity_date. A real
// "/users/me/activity-calendar"-style endpoint is needed before the
// calendar can show a genuine month-long history.
function hasKnownActivity(
  iso: string,
  weeklyPlan: WeeklyPlanRead | null,
  streak: TrainingStreakRead | null,
): boolean {
  const day = weeklyPlan?.day_plans.find((candidate) => candidate.date === iso)
  if (day !== undefined) {
    return isSessionDayCompleted(day)
  }
  return streak?.last_activity_date === iso
}

function topSkillsNearMilestone(skills: SkillSummaryRead[]): SkillSummaryRead[] {
  return skills
    .filter((skill) => skill.next_milestone !== null)
    .sort((a, b) => a.next_milestone!.points_remaining - b.next_milestone!.points_remaining)
    .slice(0, 3)
}

export function HomePage() {
  const { user, accessToken } = useAuth()
  const navigate = useNavigate()

  const [trainingBlock, setTrainingBlock] = useState<TrainingBlockRead | null>(null)
  const [weeklyPlan, setWeeklyPlan] = useState<WeeklyPlanRead | null>(null)
  const [streak, setStreak] = useState<TrainingStreakRead | null>(null)
  const [stats, setStats] = useState<UserStatRead[] | null>(null)
  const [skills, setSkills] = useState<SkillSummaryRead[] | null>(null)
  const [leaderboardMe, setLeaderboardMe] = useState<LeaderboardMeRead | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [calendarExpanded, setCalendarExpanded] = useState(false)
  const [calendarMonth, setCalendarMonth] = useState(() => startOfMonth(new Date()))
  const [selectedDay, setSelectedDay] = useState<Date | null>(null)

  const [selectedStatType, setSelectedStatType] = useState<TargetStat | null>(null)

  const [selectedSkillId, setSelectedSkillId] = useState<string | null>(null)
  const [skillDetails, setSkillDetails] = useState<Record<string, SkillDetailRead>>({})
  const [loadingSkillDetailId, setLoadingSkillDetailId] = useState<string | null>(null)
  const [skillDetailError, setSkillDetailError] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    Promise.all([
      loadOptional(trainingBlockApi.getCurrentTrainingBlock(accessToken)),
      loadOptional(scheduleApi.getCurrentWeeklyPlan(accessToken)),
      progressApi.getMyStreak(accessToken),
      progressApi.getMyStats(accessToken),
      skillsApi.listSkills(accessToken),
      // Rating excess needs an age-based expected baseline -- always present
      // post-onboarding, so this is safe to call directly rather than
      // through loadOptional like the two calls above.
      leaderboardApi.getMyLeaderboardPosition(accessToken),
    ])
      .then(([block, plan, streakResult, statsResult, skillsResult, leaderboardMeResult]) => {
        if (cancelled) {
          return
        }
        setTrainingBlock(block)
        setWeeklyPlan(plan)
        setStreak(streakResult)
        setStats(statsResult)
        setSkills(skillsResult)
        setLeaderboardMe(leaderboardMeResult)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : 'Не удалось загрузить дашборд.')
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
    setSkillDetailError(null)
    setLoadingSkillDetailId(skillId)
    try {
      const detail = await skillsApi.getSkillDetail(skillId, accessToken)
      setSkillDetails((previous) => ({ ...previous, [skillId]: detail }))
    } catch (err) {
      setSkillDetailError(err instanceof ApiError ? err.message : 'Не удалось загрузить детали навыка.')
    } finally {
      setLoadingSkillDetailId(null)
    }
  }

  const todayIso = toIsoDate(new Date())
  const today = weeklyPlan?.day_plans.find((day) => day.date === todayIso) ?? null
  const avatarUrl = user?.avatar_url != null ? `${API_BASE_URL}${user.avatar_url}` : null
  const avatarTierStyle = getAvatarTierStyle(user?.level ?? 1)
  const selectedDayPlan =
    selectedDay !== null ? weeklyPlan?.day_plans.find((day) => day.date === toIsoDate(selectedDay)) : undefined
  const selectedDayHasActivity =
    selectedDay !== null && hasKnownActivity(toIsoDate(selectedDay), weeklyPlan, streak)
  const selectedSkillName = skills?.find((skill) => skill.id === selectedSkillId)?.name ?? ''
  const selectedStat =
    selectedStatType !== null ? (stats?.find((stat) => stat.stat_type === selectedStatType) ?? null) : null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex min-h-svh max-w-3xl flex-col gap-4 px-4 py-8">
        <div className={`flex items-center justify-between gap-4 p-4 ${CARD_CLASS}`}>
          <div className="flex items-center gap-4">
            {/* Two-layer wrapper: the outer div carries the level-tier
                border/glow (box-shadow), the inner one clips the photo to a
                circle. Both on the same element would clip the glow itself
                -- overflow-hidden clips a box's own box-shadow, not just
                its content. */}
            <div className="h-20 w-20 shrink-0 rounded-full" style={avatarTierStyle.style}>
              <div className="flex h-full w-full items-center justify-center overflow-hidden rounded-full bg-dark-bg">
                {avatarUrl !== null ? (
                  <img src={avatarUrl} alt="" className="h-full w-full object-cover" />
                ) : (
                  <i className="ti ti-user text-3xl text-[#8A94A6]" aria-hidden="true" />
                )}
              </div>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xl font-bold leading-tight text-[#F5F7FA]">
                {user !== null ? getDisplayName(user) : ''}
              </span>
              <span className="text-sm text-[#8A94A6]">
                {[user?.position != null ? POSITION_LABELS[user.position] : null, `Уровень ${user?.level}`]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </div>
          </div>

          {streak !== null && (
            <button
              type="button"
              onClick={() => setCalendarExpanded((value) => !value)}
              className="flex shrink-0 items-center gap-1.5 rounded-md border border-white/10 bg-dark-bg px-3 py-2 transition-colors hover:border-white/20"
            >
              <i className="ti ti-flame text-accent-persimmon" aria-hidden="true" />
              <span className="font-mono text-sm text-accent-persimmon">{streak.current_streak}</span>
              <i
                className={`ti ${calendarExpanded ? 'ti-chevron-up' : 'ti-chevron-down'} text-sm text-[#8A94A6]`}
                aria-hidden="true"
              />
            </button>
          )}
        </div>

        {calendarExpanded && (
          <CalendarPanel
            month={calendarMonth}
            onMonthChange={setCalendarMonth}
            weeklyPlan={weeklyPlan}
            streak={streak}
            onSelectDay={setSelectedDay}
          />
        )}

        <FormError message={error} />
        {isLoading && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {!isLoading && (
          <div className="flex flex-col gap-4">
            <TodayCard
              day={today}
              phaseLabel={trainingBlock !== null ? BLOCK_PHASE_LABELS[trainingBlock.phase] : null}
              phase={trainingBlock !== null ? trainingBlock.phase : null}
              onStart={() => today !== null && navigate(`/training/${today.id}`)}
            />

            {stats !== null && <StatsRow stats={stats} onSelect={setSelectedStatType} />}

            {skills !== null && (
              <SkillsNearMilestoneCard skills={skills} onSelectSkill={openSkillModal} />
            )}

            {trainingBlock !== null && <PeriodizationCard block={trainingBlock} />}

            {leaderboardMe !== null && (
              <RatingRow me={leaderboardMe} onClick={() => navigate('/leaderboard')} />
            )}
          </div>
        )}
      </div>

      {selectedDay !== null && (
        <DayDetailModal
          date={selectedDay}
          dayPlan={selectedDayPlan}
          hasKnownActivity={selectedDayHasActivity}
          onClose={() => setSelectedDay(null)}
        />
      )}

      {selectedStatType !== null && selectedStat !== null && (
        <StatDetailModal statType={selectedStatType} stat={selectedStat} onClose={() => setSelectedStatType(null)} />
      )}

      {selectedSkillId !== null && (
        <SkillDetailModal
          skillName={selectedSkillName}
          detail={skillDetails[selectedSkillId]}
          isLoading={loadingSkillDetailId === selectedSkillId}
          error={skillDetailError}
          onClose={() => setSelectedSkillId(null)}
        />
      )}
    </div>
  )
}

function TodayCard({
  day,
  phaseLabel,
  phase,
  onStart,
}: {
  day: DayPlanRead | null
  phaseLabel: string | null
  phase: BlockPhase | null
  onStart: () => void
}) {
  const weekday = day !== null ? WEEKDAY_LABELS[(parseIsoDate(day.date).getDay() + 6) % 7] : null
  const eyebrow = [weekday, phaseLabel].filter(Boolean).join(' · ')

  if (day === null || day.training_session === null) {
    // Rest days never get a TrainingSession (see schedule_service.py), so
    // day.training_session === null already covers session_type === 'rest'
    // -- checking session_type here too would just be redundant with it.
    const isRestDay = day !== null && day.session_type === 'rest'
    return (
      <div className={`p-5 ${CARD_CLASS}`}>
        {eyebrow !== '' && <p className="mb-1 text-xs uppercase tracking-wide text-[#8A94A6]">{eyebrow}</p>}
        <p className="text-lg font-semibold text-[#F5F7FA]">
          {isRestDay ? getRestDayHint(phase) : 'Нет плана на сегодня'}
        </p>
      </div>
    )
  }

  const completed = isSessionDayCompleted(day)

  return (
    <div className={`flex flex-col gap-4 p-5 ${CARD_CLASS}`}>
      <div className="flex items-center justify-between gap-3">
        {eyebrow !== '' && <p className="text-xs uppercase tracking-wide text-[#8A94A6]">{eyebrow}</p>}
        {completed && (
          <span className="flex items-center gap-1 text-xs text-[#8A94A6]">
            <i className="ti ti-check" aria-hidden="true" />
            Выполнено
          </span>
        )}
      </div>
      <p className="text-2xl font-bold text-[#F5F7FA]">{DAY_SESSION_TYPE_LABELS[day.session_type]}</p>
      {!completed && (
        <Button onClick={onStart} className="w-full">
          Начать тренировку
        </Button>
      )}
    </div>
  )
}

function StatsRow({ stats, onSelect }: { stats: UserStatRead[]; onSelect: (statType: TargetStat) => void }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {TARGET_STATS.map((statType) => {
        const stat = stats.find((candidate) => candidate.stat_type === statType)
        if (stat === undefined) {
          return null
        }
        return (
          <button
            key={statType}
            type="button"
            onClick={() => onSelect(statType)}
            className={`flex flex-col items-center gap-1 px-2 py-3 transition-colors hover:border-white/20 ${CARD_CLASS}`}
          >
            <span className="text-[11px] text-[#8A94A6]">{STAT_ABBREVIATIONS[statType]}</span>
            <span className="font-mono text-xl font-bold text-accent-ice">{Math.round(stat.current_value)}</span>
            <i
              className={`ti text-sm ${
                stat.trend === 'up' ? 'ti-trending-up text-accent-ice' : 'ti-trending-down text-[#8A94A6]'
              }`}
              aria-hidden="true"
            />
          </button>
        )
      })}
    </div>
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
        <p className="text-sm text-[#8A94A6]">{TARGET_STAT_DESCRIPTIONS[statType]}</p>
        <p className="font-mono text-3xl font-bold leading-none text-[#F5F7FA]">
          {Math.round(stat.current_value)}
        </p>
      </div>
    </Modal>
  )
}

// ProgressBar.tsx is frozen for this pass, and this list wants noticeably
// taller bars (esp. on md/lg) than its fixed h-2 -- a small local variant
// instead of touching the shared component.
function SkillProgressBar({ value, max, accent }: { value: number; max: number; accent: 'ice' | 'persimmon' }) {
  const percent = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 100
  const fill = accent === 'persimmon' ? 'bg-accent-persimmon' : 'bg-accent-ice'
  return (
    <div className="h-2.5 w-full overflow-hidden rounded-full bg-white/10 md:h-3.5 lg:h-4">
      <div className={`h-full rounded-full ${fill}`} style={{ width: `${percent}%` }} />
    </div>
  )
}

function SkillsNearMilestoneCard({
  skills,
  onSelectSkill,
}: {
  skills: SkillSummaryRead[]
  onSelectSkill: (skillId: string) => void
}) {
  const top = topSkillsNearMilestone(skills)
  if (top.length === 0) {
    return null
  }

  return (
    <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <h2 className="text-sm font-medium text-[#8A94A6]">Ближайшие пороги</h2>
      <div className="flex flex-col gap-5">
        {top.map((skill) => {
          const milestone = skill.next_milestone!
          const nearThreshold = milestone.points_remaining < 5
          return (
            <button
              key={skill.id}
              type="button"
              onClick={() => onSelectSkill(skill.id)}
              className="flex flex-col gap-2 text-left"
            >
              <div className="flex items-center justify-between text-sm">
                <span className="text-[#F5F7FA]">{skill.name}</span>
                {nearThreshold ? (
                  <span className="text-xs font-medium text-accent-persimmon">почти порог</span>
                ) : (
                  <span className="text-xs text-[#8A94A6]">
                    {Math.round(milestone.points_remaining)} до «{milestone.title}»
                  </span>
                )}
              </div>
              <SkillProgressBar value={skill.value} max={milestone.threshold} accent={nearThreshold ? 'persimmon' : 'ice'} />
            </button>
          )
        })}
      </div>
    </div>
  )
}

function PeriodizationCard({ block }: { block: TrainingBlockRead }) {
  const [infoOpen, setInfoOpen] = useState(false)
  const description = BLOCK_PHASE_DESCRIPTIONS[block.phase]

  return (
    <div className={`flex flex-col gap-2 p-4 ${CARD_CLASS}`}>
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-1.5 text-[#8A94A6]">
          Блок {block.block_number} · {BLOCK_PHASE_LABELS[block.phase]}
          <button
            type="button"
            onClick={() => setInfoOpen((value) => !value)}
            aria-label="Что означает эта фаза"
            aria-expanded={infoOpen}
            title={description}
            className="text-[#8A94A6] transition-colors hover:text-accent-ice"
          >
            <i className="ti ti-info-circle text-sm" aria-hidden="true" />
          </button>
        </span>
        <span className="font-mono text-accent-ice">{block.week_in_block}/4</span>
      </div>
      {infoOpen && <p className="text-xs text-[#8A94A6]">{description}</p>}
      <ProgressBar value={block.week_in_block} max={4} />
    </div>
  )
}

function RatingRow({ me, onClick }: { me: LeaderboardMeRead; onClick: () => void }) {
  const sign = me.rating_excess > 0 ? '+' : ''
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex w-full items-center justify-between gap-4 p-5 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
    >
      <div className="flex flex-col gap-0.5">
        <span className="text-sm font-medium text-[#F5F7FA]">Рейтинг</span>
        {/* Same explanation LeaderboardPage gives for rating_excess, trimmed to fit a one-line subtitle. */}
        <span className="text-xs text-[#8A94A6]">Относительно вашего возраста и стажа</span>
      </div>
      <span className="font-mono text-lg text-[#F5F7FA]">
        #{me.rank} <span className="text-accent-ice">{sign}{me.rating_excess.toFixed(1)}</span>
      </span>
    </button>
  )
}

function CalendarPanel({
  month,
  onMonthChange,
  weeklyPlan,
  streak,
  onSelectDay,
}: {
  month: Date
  onMonthChange: (month: Date) => void
  weeklyPlan: WeeklyPlanRead | null
  streak: TrainingStreakRead | null
  onSelectDay: (date: Date) => void
}) {
  const cells = buildMonthGrid(month)
  const todayIso = toIsoDate(new Date())

  return (
    <div className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={() => onMonthChange(addMonths(month, -1))}
          aria-label="Предыдущий месяц"
          className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
        >
          <i className="ti ti-chevron-left" aria-hidden="true" />
        </button>
        <span className="text-sm font-medium text-[#F5F7FA]">
          {MONTH_LABELS[month.getMonth()]} {month.getFullYear()}
        </span>
        <button
          type="button"
          onClick={() => onMonthChange(addMonths(month, 1))}
          aria-label="Следующий месяц"
          className="text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
        >
          <i className="ti ti-chevron-right" aria-hidden="true" />
        </button>
      </div>

      <div className="grid grid-cols-7 gap-1 text-center text-xs text-[#8A94A6]">
        {WEEKDAY_LABELS.map((label) => (
          <span key={label}>{label}</span>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-1">
        {cells.map((date, index) => {
          if (date === null) {
            return <div key={index} />
          }
          const iso = toIsoDate(date)
          const active = hasKnownActivity(iso, weeklyPlan, streak)
          const isToday = iso === todayIso
          return (
            <button
              key={iso}
              type="button"
              onClick={() => onSelectDay(date)}
              className={`aspect-square rounded font-mono text-xs transition-colors ${
                active
                  ? 'bg-accent-persimmon text-dark-bg'
                  : `text-[#8A94A6] hover:bg-white/5 ${isToday ? 'border border-accent-ice' : ''}`
              }`}
            >
              {date.getDate()}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function DayDetailModal({
  date,
  dayPlan,
  hasKnownActivity: dayHasActivity,
  onClose,
}: {
  date: Date
  dayPlan: DayPlanRead | undefined
  hasKnownActivity: boolean
  onClose: () => void
}) {
  return (
    <Modal title={formatShortDate(date)} onClose={onClose}>
      {dayPlan === undefined && (
        <p className="text-sm text-[#8A94A6]">
          {dayHasActivity
            ? // Known from TrainingStreak.last_activity_date only -- no
              // per-block breakdown available outside the current week, see
              // the hasKnownActivity TODO above.
              'В этот день была тренировка, но детали пока недоступны.'
            : 'Тренировки не было.'}
        </p>
      )}

      {dayPlan !== undefined && dayPlan.session_type === 'rest' && (
        <p className="text-sm text-[#8A94A6]">День отдыха.</p>
      )}

      {dayPlan !== undefined && dayPlan.session_type !== 'rest' && dayPlan.training_session === null && (
        <p className="text-sm text-[#8A94A6]">Тренировки не было.</p>
      )}

      {dayPlan !== undefined && dayPlan.training_session !== null && (
        <div className="flex flex-col gap-2">
          <p className="text-xs uppercase tracking-wide text-[#8A94A6]">
            {DAY_SESSION_TYPE_LABELS[dayPlan.session_type]}
          </p>
          {dayPlan.training_session.blocks.map((block) => (
            <div key={block.id} className="flex items-center justify-between text-sm">
              <span className={block.completed_at !== null ? 'text-[#F5F7FA]' : 'text-[#8A94A6]'}>
                {block.exercise.name}
              </span>
              <i
                className={`ti ${block.completed_at !== null ? 'ti-check text-accent-ice' : 'ti-minus text-[#8A94A6]'}`}
                aria-hidden="true"
              />
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
