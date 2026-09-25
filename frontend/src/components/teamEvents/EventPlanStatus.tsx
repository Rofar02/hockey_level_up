import type { TeamEventRead } from '../../types/teamEvent'
import { boardSummaryText } from '../../utils/boardPlan'

// One line about a training's plan, shared by the team page's "Ближайшее"
// card and the events list: what's in it once published, or -- for the
// captain -- whether there's still work to do. Nothing for a game.
export function EventPlanStatus({ event, isCaptain }: { event: TeamEventRead; isCaptain: boolean }) {
  if (event.event_type !== 'training') {
    return null
  }
  const summary = event.sections !== null ? boardSummaryText(event.sections) : null
  const isPublished = event.board_status === 'published'

  if (isPublished && summary !== null) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-accent-ice">
        <i className="ti ti-clipboard-check" aria-hidden="true" />
        План готов · {summary}
      </span>
    )
  }
  if (!isCaptain) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-[#8A94A6]">
        <i className="ti ti-clipboard" aria-hidden="true" />
        Тренер готовит план
      </span>
    )
  }
  if (summary === null) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-[#FF8A5C]">
        <i className="ti ti-clipboard-plus" aria-hidden="true" />
        План не составлен
      </span>
    )
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-[#FFCF5C]">
      <i className="ti ti-clipboard" aria-hidden="true" />
      Черновик · {summary} — не опубликован
    </span>
  )
}
