import { Modal } from './Modal'
import { LEVEL_MILESTONES } from '../../utils/levelUnlocks'

// What the level badge's tap opens -- a plain progression list rather than
// reusing SkillDetailModal's threshold-bar shape, since these perks are
// binary (unlocked at level N or not) with no partial-progress value to
// show, unlike a skill's stat-driven thresholds.
export function LevelUnlocksModal({ level, onClose }: { level: number; onClose: () => void }) {
  return (
    <Modal title="Прокачка уровня" onClose={onClose}>
      <div className="flex flex-col gap-2">
        {LEVEL_MILESTONES.map((milestone) => {
          const unlocked = level >= milestone.level
          return (
            <div
              key={milestone.level}
              className={`flex items-center gap-3 rounded-md border px-3 py-2.5 ${
                unlocked ? 'border-accent-ice/25 bg-accent-ice/[0.06]' : 'border-white/10'
              }`}
            >
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                  unlocked ? 'bg-accent-ice/15' : 'bg-white/5'
                }`}
              >
                <i
                  className={`ti ${unlocked ? 'ti-check' : 'ti-lock'} text-sm ${
                    unlocked ? 'text-accent-ice' : 'text-[#8A94A6]'
                  }`}
                  aria-hidden="true"
                />
              </span>
              <div className="flex min-w-0 flex-1 flex-col">
                <span className={`text-sm font-medium ${unlocked ? 'text-[#F5F7FA]' : 'text-[#8A94A6]'}`}>
                  {milestone.label}
                </span>
                <span className="text-xs text-[#8A94A6]">
                  {unlocked ? `Открыто с уровня ${milestone.level}` : `Откроется на уровне ${milestone.level}`}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </Modal>
  )
}
