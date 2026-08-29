import { FormError } from './ui/FormError'
import { Modal } from './ui/Modal'
import { TARGET_STAT_LABELS } from '../types/exercise'
import type { SkillDetailRead } from '../types/skill'

// Shared by ProfilePage's full skill list and HomePage's "ближайшие пороги"
// card -- same detail view (stat contribution breakdown + milestones) either
// way, just triggered from different lists.
export function SkillDetailModal({
  skillName,
  detail,
  isLoading,
  error,
  onClose,
}: {
  skillName: string
  detail: SkillDetailRead | undefined
  isLoading: boolean
  error: string | null
  onClose: () => void
}) {
  return (
    <Modal title={skillName} onClose={onClose}>
      {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}
      <FormError message={error} />

      {detail !== undefined && (
        <div className="flex flex-col gap-4">
          <div>
            {/* Same ice-line divider as MorePage/ReferencePage section
                headers -- one convention for "labelled group" everywhere
                (hockey design pass, 2026-08-30). */}
            <div className="mb-2 flex items-center gap-2">
              <span className="h-px w-3 shrink-0 bg-accent-ice/60" aria-hidden="true" />
              <p className="shrink-0 text-xs font-medium uppercase tracking-wide text-text-secondary">
                Вклад характеристик
              </p>
              <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
            </div>
            <div className="flex flex-col gap-1.5">
              {detail.stat_breakdown.map((item) => (
                <div key={item.stat_type} className="flex items-center justify-between text-sm">
                  <span>{TARGET_STAT_LABELS[item.stat_type]}</span>
                  <span className="font-mono text-text-secondary">+{item.contribution.toFixed(1)}</span>
                </div>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-center gap-2">
              <span className="h-px w-3 shrink-0 bg-accent-ice/60" aria-hidden="true" />
              <p className="shrink-0 text-xs font-medium uppercase tracking-wide text-text-secondary">
                Пороги
              </p>
              <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
            </div>
            <div className="flex flex-col gap-2.5">
              {detail.milestones.map((milestone) => (
                <div key={milestone.id} className="flex items-start gap-2">
                  <i
                    className={`ti mt-0.5 ${
                      milestone.achieved ? 'ti-lock-open text-accent-ice' : 'ti-lock text-text-secondary'
                    }`}
                    aria-hidden="true"
                  />
                  <div>
                    <p
                      className={`text-sm ${
                        milestone.achieved ? 'text-text-primary' : 'text-text-secondary'
                      }`}
                    >
                      {milestone.threshold} — {milestone.title}
                    </p>
                    <p className="text-xs text-text-secondary">{milestone.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Modal>
  )
}
