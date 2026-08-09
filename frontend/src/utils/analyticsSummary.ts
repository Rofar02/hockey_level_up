import { TARGET_STAT_LABELS } from '../types/exercise'
import type { TargetStat } from '../types/exercise'
import type { AnalyticsMoverRead, AnalyticsSummaryRead } from '../types/analytics'

// Standard Russian plural-form selection (1 очко / 2 очка / 5 очков) -- the
// "N X" copy elsewhere in the app (HomePage/ProfilePage's milestone teaser)
// gets away with a bare number precisely by never spelling out a unit
// word; this summary does spell it out, so it has to get the grammar right.
function pluralizePoints(value: number): string {
  const abs = Math.abs(Math.round(value))
  const mod10 = abs % 10
  const mod100 = abs % 100
  if (mod100 >= 11 && mod100 <= 14) {
    return 'очков'
  }
  if (mod10 === 1) {
    return 'очко'
  }
  if (mod10 >= 2 && mod10 <= 4) {
    return 'очка'
  }
  return 'очков'
}

function moverLabel(mover: AnalyticsMoverRead): string {
  return mover.type === 'stat' ? TARGET_STAT_LABELS[mover.name as TargetStat] : mover.name
}

// "характеристика"/"навык" are fixed, grammatically-known nouns attached to
// whatever the actual (arbitrary, admin-authored) name is -- the verb only
// ever has to agree with these two constants, never with an unknown-gender
// skill name, so this never needs a name-to-gender lookup table.
function moverNoun(mover: AnalyticsMoverRead): string {
  return mover.type === 'stat' ? 'характеристика' : 'навык'
}

// Data-only summary (see app/schemas/analytics.py's comment on why) --
// this is where the actual Russian wording lives, kept separate from the
// computation so tone can change without touching AnalyticsService.
export function buildAnalyticsSummaryText(summary: AnalyticsSummaryRead): string {
  const sentences: string[] = []

  const gainerDelta = Math.round(summary.top_gainer.delta)
  if (gainerDelta > 0) {
    const verb = summary.top_gainer.type === 'stat' ? 'выросла' : 'вырос'
    sentences.push(
      `Заметнее всего ${verb} ${moverNoun(summary.top_gainer)} «${moverLabel(summary.top_gainer)}» — плюс ${gainerDelta} ${pluralizePoints(gainerDelta)}.`,
    )
  } else {
    sentences.push('Заметных изменений за этот период пока не было.')
  }

  if (summary.top_decliner !== null) {
    const declinerDelta = Math.abs(Math.round(summary.top_decliner.delta))
    const verb = summary.top_decliner.type === 'stat' ? 'просела' : 'просел'
    const reasonSuffix = summary.decline_reason !== null ? ` ${summary.decline_reason}` : ''
    sentences.push(
      `А вот ${moverNoun(summary.top_decliner)} «${moverLabel(summary.top_decliner)}» ${verb} — минус ${declinerDelta} ${pluralizePoints(declinerDelta)}.${reasonSuffix}`,
    )
  }

  if (summary.closest_to_milestone !== null) {
    const remaining = Math.round(summary.closest_to_milestone.points_remaining)
    sentences.push(
      `До следующего порога навыка «${summary.closest_to_milestone.skill_name}» осталось ${remaining} ${pluralizePoints(remaining)} — стоит налечь именно на него.`,
    )
  }

  return sentences.join(' ')
}
