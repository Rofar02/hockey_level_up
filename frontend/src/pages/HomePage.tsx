import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { OnboardingTour } from '../components/OnboardingTour'
import { SkillDetailModal } from '../components/SkillDetailModal'
import { Button } from '../components/ui/Button'
import { CardGlow } from '../components/ui/CardGlow'
import { CARD_BORDER, CARD_CLASS } from '../components/ui/cardStyle'
import { FaceoffProgressRing } from '../components/ui/FaceoffProgressRing'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { ProgressBar } from '../components/ui/ProgressBar'
import { RankBadge } from '../components/ui/RankBadge'
import { StatIcon } from '../components/ui/StatIcon'
import { XpBar } from '../components/ui/XpBar'
import { API_BASE_URL, ApiError } from '../api/client'
import * as leaderboardApi from '../api/leaderboard'
import * as progressApi from '../api/progress'
import * as scheduleApi from '../api/schedule'
import * as skillsApi from '../api/skills'
import * as trainingBlockApi from '../api/trainingBlock'
import * as usersApi from '../api/users'
import { useAuth } from '../hooks/useAuth'
import { useCoachmarkStep } from '../hooks/useCoachmarkStep'
import { useSuppressCoachmarks } from '../hooks/useSuppressCoachmarks'
import { TARGET_STATS, TARGET_STAT_DESCRIPTIONS, TARGET_STAT_LABELS } from '../types/exercise'
import type { ExerciseRead, TargetStat } from '../types/exercise'
import type { LeaderboardMeRead } from '../types/leaderboard'
import type { ActivityCalendarDayRead, TrainingStreakRead, UserStatRead } from '../types/progress'
import { DAY_SESSION_TYPE_LABELS, SESSION_TYPE_COLORS, SESSION_TYPE_ICONS } from '../types/schedule'
import type {
  DayPlanRead,
  DaySessionType,
  SessionBlockRead,
  TrainingPhase,
  TrainingSessionRead,
  WeeklyPlanRead,
} from '../types/schedule'
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
// before shipping. Phrased around "фаза" rather than "неделя" since Phase 4
// made phase length session-count-driven, not a fixed calendar week.
const BLOCK_PHASE_DESCRIPTIONS: Record<BlockPhase, string> = {
  accumulation:
    'Базовый этап блока: набираем общий объём тренировок без резких скачков сложности.',
  intensification:
    'Сложность упражнений заметно растёт — это самая требовательная фаза блока. Следите за техникой.',
  deload:
    'Разгрузочная фаза перед новым блоком: упражнения проще, а нагрузки в основной части меньше. Время на восстановление.',
}

// Rest-day hint on TodayCard: during intensification (the highest-load
// phase, see BLOCK_PHASE_DESCRIPTIONS above) light movement speeds recovery
// more than full inactivity, so that phase gets a more specific nudge.
// Accumulation/deload phases, or no active block at all, get the same
// simple text -- no phase-specific tuning needed there.
function getRestDayHint(phase: BlockPhase | null): string {
  if (phase === 'intensification') {
    return 'День отдыха. Лёгкая прогулка 20-30 минут поможет мышцам быстрее восстановиться после высокой нагрузки в этой фазе.'
  }
  return 'День отдыха. Дайте телу восстановиться.'
}

// Read CARD_CLASS as the rink's blue line -- neutral/progress content
// defaults to it. (Tried a bolder border-t-2/0.5 as a 2026-08-28
// experiment -- reverted, the thin line was the right call.)
// Same card, red top line instead -- the rink's other line, reserved for
// content that's a status/urgency call rather than routine progress (hockey
// design pass, 2026-08-28). Only TournamentTaperBanner uses this today.
const CARD_CLASS_URGENT = 'rounded-md border-t border-accent-persimmon/50 bg-dark-card'

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
  return (
    blocks !== undefined &&
    blocks.length > 0 &&
    blocks.every((block) => block.completed_at !== null || block.skipped_at !== null)
  )
}

// Same fixed workout-flow order, labels and icons as NewSchedulePage/
// TrainingSessionPage's own page-local copies (that pair's own comments
// call out the duplication convention this follows) -- DayDetailModal's
// history view groups by phase the same way both of those already do, so a
// past day reads the same whether you're looking at it live or looking back.
const PHASE_SEQUENCE: TrainingPhase[] = ['warmup', 'main', 'cooldown', 'puck']

const PHASE_LABELS: Record<TrainingPhase, string> = {
  warmup: 'Разминка',
  main: 'Основная часть',
  cooldown: 'Заминка',
  puck: 'Владение шайбой',
}

const PHASE_ICONS: Record<TrainingPhase, string> = {
  warmup: 'ti-flame',
  main: 'ti-barbell',
  cooldown: 'ti-wind',
  puck: 'ti-disc',
}

function formatTargetVolume(exercise: ExerciseRead): string | null {
  if (exercise.target_sets !== null && exercise.rep_range_min !== null && exercise.rep_range_max !== null) {
    return `${exercise.target_sets} × ${exercise.rep_range_min}-${exercise.rep_range_max}`
  }
  if (exercise.target_duration_seconds !== null) {
    return `${exercise.target_duration_seconds} сек`
  }
  return null
}

// At least one exercise ticked but not every one -- "Начать тренировку" reads
// as a lie once the player has already been in the session (found
// 2026-08-27: reopening TodayCard after checking off a few exercises still
// offered to "start" it from scratch instead of picking back up where they
// left off).
function isSessionDayStarted(day: DayPlanRead): boolean {
  const blocks = day.training_session?.blocks
  return blocks !== undefined && blocks.some((block) => block.completed_at !== null || block.skipped_at !== null)
}

// Backed by GET /users/me/activity-calendar (2026-08-19) -- real
// per-day completion history for whatever month is currently loaded,
// not just the current week's WeeklyPlanRead plus a single
// TrainingStreak.last_activity_date guess for every other day.
function hasKnownActivity(iso: string, calendarData: Record<string, ActivityCalendarDayRead>): boolean {
  return calendarData[iso]?.fully_completed === true
}

function topSkillsNearMilestone(skills: SkillSummaryRead[]): SkillSummaryRead[] {
  return skills
    .filter((skill) => skill.next_milestone !== null)
    .sort((a, b) => a.next_milestone!.points_remaining - b.next_milestone!.points_remaining)
    .slice(0, 3)
}

export function HomePage() {
  const { user, accessToken, updateUser } = useAuth()
  const navigate = useNavigate()

  // Local, session-only guard on top of user.has_seen_onboarding_tour --
  // set the instant the tour closes, regardless of whether the
  // persist-to-server call below succeeds, so a dropped request never
  // strands the user behind the tour; worst case it just shows again next
  // launch.
  const [tourDismissed, setTourDismissed] = useState(false)

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
  const [calendarData, setCalendarData] = useState<Record<string, ActivityCalendarDayRead>>({})
  const [selectedDay, setSelectedDay] = useState<Date | null>(null)
  // Lazily fetched fallback for a day the calendar shows activity for but
  // that isn't inside the currently-loaded WeeklyPlan (any day outside the
  // current week -- last week, further back, or next week before it's
  // loaded) -- see the effect below and GET /schedule/day-plan. Keyed by
  // isoDate (not just the plan) so a stale result from a previously-
  // selected day is never shown for a new one while its own fetch is still
  // in flight.
  const [fetchedDayPlan, setFetchedDayPlan] = useState<{ isoDate: string; plan: DayPlanRead | null } | null>(
    null,
  )

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
      // Rating excess needs an age-based expected baseline, and age is
      // genuinely optional (never collected anywhere in onboarding or
      // registration) -- the backend 400s without it. That must not take
      // down the rest of the dashboard the way an unguarded Promise.all
      // member would (Promise.all rejects whole -- weeklyPlan/streak/stats
      // would all silently fail to ever reach state, leaving the entire
      // dashboard blank behind a single raw backend error string). Caught
      // locally instead of routed through loadOptional (that helper's
      // contract is specifically "404 means not-yet-declared" -- this is a
      // different, 400, "not eligible" case).
      leaderboardApi.getMyLeaderboardPosition(accessToken).catch(() => null),
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

  // Only fetched once the panel is actually open (not on every dashboard
  // load) and refetched whenever the visible month changes -- one request
  // per month, not one per day like a naive per-cell fetch would be.
  useEffect(() => {
    if (accessToken === null || !calendarExpanded) {
      return
    }
    let cancelled = false
    progressApi
      .getMyActivityCalendar(toIsoDate(calendarMonth), accessToken)
      .then((days) => {
        if (cancelled) {
          return
        }
        const byDate: Record<string, ActivityCalendarDayRead> = {}
        for (const day of days) {
          byDate[day.date] = day
        }
        setCalendarData(byDate)
      })
      .catch(() => {
        // Best-effort -- a failed fetch just leaves this month's cells
        // unhighlighted rather than taking down the rest of the dashboard.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, calendarExpanded, calendarMonth])

  // A day tapped in the calendar is usually inside weeklyPlan already (this
  // week) and needs no fetch at all -- this only runs for a day outside it
  // (see DayDetailModal, which used to just say "детали недоступны" for
  // exactly this case). loadOptional/404 covers a date with no DayPlan at
  // all (a future day nothing's been generated for).
  useEffect(() => {
    if (accessToken === null || selectedDay === null) {
      return
    }
    const isoDate = toIsoDate(selectedDay)
    if (weeklyPlan?.day_plans.some((day) => day.date === isoDate) === true) {
      return
    }
    let cancelled = false
    loadOptional(scheduleApi.getDayPlan(isoDate, accessToken)).then((plan) => {
      if (!cancelled) {
        setFetchedDayPlan({ isoDate, plan })
      }
    })
    return () => {
      cancelled = true
    }
  }, [accessToken, selectedDay, weeklyPlan])

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

  async function persistTourSeen() {
    if (accessToken === null) {
      return
    }
    try {
      const updated = await usersApi.markOnboardingTourSeen(accessToken)
      updateUser(updated)
    } catch {
      // Best-effort -- tourDismissed below already lets this session
      // through; a failed persist just means the tour shows again next
      // launch instead of being gone for good.
    }
  }

  function handleTourSkip() {
    setTourDismissed(true)
    void persistTourSeen()
  }

  function handleTourComplete() {
    setTourDismissed(true)
    void persistTourSeen()
    // Straight into planning the first week -- an empty Home dashboard
    // ("Нет плана на сегодня") right after the tour is a dead end, not a
    // next step.
    navigate('/schedule/new')
  }

  const showTour = user !== null && !user.has_seen_onboarding_tour && !tourDismissed
  // The welcome tour covers the page but doesn't unmount it -- without this,
  // a coachmark registered by whatever's underneath (e.g. "Ближайшие
  // пороги") renders right on top of the tour instead of waiting for it to
  // close (found live, 2026-08-30, on a brand-new account's first visit).
  useSuppressCoachmarks(showTour)

  const todayIso = toIsoDate(new Date())
  const today = weeklyPlan?.day_plans.find((day) => day.date === todayIso) ?? null
  const avatarUrl = user?.avatar_url != null ? `${API_BASE_URL}${user.avatar_url}` : null
  const avatarTierStyle = getAvatarTierStyle(user?.level ?? 1)
  const selectedIsoDate = selectedDay !== null ? toIsoDate(selectedDay) : null
  const selectedDayWeeklyPlanDay =
    selectedIsoDate !== null ? weeklyPlan?.day_plans.find((day) => day.date === selectedIsoDate) : undefined
  // fetchedDayPlan.plan is `null` for "fetched, no plan for that date" (a
  // real answer -- don't fall through to "still loading"), so only
  // `undefined` (nothing fetched yet, or for a different date) is coerced
  // away below; DayDetailModal tells the two apart via isLoadingPlan.
  const fetchedForSelectedDate =
    fetchedDayPlan?.isoDate === selectedIsoDate ? fetchedDayPlan.plan : undefined
  const selectedDayPlan = selectedDayWeeklyPlanDay ?? fetchedForSelectedDate ?? undefined
  const isLoadingSelectedDayPlan =
    selectedIsoDate !== null && selectedDayWeeklyPlanDay === undefined && fetchedForSelectedDate === undefined
  const selectedDayHasActivity =
    selectedDay !== null && hasKnownActivity(toIsoDate(selectedDay), calendarData)
  const selectedSkillName = skills?.find((skill) => skill.id === selectedSkillId)?.name ?? ''
  const selectedStat =
    selectedStatType !== null ? (stats?.find((stat) => stat.stat_type === selectedStatType) ?? null) : null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      {showTour && <OnboardingTour onSkip={handleTourSkip} onComplete={handleTourComplete} />}
      <div className="relative z-[1] mx-auto flex min-h-svh max-w-3xl flex-col gap-4 px-4 py-8">
        <div className={`flex flex-col gap-4 p-4 ${CARD_CLASS}`}>
          {/* Level sits under the name (identity info, left-aligned with
              it) instead of paired with the streak button on the right --
              the two read as unrelated facts (character level vs. a
              daily-activity counter), so pairing them as matched pills
              read as arbitrary rather than intentional.

              No flex-wrap here (tried it, wrong call -- the streak button
              would drop to a second row on a long name, which looks like
              something broke, not like a deliberate layout). Instead
              min-w-0 on both the left column and its name/position wrapper
              lets THAT column shrink and wrap its own text across two
              lines -- the streak button stays shrink-0 and pinned to this
              same row no matter how long the name is. */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-4">
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
              <div className="flex min-w-0 flex-col gap-1">
                <span className="text-xl font-bold leading-tight text-[#F5F7FA]">
                  {user !== null ? getDisplayName(user) : ''}
                </span>
                <span className="text-sm text-[#8A94A6]">
                  {user?.position != null ? POSITION_LABELS[user.position] : ''}
                </span>
                {/* Same compact pill ProfilePage's own card uses for level
                    (px-2.5 py-0.5, text-[11px]) -- one style for "level
                    badge sitting under a name" wherever that pattern shows
                    up, not a one-off sized to match a neighboring button. */}
                <span className="mt-0.5 flex w-fit items-center gap-1 rounded-md border border-accent-ice/25 bg-accent-ice/[0.08] px-2.5 py-0.5">
                  <span className="font-sans text-[9px] font-semibold uppercase tracking-wider text-accent-ice/70">
                    Ур.
                  </span>
                  <span className="font-display text-sm font-semibold leading-none text-accent-ice">
                    {user?.level ?? 1}
                  </span>
                </span>
              </div>
            </div>

            {streak !== null && (
              <button
                type="button"
                onClick={() => setCalendarExpanded((value) => !value)}
                className="flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-white/10 bg-dark-bg px-3 py-2 transition-colors hover:border-white/20"
              >
                <i className="ti ti-flame text-xs text-accent-persimmon" aria-hidden="true" />
                <span className="font-mono text-xs font-bold text-accent-persimmon">
                  {streak.current_streak}
                </span>
                <i
                  className={`ti ${calendarExpanded ? 'ti-chevron-up' : 'ti-chevron-down'} text-xs text-[#8A94A6]`}
                  aria-hidden="true"
                />
              </button>
            )}
          </div>

          <XpBar level={user?.level ?? 1} xp={user?.xp ?? 0} />
        </div>

        {calendarExpanded && (
          <CalendarPanel
            month={calendarMonth}
            onMonthChange={setCalendarMonth}
            calendarData={calendarData}
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

            {user !== null && <TournamentTaperBanner tournamentDate={user.tournament_date} />}

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
          isLoadingPlan={isLoadingSelectedDayPlan}
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
      <div className={`relative overflow-hidden p-5 ${CARD_CLASS}`}>
        <CardGlow />
        {/* relative: an absolute sibling (CardGlow) with z-index:auto
            actually paints ABOVE static in-flow content per CSS stacking
            order -- relative (still z-index:auto) is what puts this back
            on top, same fix TeamDetailPage's card-glow already needed. */}
        <div className="relative flex items-center gap-4">
          <i
            className={`ti ${isRestDay ? SESSION_TYPE_ICONS.rest : 'ti-calendar-off'} text-2xl text-[#8A94A6]`}
            aria-hidden="true"
          />
          <div>
            {eyebrow !== '' && <p className="mb-1 text-xs uppercase tracking-wide text-[#8A94A6]">{eyebrow}</p>}
            <p className="text-lg font-semibold text-[#F5F7FA]">
              {isRestDay ? getRestDayHint(phase) : 'Нет плана на сегодня'}
            </p>
          </div>
        </div>
      </div>
    )
  }

  const completed = isSessionDayCompleted(day)
  const started = !completed && isSessionDayStarted(day)

  return (
    <div className={`relative overflow-hidden p-5 ${CARD_CLASS}`}>
      <CardGlow />
      <div className="relative flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          {eyebrow !== '' && <p className="text-xs uppercase tracking-wide text-[#8A94A6]">{eyebrow}</p>}
          {completed && (
            <span className="flex items-center gap-1 rounded-full bg-accent-ice/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-ice">
              <i className="ti ti-check" aria-hidden="true" />
              Выполнено
            </span>
          )}
        </div>
        <p className="flex items-center gap-2 text-2xl font-bold text-[#F5F7FA]">
          <i className={`ti ${SESSION_TYPE_ICONS[day.session_type]} ${SESSION_TYPE_COLORS[day.session_type]}`} aria-hidden="true" />
          {DAY_SESSION_TYPE_LABELS[day.session_type]}
        </p>
        {!completed && (
          <Button onClick={onStart} className="w-full">
            {started ? 'Продолжить тренировку' : 'Начать тренировку'}
          </Button>
        )}
      </div>
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
            className={`flex flex-col items-center gap-1.5 px-2 py-3 transition-colors hover:border-white/20 ${CARD_CLASS}`}
          >
            <StatIcon stat={statType} size={18} className="text-accent-ice" />
            <span className="text-[11px] text-[#8A94A6]">{STAT_ABBREVIATIONS[statType]}</span>
            <span className="font-display text-xl font-bold text-accent-ice">{Math.round(stat.current_value)}</span>
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
        <p className="font-display text-3xl font-bold leading-none text-[#F5F7FA]">
          {Math.round(stat.current_value)}
        </p>
      </div>
    </Modal>
  )
}

function SkillsNearMilestoneCard({
  skills,
  onSelectSkill,
}: {
  skills: SkillSummaryRead[]
  onSelectSkill: (skillId: string) => void
}) {
  // First real usage of the coachmark tour overlay (2026-08-30
  // discoverability pass) -- these rows just picked up a chevron+accent
  // affordance, but a first-time visitor still benefits from one explicit
  // "these are tappable" nudge the first time this card appears.
  const coachmarkRef = useCoachmarkStep(
    'home-skill-milestones',
    'Нажмите на навык, чтобы увидеть его пороги и вклад в характеристики.',
    'ti-hand-click',
  )
  const top = topSkillsNearMilestone(skills)
  if (top.length === 0) {
    return null
  }

  return (
    <div ref={coachmarkRef} className={`flex flex-col gap-3 p-4 ${CARD_CLASS}`}>
      <h2 className="text-sm font-medium text-[#8A94A6]">Ближайшие пороги</h2>
      <div className="flex flex-col gap-4">
        {top.map((skill) => {
          const milestone = skill.next_milestone!
          const nearThreshold = milestone.points_remaining < 5
          const percent =
            milestone.threshold > 0
              ? Math.max(0, Math.min(100, (skill.value / milestone.threshold) * 100))
              : 100
          return (
            <button
              key={skill.id}
              type="button"
              onClick={() => onSelectSkill(skill.id)}
              className="group flex items-center gap-3 text-left"
            >
              {/* Faceoff-circle ring, not a linear bar -- a milestone
                  threshold is a target you're closing in on, which the
                  ring reads as directly (hockey design pass, 2026-08-28).
                  Center shows percent; the text beside it still carries
                  the concrete "how many points" detail the ring can't. */}
              <FaceoffProgressRing
                value={skill.value}
                max={milestone.threshold}
                accent={nearThreshold ? 'persimmon' : 'ice'}
                size={48}
                centerValue={`${Math.round(percent)}%`}
              />
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                {/* Accent color, not plain white -- this row was tappable
                    but read as inert label text (discoverability pass,
                    2026-08-30: "Ближайшие пороги" names gave no visual
                    affordance). Same treatment as the chevron pattern
                    already used for row-style navigation elsewhere. */}
                <span className="truncate text-sm font-medium text-accent-ice">{skill.name}</span>
                {nearThreshold ? (
                  <span className="text-xs font-medium text-accent-persimmon">почти порог</span>
                ) : (
                  <span className="text-xs text-[#8A94A6]">
                    {Math.round(milestone.points_remaining)} до «{milestone.title}»
                  </span>
                )}
              </div>
              <i
                className="ti ti-chevron-right shrink-0 text-lg text-[#8A94A6] transition-all group-hover:translate-x-0.5 group-hover:text-accent-ice"
                aria-hidden="true"
              />
            </button>
          )
        })}
      </div>
    </div>
  )
}

// Mirrors app.core.training_block.TAPER_WINDOW_WEEKS / _TAPER_FINAL_WEEK_DAYS
// -- display-only, the server is the source of truth for actual volume.
const TAPER_WINDOW_DAYS = 21
const TAPER_FINAL_WEEK_DAYS = 7

function TournamentTaperBanner({ tournamentDate }: { tournamentDate: string | null }) {
  if (tournamentDate === null) {
    return null
  }
  const daysUntil = Math.floor(
    (new Date(tournamentDate).getTime() - new Date().setHours(0, 0, 0, 0)) / 86_400_000,
  )
  if (daysUntil < 0 || daysUntil >= TAPER_WINDOW_DAYS) {
    return null
  }
  const isFinalWeek = daysUntil < TAPER_FINAL_WEEK_DAYS

  return (
    <div className={`flex flex-col gap-2 p-4 ${CARD_CLASS_URGENT}`}>
      <p className="text-xs text-accent-persimmon">
        {isFinalWeek
          ? `Финальная неделя перед турниром (через ${daysUntil} дн.) — объём тренировок снижен по максимуму.`
          : `Подводка к турниру (через ${daysUntil} дн.) — объём тренировок постепенно снижается.`}
      </p>
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
        <span className="font-mono text-accent-ice">
          {block.sessions_completed_in_phase}/{block.sessions_to_advance}
        </span>
      </div>
      {infoOpen && <p className="text-xs text-[#8A94A6]">{description}</p>}
      {block.is_macrocycle_deload && (
        <p className="text-xs text-accent-persimmon">
          Восстановительный макроцикл — вес и повторы временно ниже обычного, чтобы вы отдохнули
          перед следующим циклом роста.
        </p>
      )}
      <ProgressBar value={block.sessions_completed_in_phase} max={block.sessions_to_advance} />
    </div>
  )
}

function RatingRow({ me, onClick }: { me: LeaderboardMeRead; onClick: () => void }) {
  const sign = me.rating_excess > 0 ? '+' : ''
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group flex w-full items-center justify-between gap-4 p-5 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
    >
      <div className="flex items-center gap-3">
        <RankBadge rank={me.rank} />
        <div className="flex flex-col gap-0.5">
          <span className="text-sm font-medium text-[#F5F7FA]">Рейтинг</span>
          {/* Same explanation LeaderboardPage gives for rating_excess, trimmed to fit a one-line subtitle. */}
          <span className="text-xs text-[#8A94A6]">Относительно вашего возраста и стажа</span>
        </div>
      </div>
      <span className="flex shrink-0 items-center gap-2">
        <span className="font-display text-lg font-semibold text-accent-ice">{sign}{me.rating_excess.toFixed(1)}</span>
        {/* Discoverability pass, 2026-08-30 -- a CARD_CLASS row that
            navigates needs the same chevron cue /more and /reference's rows
            already carry, not just "it's a button" left implicit. */}
        <i
          className="ti ti-chevron-right text-lg text-[#8A94A6] transition-all group-hover:translate-x-0.5 group-hover:text-accent-ice"
          aria-hidden="true"
        /></span>
    </button>
  )
}

function CalendarPanel({
  month,
  onMonthChange,
  calendarData,
  onSelectDay,
}: {
  month: Date
  onMonthChange: (month: Date) => void
  calendarData: Record<string, ActivityCalendarDayRead>
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
          const active = hasKnownActivity(iso, calendarData)
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
  isLoadingPlan,
  hasKnownActivity: dayHasActivity,
  onClose,
}: {
  date: Date
  dayPlan: DayPlanRead | undefined
  isLoadingPlan: boolean
  hasKnownActivity: boolean
  onClose: () => void
}) {
  return (
    <Modal title={formatShortDate(date)} onClose={onClose}>
      {isLoadingPlan && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

      {!isLoadingPlan && dayPlan === undefined && (
        <p className="text-sm text-[#8A94A6]">
          {dayHasActivity
            ? // GET /schedule/day-plan (by exact date) came back 404 despite
              // GET /users/me/activity-calendar marking this date
              // fully_completed -- shouldn't happen (fully_completed implies
              // a DayPlan+TrainingSession exist), kept as a defensive
              // fallback rather than assumed impossible.
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
        <DayDetailSession session={dayPlan.training_session} sessionType={dayPlan.session_type} />
      )}
    </Modal>
  )
}

// Same phase-card shape as NewSchedulePage's DayPreviewPhaseSection/
// StartedDayPhaseSection and TrainingSessionPage's PhasePreviewSheet -- icon
// + label + count header, hairline-divided rows below -- rather than the
// flat "name, checkmark" list this replaced (found 2026-08-27: "текста
// дохрена" -- a fully off-ice day is 15+ exercises with nothing visually
// separating one from the next, or one phase from another).
function DayDetailSession({
  session,
  sessionType,
}: {
  session: TrainingSessionRead
  sessionType: DaySessionType
}) {
  const doneCount = session.blocks.filter(
    (block) => block.completed_at !== null || block.skipped_at !== null,
  ).length
  const totalCount = session.blocks.length
  const durationMinutes = Math.max(1, Math.round(session.duration_seconds / 60))

  const blocksByPhase: Record<TrainingPhase, SessionBlockRead[]> = {
    warmup: [],
    main: [],
    cooldown: [],
    puck: [],
  }
  for (const block of session.blocks) {
    blocksByPhase[block.phase].push(block)
  }
  const activePhases = PHASE_SEQUENCE.filter((phase) => blocksByPhase[phase].length > 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-sm font-medium text-[#F5F7FA]">
          <i
            className={`ti ${SESSION_TYPE_ICONS[sessionType]} ${SESSION_TYPE_COLORS[sessionType]}`}
            aria-hidden="true"
          />
          {DAY_SESSION_TYPE_LABELS[sessionType]}
        </span>
        <span className="font-mono text-xs text-[#8A94A6]">
          {doneCount} из {totalCount} · ~{durationMinutes} мин
        </span>
      </div>

      {activePhases.map((phase) => (
        <div key={phase} className={`overflow-hidden rounded-md ${CARD_BORDER} bg-dark-bg/40`}>
          <div className="flex items-center gap-2 px-3 pb-2 pt-2.5">
            <i className={`ti ${PHASE_ICONS[phase]} text-sm text-accent-ice`} aria-hidden="true" />
            <p className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">{PHASE_LABELS[phase]}</p>
            <span className="ml-auto font-mono text-[11px] text-[#8A94A6]">{blocksByPhase[phase].length}</span>
          </div>
          <div className="flex flex-col divide-y divide-white/5">
            {blocksByPhase[phase].map((block) => {
              const volume = formatTargetVolume(block.exercise)
              const skipped = block.skipped_at !== null
              const done = block.completed_at !== null || skipped
              return (
                <div key={block.id} className="flex items-center gap-3 px-3 py-2.5">
                  <i
                    className={`ti ${
                      skipped ? 'ti-player-skip-forward text-[#8A94A6]' : done ? 'ti-check text-accent-ice' : 'ti-minus text-[#8A94A6]'
                    } shrink-0 text-xs`}
                    aria-hidden="true"
                  />
                  <span className={`line-clamp-2 min-w-0 flex-1 text-sm ${done ? 'text-[#F5F7FA]' : 'text-[#8A94A6]'}`}>
                    {block.exercise.name}
                  </span>
                  {volume !== null && (
                    <span className="shrink-0 whitespace-nowrap rounded bg-white/5 px-1.5 py-0.5 font-mono text-[11px] text-[#8A94A6]">
                      {volume}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
