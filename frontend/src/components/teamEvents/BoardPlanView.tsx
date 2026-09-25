import { useLayoutEffect, useRef, useState } from 'react'
import { CARD_CLASS } from '../ui/cardStyle'
import { Modal } from '../ui/Modal'
import { RinkDiagram } from './diagram/RinkDiagram'
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
                    <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="line-clamp-2 text-sm font-medium text-[#F5F7FA]">{drill.title}</span>
                      <DrillMeta drill={drill} />
                    </span>
                    {/* The scheme is the point of the plan for a player --
                        shown right in the list, not behind a tiny icon. */}
                    {drill.diagram !== null && (
                      <span
                        aria-hidden="true"
                        data-testid="scheme-thumbnail"
                        className="flex h-[76px] w-11 shrink-0 items-center justify-center overflow-hidden rounded-md border border-white/10 bg-[#0B0F14]/60"
                      >
                        <RinkDiagram diagram={drill.diagram} className="h-[76px] w-auto" />
                      </span>
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

function DrillMeta({ drill }: { drill: TeamEventDrillRead }) {
  const hasMinutes = drill.duration_minutes !== null
  const hasScheme = drill.diagram !== null
  if (!hasMinutes && !hasScheme) {
    return null
  }
  return (
    <span className="flex items-center gap-1.5 text-xs text-[#8A94A6]">
      {hasMinutes && formatMinutes(drill.duration_minutes ?? 0)}
      {hasMinutes && hasScheme && <span aria-hidden="true">·</span>}
      {hasScheme && (
        <span className="flex items-center gap-1 text-accent-ice">
          <i className="ti ti-route" aria-hidden="true" />
          схема
        </span>
      )}
    </span>
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
  const ref = useRef<HTMLDivElement>(null)
  // The detail replaces the list in place -- after tapping a drill far down
  // a long list, its top (and the scheme) would otherwise sit above or
  // below the visible area and the tap would look like it did nothing.
  useLayoutEffect(() => {
    const element = ref.current
    if (element === null) {
      return
    }
    const top = element.getBoundingClientRect().top
    if (top < 0 || top > window.innerHeight * 0.4) {
      element.scrollIntoView({ block: 'start' })
    }
  }, [drill.id])

  return (
    <div ref={ref} className="flex scroll-mt-4 flex-col gap-4">
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
      {drill.diagram !== null && (
        <div className="flex flex-col gap-2">
          <RinkDiagram diagram={drill.diagram} className="mx-auto max-h-[60dvh] w-auto max-w-full rounded-[18px]" />
          <DiagramLegend />
        </div>
      )}
      {drill.description !== null && drill.description !== '' ? (
        <p className="whitespace-pre-line text-sm leading-relaxed text-[#C9D1DC]">{drill.description}</p>
      ) : (
        <p className="text-sm text-[#8A94A6]">Тренер не добавил описание — уточни на льду.</p>
      )}
    </div>
  )
}

function DiagramLegend() {
  const items: { label: string; stroke: string; dash?: string; wave?: boolean; both?: boolean; shot?: boolean }[] = [
    { label: 'пас', stroke: '#FF6A3D' },
    { label: 'перепас', stroke: '#FF6A3D', both: true },
    { label: 'бросок', stroke: '#FF8A80', shot: true },
    { label: 'кат с шайбой', stroke: '#5FD4FF', wave: true },
    { label: 'кат без шайбы', stroke: '#F2F5F8', dash: '3 3' },
  ]
  return (
    <div className="flex flex-wrap justify-center gap-x-3 gap-y-1 text-[11px] text-[#8A94A6]">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1">
          <svg width="18" height="8" aria-hidden="true">
            {item.wave ? (
              <path d="M0,4 Q2.25,0 4.5,4 T9,4 T13.5,4 T18,4" stroke={item.stroke} strokeWidth="1.8" fill="none" />
            ) : item.shot ? (
              <path d="M0,2.5 L13,2.5 M0,5.5 L13,5.5 M12,0.5 L17.5,4 L12,7.5 Z" stroke={item.stroke} strokeWidth="1.3" fill={item.stroke} strokeLinejoin="round" />
            ) : item.both ? (
              <path d="M4,4 L14,4 M4,1 L0,4 L4,7 M14,1 L18,4 L14,7" stroke={item.stroke} strokeWidth="1.8" fill="none" strokeLinejoin="round" />
            ) : (
              <line x1="0" y1="4" x2="18" y2="4" stroke={item.stroke} strokeWidth="2" strokeDasharray={item.dash} />
            )}
          </svg>
          {item.label}
        </span>
      ))}
      <span className="flex items-center gap-1">
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
          <circle cx="6" cy="6" r="5.5" fill="#FF6A3D" />
          <text x="6" y="6.4" textAnchor="middle" dominantBaseline="central" fontSize="7" fontWeight="800" fill="#fff">
            1
          </text>
        </svg>
        порядок: одинаковые цифры — одновременно
      </span>
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
