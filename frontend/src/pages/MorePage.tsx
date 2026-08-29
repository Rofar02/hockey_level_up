import { Link } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'

interface MoreItem {
  icon: string
  label: string
  description: string
  to?: string
  comingSoon?: boolean
}

interface MoreGroup {
  label: string
  items: MoreItem[]
}

// Grouped with section labels (rather than a flat list or a tabs
// switcher) -- with only six items total, tabs would add a navigation
// layer for little payoff and risk destabilizing an already fragile
// layout; a labelled, scrollable list keeps everything reachable in
// one place. See docs/hockeylevelup_dev_plan.md discussion.
const GROUPS: MoreGroup[] = [
  {
    label: 'Тренировочный процесс',
    items: [
      { icon: 'ti-book', label: 'Справочник', description: 'Статьи об экипировке и основах хоккея', to: '/reference' },
      {
        icon: 'ti-clipboard-list',
        label: 'Каталог упражнений',
        description: 'Все упражнения с техникой — только для просмотра',
        to: '/exercise-catalog',
      },
      { icon: 'ti-notebook', label: 'Дневник', description: 'Заметки о тренировках на льду и играх', to: '/diary' },
      {
        icon: 'ti-bandage',
        label: 'Ограничения',
        description: 'Что болит, чтобы не предлагать эти упражнения',
        to: '/restrictions',
      },
    ],
  },
  {
    label: 'Социальное',
    items: [
      { icon: 'ti-users', label: 'Команда', description: 'Создать команду или вступить по коду', to: '/teams' },
      { icon: 'ti-user-plus', label: 'Друзья', description: 'Добавляйте друзей и сравнивайте статы', to: '/friends' },
      {
        icon: 'ti-users-group',
        label: 'Совместные тренировки',
        description: 'Позовите друзей потренироваться в один день',
        to: '/training-parties',
      },
    ],
  },
]

// BottomNav's "Ещё" tab used to open this as a popup right where it was
// tapped (see git history's MoreMenu) -- moved to its own route (2026-08-27)
// so it's a normal NavLink tab like the other three, back/forward and a
// direct link to /more both work, and it doesn't need Modal's body-scroll
// lock just to show six links.
export function MorePage() {
  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Ещё</h1>
        </div>

        <div className="flex flex-col gap-4">
          {GROUPS.map((group) => (
            <div key={group.label} className="flex flex-col gap-2">
              {/* Ice-line section header, not a bare uppercase label -- a
                  short accent segment (the blue line's paint) fading into a
                  hairline the rest of the way, echoing CARD_CLASS's own
                  "blue line" border convention (hockey design pass,
                  2026-08-30). */}
              <div className="flex items-center gap-2 px-1">
                <span className="h-px w-4 shrink-0 bg-accent-ice/60" aria-hidden="true" />
                <span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">
                  {group.label}
                </span>
                <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
              </div>
              {group.items.map((item) =>
                item.comingSoon ? (
                  <div
                    key={item.label}
                    className={`flex w-full items-center gap-3 p-4 opacity-50 ${CARD_CLASS}`}
                  >
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-white/5">
                      <i className={`ti ${item.icon} text-lg text-[#8A94A6]`} aria-hidden="true" />
                    </span>
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate text-sm font-medium text-[#F5F7FA]">{item.label}</span>
                      <span className="truncate text-xs text-[#8A94A6]">{item.description}</span>
                    </div>
                    {/* Dashed rather than the solid pill "Готово"/status
                        badges use elsewhere -- reads as "off the ice" (a
                        benched item), not a completed state, so it needs its
                        own distinct shape rather than borrowing that one. */}
                    <span className="shrink-0 rounded border border-dashed border-white/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[#8A94A6]">
                      Скоро
                    </span>
                  </div>
                ) : (
                  <Link
                    key={item.label}
                    to={item.to ?? '#'}
                    className={`group flex w-full items-center gap-3 p-4 text-left transition-colors hover:border-white/20 ${CARD_CLASS}`}
                  >
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent-ice/10">
                      <i className={`ti ${item.icon} text-lg text-accent-ice`} aria-hidden="true" />
                    </span>
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate text-sm font-medium text-[#F5F7FA]">{item.label}</span>
                      <span className="truncate text-xs text-[#8A94A6]">{item.description}</span>
                    </div>
                    <i
                      className="ti ti-chevron-right shrink-0 text-lg text-[#8A94A6] transition-all group-hover:translate-x-0.5 group-hover:text-accent-ice"
                      aria-hidden="true"
                    />
                  </Link>
                ),
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
