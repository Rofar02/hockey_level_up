import { useEffect, useRef, useState } from 'react'
import { BodyChart, ViewSide } from 'body-muscles'
import type { MuscleGroup } from '../types/exercise'
import { buildRestrictionBodyState, muscleGroupForLibraryId } from '../utils/muscleLoad'

// RestrictionsPage's picker for the 9 muscle groups covered by anatomy --
// the remaining few concerns with no single body location (rotation,
// coordination, stick-handling) stay as plain chips next to this, not on
// the avatar (see RestrictionsPage). Same body-muscles integration as
// MuscleLoadChart (Profile's load heatmap), stripped down to just this
// page's own two states -- already-restricted (persimmon-red) and
// currently-selected-to-report (the library's own selected outline) --
// with no intensity data, legend, or info panel to manage.
export function RestrictionAvatar({
  restrictedGroups,
  selectedGroup,
  onSelectGroup,
}: {
  restrictedGroups: MuscleGroup[]
  selectedGroup: MuscleGroup | null
  onSelectGroup: (group: MuscleGroup) => void
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<BodyChart | null>(null)
  const [view, setView] = useState<ViewSide>(ViewSide.FRONT)
  // onSelectGroup is bound once at construction time (see the mount-only
  // effect's own comment below) -- read through a ref so a later render's
  // closure never goes stale, same reasoning as MuscleLoadChart's loadsRef.
  const onSelectGroupRef = useRef(onSelectGroup)
  onSelectGroupRef.current = onSelectGroup

  const restrictedSet = new Set(restrictedGroups)

  useEffect(() => {
    if (containerRef.current === null) {
      return
    }
    const chart = new BodyChart(containerRef.current, {
      view,
      bodyState: buildRestrictionBodyState(restrictedSet, selectedGroup),
      onMuscleClick: (libraryId: string) => {
        const group = muscleGroupForLibraryId(libraryId)
        if (group !== null) {
          onSelectGroupRef.current(group)
        }
      },
    })
    chartRef.current = chart
    return () => {
      chart.destroy()
      chartRef.current = null
    }
    // Constructed once on mount, kept in sync via chart.update() below --
    // same split as MuscleLoadChart (see its own identical comment).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    chartRef.current?.update({ view, bodyState: buildRestrictionBodyState(restrictedSet, selectedGroup) })
    // restrictedSet is a fresh object every render -- keyed off
    // restrictedGroups (its actual dependency) instead, same reasoning
    // MuscleLoadChart uses for `loads`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, restrictedGroups, selectedGroup])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-center gap-2">
        <button
          type="button"
          onClick={() => setView(ViewSide.FRONT)}
          className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
            view === ViewSide.FRONT
              ? 'border-accent-ice text-accent-ice'
              : 'border-white/10 text-[#8A94A6] hover:text-[#F5F7FA]'
          }`}
        >
          Спереди
        </button>
        <button
          type="button"
          onClick={() => setView(ViewSide.BACK)}
          className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
            view === ViewSide.BACK
              ? 'border-accent-ice text-accent-ice'
              : 'border-white/10 text-[#8A94A6] hover:text-[#F5F7FA]'
          }`}
        >
          Сзади
        </button>
      </div>
      <div ref={containerRef} className="mx-auto w-full max-w-[280px] restriction-avatar" />
    </div>
  )
}
