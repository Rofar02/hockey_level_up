import { useState } from 'react'
import { CARD_CLASS } from '../ui/cardStyle'
import { Modal } from '../ui/Modal'
import type { TeamEventDrillRead, TeamEventDrillSectionRead } from '../../types/teamEvent'
import { formatMinutes, totalMinutes } from '../../utils/boardPlan'

// Read-only board: sections in order, each drill tappable for its full
// description. Player side of EventBoardPanel and the body of
// BoardPlanModal (HomePage's team day card).
export function BoardPlanView({ sections }: { sections: TeamEventDrillSectionRead[] }) {
  const [selected, setSelected] = useState<{ drill: TeamEventDrillRead; sectionName: string } | null>(null)

  if (selected !== null) {
    return <DrillDetail drill={selected.drill} sectionName={selected.sectionName} onBack={() => setSelected(null)} />
  }

  const nonEmpty = sections.filter((section) => section.drills.length > 0)
  if (nonEmpty.length === 0) {
    return <p className="text-sm text-[#8A94A6]">В плане пока нет упражнений.</p>
  }

  return (
    <div className="flex flex-col gap-4">
      {nonEmpty.map((section) => {
        const minutes = totalMinutes(section.drills)
        return (
          <section key={section.id} className="flex flex-col gap-2">
            <div className="flex items-baseline justify-between gap-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">{section.name}</h3>
              {minutes !== null && <span className="text-xs text-[#5B6472]">{formatMinutes(minutes)}</span>}
            </div>
            <ul className="flex flex-col gap-2">
              {section.drills.map((drill, index) => (
                <li key={drill.id}>
                  <button
                    type="button"
                    onClick={() => setSelected({ drill, sectionName: section.name })}
                    className={`flex w-full items-center gap-3 p-3 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
                  >
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs text-[#8A94A6]">
                      {index + 1}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm font-medium text-[#F5F7FA]">{drill.title}</span>
                    {drill.duration_minutes !== null && (
                      <span className="shrink-0 text-xs text-[#8A94A6]">{formatMinutes(drill.duration_minutes)}</span>
                    )}
                    <i className="ti ti-chevron-right shrink-0 text-[#5B6472]" aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )
      })}
    </div>
  )
}

function DrillDetail({
  drill,
  sectionName,
  onBack,
}: {
  drill: TeamEventDrillRead
  sectionName: string
  onBack: () => void
}) {
  return (
    <div className="flex flex-col gap-4">
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-1 self-start text-sm text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
      >
        <i className="ti ti-chevron-left" aria-hidden="true" />
        Весь план
      </button>
      <div>
        <p className="text-xs uppercase tracking-wide text-[#8A94A6]">
          {sectionName}
          {drill.duration_minutes !== null && ` · ${formatMinutes(drill.duration_minutes)}`}
        </p>
        <h3 className="mt-1 text-lg font-semibold text-[#F5F7FA]">{drill.title}</h3>
      </div>
      {drill.description !== null && drill.description !== '' ? (
        <p className="whitespace-pre-line text-sm leading-relaxed text-[#C9D1DC]">{drill.description}</p>
      ) : (
        <p className="text-sm text-[#8A94A6]">Тренер не добавил описание — уточни на льду.</p>
      )}
    </div>
  )
}

export function BoardPlanModal({
  sections,
  onClose,
}: {
  sections: TeamEventDrillSectionRead[]
  onClose: () => void
}) {
  return (
    <Modal title="План тренировки" onClose={onClose}>
      <BoardPlanView sections={sections} />
    </Modal>
  )
}
