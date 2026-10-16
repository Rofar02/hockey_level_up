import type { TeamEventDrillSectionRead } from '../../types/teamEvent'
import { formatMinutes, pluralRu, totalMinutes } from '../../utils/boardPlan'
import { diagramViewBox, isEmptyDiagram } from '../../utils/rinkDiagram'
import { RinkDiagram } from './diagram/RinkDiagram'

// The plan as a player meets it (2026-10-14): the reel's own look -- the
// title in the display face, a still of the first scheme, the drills by
// section -- and one big «Смотреть план» that opens the reel itself
// (TrainingReel). The event page's plan tab, the week screen's team day
// and the captain's «Как видит игрок» show this instead of the old list.

const PREVIEW_ASPECT = 16 / 9

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

export function PlanCover({
  sections,
  onOpen,
  compact = false,
}: {
  sections: TeamEventDrillSectionRead[]
  onOpen: () => void
  // The week screen's sheet: the header, the still and the button -- no list.
  compact?: boolean
}) {
  const withDrills = sections.filter((section) => section.drills.length > 0)
  const drills = withDrills.flatMap((section) => section.drills)
  const minutes = totalMinutes(drills)
  const firstScheme = drills.find((drill) => drill.diagram !== null && !isEmptyDiagram(drill.diagram))?.diagram ?? null
  const viewBox = firstScheme !== null ? diagramViewBox(firstScheme, PREVIEW_ASPECT) : null
  // Drills are numbered through the whole plan, as in the reel.
  const firstNumber = withDrills.map((_, k) =>
    withDrills.slice(0, k).reduce((sum, section) => sum + section.drills.length, 1),
  )

  return (
    <section
      aria-label="План тренировки"
      className="flex flex-col gap-4 overflow-hidden rounded-2xl border border-accent-ice/20 bg-[#0B111C] p-4 text-[#F5F7FA]"
    >
      <div className="flex flex-col items-center gap-1 border-y-2 border-accent-ice/55 py-2.5 text-center">
        <h2 className="font-display text-[26px] font-bold leading-none tracking-[0.05em]">ПЛАН ТРЕНИРОВКИ</h2>
        <p className="text-xs uppercase tracking-[0.1em] text-[#A9C7E0]">
          {drills.length} {pluralRu(drills.length, ['упражнение', 'упражнения', 'упражнений'])}
          {minutes !== null && ` · ${formatMinutes(minutes)}`}
        </p>
      </div>

      {firstScheme !== null && viewBox !== null && (
        <button
          type="button"
          onClick={onOpen}
          aria-label="Смотреть схемы"
          className="relative aspect-video w-full max-w-full overflow-hidden rounded-xl bg-[#E9F4FA]"
        >
          <RinkDiagram diagram={firstScheme} viewBox={viewBox} frame={null} className="h-full w-full" />
          <span className="absolute inset-0 flex items-center justify-center" aria-hidden="true">
            <span className="flex h-14 w-14 items-center justify-center rounded-full bg-[#0B111C]/80">
              <i className="ti ti-player-play text-2xl text-accent-ice" />
            </span>
          </span>
        </button>
      )}

      {!compact && (
        <ol className="flex flex-col gap-3">
          {withDrills.map((section, sectionIndex) => {
            const sectionMinutes = totalMinutes(section.drills)
            return (
              <li key={section.id} className="flex flex-col gap-1.5">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 font-display text-xs font-semibold tracking-[0.16em] text-accent-persimmon">
                    {section.name.toUpperCase()}
                  </span>
                  {sectionMinutes !== null && (
                    <span className="shrink-0 whitespace-nowrap font-display text-xs tracking-[0.1em] text-[#8A94A6]">
                      {formatMinutes(sectionMinutes).toUpperCase()}
                    </span>
                  )}
                </div>
                <ol className="flex flex-col gap-1">
                  {section.drills.map((drill, drillIndex) => {
                    return (
                      <li key={drill.id} className="flex min-w-0 items-baseline gap-3">
                        <span className="w-6 shrink-0 font-display text-sm font-semibold text-[#6B7588]">
                          {pad2(firstNumber[sectionIndex] + drillIndex)}
                        </span>
                        <span className="min-w-0 flex-1 truncate font-display text-[15px] uppercase tracking-wide">
                          {drill.title}
                        </span>
                        {drill.diagram !== null && !isEmptyDiagram(drill.diagram) && (
                          <i className="ti ti-route shrink-0 text-sm text-accent-ice" aria-label="есть схема" />
                        )}
                        {drill.duration_minutes !== null && (
                          <span className="shrink-0 text-xs tabular-nums text-[#8A94A6]">{drill.duration_minutes} мин</span>
                        )}
                      </li>
                    )
                  })}
                </ol>
              </li>
            )
          })}
        </ol>
      )}

      <button
        type="button"
        onClick={onOpen}
        className="flex h-[52px] w-full items-center justify-center gap-2 rounded-[14px] bg-accent-persimmon text-base font-semibold text-[#111827] transition-opacity hover:opacity-90"
      >
        <i className="ti ti-player-play" aria-hidden="true" />
        Смотреть план
      </button>
    </section>
  )
}
