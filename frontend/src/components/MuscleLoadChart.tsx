import { useEffect, useRef, useState } from 'react'
import { BodyChart, ViewSide } from 'body-muscles'
import type { MuscleLoadRead } from '../types/progress'
import {
  MUSCLE_LOAD_STAGES,
  MUSCLE_LOAD_STAGE_LABELS,
  buildBodyMusclesState,
} from '../utils/muscleLoad'

// Approximate yellow->orange->red swatches for the legend, matching the
// library's own gradient description -- not read from its exported
// INTENSITY_COLORS, which is a continuous 0-10 gradient with no natural
// single color per discrete stage boundary.
const STAGE_SWATCH_COLORS: Record<(typeof MUSCLE_LOAD_STAGES)[number], string> = {
  untrained: '#3A4152',
  fresh: '#4C9F70',
  light: '#D8C441',
  moderate: '#E08B3B',
  overloaded: '#D5493A',
}

// Thin React wrapper around body-muscles' vanilla BodyChart class (see
// https://github.com/vulovix/body-muscles -- Apache-2.0, not MIT as the
// planning doc that introduced this stated; zero-dependency, no
// React-specific export exists in the package itself, hence this
// wrapper). Front/back switching is built here as two plain buttons
// driving the `view` option, not delegated to the library -- its actual
// public API (checked against the installed package, not just the
// README) only exposes `view`/`showViewLabel` as passive options with no
// built-in toggle control, contrary to what the planning doc assumed.
export function MuscleLoadChart({ loads }: { loads: MuscleLoadRead[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<BodyChart | null>(null)
  const [view, setView] = useState<ViewSide>(ViewSide.FRONT)

  useEffect(() => {
    if (containerRef.current === null) {
      return
    }
    const chart = new BodyChart(containerRef.current, {
      view,
      bodyState: buildBodyMusclesState(loads),
    })
    chartRef.current = chart
    return () => {
      chart.destroy()
      chartRef.current = null
    }
    // Instantiated once on mount -- the effect below keeps it in sync with
    // later view/loads changes via chart.update(), the same split the
    // library's own README example uses (construct once, update()
    // afterwards) rather than destroying/recreating on every change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    chartRef.current?.update({ view, bodyState: buildBodyMusclesState(loads) })
  }, [view, loads])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-center gap-2">
        <button
          type="button"
          onClick={() => setView(ViewSide.FRONT)}
          className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
            view === ViewSide.FRONT
              ? 'border-accent-ice text-accent-ice'
              : 'border-white/10 text-text-secondary hover:text-text-primary'
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
              : 'border-white/10 text-text-secondary hover:text-text-primary'
          }`}
        >
          Сзади
        </button>
      </div>
      <div ref={containerRef} className="mx-auto w-full max-w-[280px]" />
      <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
        {MUSCLE_LOAD_STAGES.map((stage) => (
          <div key={stage} className="flex items-center gap-1.5">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: STAGE_SWATCH_COLORS[stage] }}
              aria-hidden="true"
            />
            <span className="text-xs text-text-secondary">{MUSCLE_LOAD_STAGE_LABELS[stage]}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
