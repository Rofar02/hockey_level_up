import { useNavigate } from 'react-router-dom'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { BoardPlanView } from './BoardPlanView'
import { useTeamEvent, type LoadedTeamEvent } from '../../hooks/useTeamEvent'
import { formatMinutes, pluralRu, boardTotalMinutes } from '../../utils/boardPlan'
import { formatTime } from '../../utils/date'

function publishedSections(loaded: LoadedTeamEvent) {
  return loaded.event.board_status === 'published'
    ? (loaded.event.sections ?? []).filter((section) => section.drills.length > 0)
    : []
}

// The line under a team day on the week screen: when, and what's in the
// coach's plan ("Начало в 19:00 · 2 упражнения · 25 мин · 1 схема").
export function TeamDayWeekLine({ eventId }: { eventId: string }) {
  const loaded = useTeamEvent(eventId)
  if (loaded === undefined) {
    return <p className="text-xs text-[#8A94A6]">Загрузка командного события...</p>
  }
  if (loaded === null) {
    return null
  }
  const time = formatTime(new Date(loaded.event.starts_at))
  if (loaded.event.event_type !== 'training') {
    return <p className="text-xs text-[#8A94A6]">Начало в {time}</p>
  }
  const sections = publishedSections(loaded)
  const drills = sections.flatMap((section) => section.drills)
  if (drills.length === 0) {
    return <p className="text-xs text-[#8A94A6]">Начало в {time} · тренер ещё готовит план</p>
  }
  const minutes = boardTotalMinutes(sections)
  const schemes = drills.filter((drill) => drill.diagram !== null).length
  const parts = [
    `Начало в ${time}`,
    `${drills.length} ${pluralRu(drills.length, ['упражнение', 'упражнения', 'упражнений'])}`,
    minutes !== null ? formatMinutes(minutes) : null,
    schemes > 0 ? `${schemes} ${pluralRu(schemes, ['схема', 'схемы', 'схем'])}` : null,
  ]
  return <p className="text-xs text-[#8A94A6]">{parts.filter(Boolean).join(' · ')}</p>
}

// Tapping a team training on the week screen: the coach's plan (drills
// tappable, schemes visible), plus the app's own pre-ice warmup and the
// event page.
export function TeamDayPlanModal({
  title,
  eventId,
  onClose,
  onOpenWarmup,
}: {
  title: string
  eventId: string
  onClose: () => void
  onOpenWarmup: (() => void) | null
}) {
  const navigate = useNavigate()
  const loaded = useTeamEvent(eventId)
  const sections = loaded != null ? publishedSections(loaded) : []

  return (
    <Modal title={title} onClose={onClose}>
      <div className="flex flex-col gap-4">
        {loaded === undefined && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}
        {loaded === null && <p className="text-sm text-[#8A94A6]">Не удалось загрузить командное событие.</p>}
        {loaded != null && (
          <>
            <p className="text-sm text-[#8A94A6]">Начало в {formatTime(new Date(loaded.event.starts_at))}</p>
            {sections.length > 0 ? (
              <BoardPlanView sections={sections} />
            ) : (
              <p className="rounded-xl border border-dashed border-white/15 p-4 text-sm text-[#8A94A6]">
                Тренер ещё не опубликовал план. Он появится здесь, как только будет готов.
              </p>
            )}
            <div className="flex flex-col gap-2 border-t border-white/5 pt-3">
              {onOpenWarmup !== null && (
                <Button variant="neutral" onClick={onOpenWarmup} className="w-full">
                  Разминка до выхода на лёд
                </Button>
              )}
              <Button
                variant="neutral"
                onClick={() => navigate(`/teams/${loaded.teamId}/events/${loaded.event.id}`)}
                className="w-full"
              >
                Открыть событие
              </Button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
