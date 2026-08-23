import { useNavigate } from 'react-router-dom'
import { Modal } from './ui/Modal'

// Same icy top-border card convention as Home/Profile/TrainingSession.
const CARD_CLASS = 'rounded-md border-t border-[rgba(215,239,255,0.35)] bg-dark-card'

interface MoreItem {
  icon: string
  label: string
  description: string
  to?: string
  comingSoon?: boolean
}

const ITEMS: MoreItem[] = [
  { icon: 'ti-book', label: 'Справочник', description: 'Статьи и техника упражнений', to: '/reference' },
  { icon: 'ti-notebook', label: 'Дневник', description: 'Заметки о тренировках на льду и играх', to: '/diary' },
  {
    icon: 'ti-bandage',
    label: 'Ограничения',
    description: 'Что болит, чтобы не предлагать эти упражнения',
    to: '/restrictions',
  },
  { icon: 'ti-users', label: 'Команда', description: 'Создать команду или вступить по коду', to: '/teams' },
  { icon: 'ti-user-plus', label: 'Друзья', description: 'Добавляйте друзей и сравнивайте статы', to: '/friends' },
  {
    icon: 'ti-users-group',
    label: 'Совместные тренировки',
    description: 'Позовите друзей потренироваться в один день',
    to: '/training-parties',
  },
]

// Popup opened by BottomNav's "Ещё" tab -- a quick pick of the secondary
// sections right where the tab was tapped, instead of first landing on an
// intermediate page just to choose one.
export function MoreMenu({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate()

  function handleSelect(to: string) {
    onClose()
    navigate(to)
  }

  return (
    <Modal title="Ещё" onClose={onClose}>
      <div className="flex flex-col gap-2">
        {ITEMS.map((item) =>
          item.comingSoon ? (
            <div
              key={item.label}
              className={`flex w-full items-center gap-3 p-4 opacity-50 ${CARD_CLASS}`}
            >
              <i className={`ti ${item.icon} shrink-0 text-xl text-[#8A94A6]`} aria-hidden="true" />
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="truncate text-sm font-medium text-[#F5F7FA]">{item.label}</span>
                <span className="truncate text-xs text-[#8A94A6]">{item.description}</span>
              </div>
              <span className="shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[#8A94A6]">
                Скоро
              </span>
            </div>
          ) : (
            <button
              key={item.label}
              type="button"
              onClick={() => item.to !== undefined && handleSelect(item.to)}
              className={`flex w-full items-center gap-3 p-4 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
            >
              <i className={`ti ${item.icon} shrink-0 text-xl text-[#8A94A6]`} aria-hidden="true" />
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="truncate text-sm font-medium text-[#F5F7FA]">{item.label}</span>
                <span className="truncate text-xs text-[#8A94A6]">{item.description}</span>
              </div>
              <i className="ti ti-chevron-right shrink-0 text-lg text-[#8A94A6]" aria-hidden="true" />
            </button>
          ),
        )}
      </div>
    </Modal>
  )
}
