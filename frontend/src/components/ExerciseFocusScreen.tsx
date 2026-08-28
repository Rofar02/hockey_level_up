import { useEffect, useState } from 'react'
import { ExerciseDetailBody } from './ExerciseDetailModal'
import { ExerciseVideoStage } from './ExerciseVideoStage'
import * as exercisesApi from '../api/exercises'
import type { SessionBlockRead } from '../types/schedule'
import type { SkillSummaryRead } from '../types/skill'

// The row-tap "focus mode" from the hockey design pass (2026-08-28, plan
// item 1a): expands one exercise to fill the width TrainingSessionPage's
// exercise-list card normally uses, in place of that list -- the progress
// bar/stage tabs/"Этап N из M" heading above it in the page are untouched,
// so the step-by-step flow this nests inside (see PhaseTracker) stays
// exactly where it was, not covered by an overlay. ExerciseDetailBody
// (SetLogger, technique, replace) is reused as-is; this only adds the
// identity header (name + which skills it trains) and the ice-map zone
// visualization on top of it.
export function ExerciseFocusScreen({
  block,
  phaseLabel,
  phaseIcon,
  skills,
  trainingSessionId,
  accessToken,
  onBack,
  onComplete,
  onSettled,
  blockId,
  onReplaced,
}: {
  block: SessionBlockRead
  // Разминка/Основная часть/Заминка -- shown as its own chip here too, not
  // just relying on TrainingSessionPage's own heading above this card
  // (icelevel_player_master_prompt.md, 2026-08-28: "должно быть явно,
  // текстом ... видна в любой момент"). That heading survives regardless
  // (it sits outside this component entirely), but a long exercise
  // (several sets, feedback prompt) can scroll it out of view, so it's
  // repeated here where it can't.
  phaseLabel: string
  phaseIcon: string
  // Full skill catalog (id -> name), fetched once at the page level --
  // this component only resolves this one exercise's tag ids against it.
  skills: SkillSummaryRead[]
  trainingSessionId: string
  accessToken: string
  onBack: () => void
  // Forwarded to ExerciseDetailBody exactly as-is (undefined means "already
  // completed" or read-only, same gate the old boxed modal's call site
  // used) -- deliberately NOT re-derived from isExerciseDone here, which
  // for a target_sets exercise can go true before completed_at does (once
  // every set is logged) and would cut off SetLogger's own reconciling
  // effect that depends on this callback still being defined at that point.
  onComplete?: () => void
  // Fires once feedback is answered -- TrainingSessionPage uses this to
  // auto-advance to the next not-yet-done exercise in the phase without
  // returning to the list (icelevel_player_master_prompt.md, 2026-08-28).
  onSettled?: () => void
  blockId?: string
  onReplaced?: (updated: SessionBlockRead) => void
}) {
  const exercise = block.exercise
  const [skillNames, setSkillNames] = useState<string[]>([])

  useEffect(() => {
    let cancelled = false
    exercisesApi
      .listExerciseSkills(exercise.id, accessToken)
      .then((tags) => {
        if (cancelled) {
          return
        }
        const names = tags
          .map((tag) => skills.find((skill) => skill.id === tag.skill_id)?.name)
          .filter((name): name is string => name !== undefined)
        setSkillNames(names)
      })
      .catch(() => {
        // Best-effort -- the identity header just shows no skill line/falls
        // back to the generic zone below if this fails.
        setSkillNames([])
      })
    return () => {
      cancelled = true
    }
  }, [exercise.id, accessToken, skills])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={onBack}
          className="flex w-fit items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary"
        >
          <i className="ti ti-chevron-left" aria-hidden="true" />
          Назад к этапу
        </button>
        <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-white/10 px-2.5 py-1 text-[11px] font-medium uppercase tracking-wide text-text-secondary">
          <i className={`ti ${phaseIcon} text-accent-ice`} aria-hidden="true" />
          {phaseLabel}
        </span>
      </div>

      {/* Player-style stage: the real embed once a video exists, the same
          "video coming soon" placeholder either way -- ExerciseVideoStage
          is the one shared component for this (2026-08-28), also used
          inside the "Техника" tab below for the boxed modal context.
          Title sits above it as a normal heading rather than overlaid on
          top, since an overlay would sit on top of a real embed's own
          controls once video exists, not just this placeholder. */}
      <h2 className="text-xl font-bold leading-tight text-text-primary">{exercise.name}</h2>
      <ExerciseVideoStage exercise={exercise} />

      {skillNames.length > 0 && <p className="text-xs text-text-secondary">Развивает: {skillNames.join(', ')}</p>}

      <ExerciseDetailBody
        exercise={exercise}
        trainingSessionId={trainingSessionId}
        accessToken={accessToken}
        onClose={onBack}
        onLastSetCompleted={onComplete}
        onSettled={onSettled}
        blockId={blockId}
        onReplaced={onReplaced}
        variant="focus"
      />
    </div>
  )
}
