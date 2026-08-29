import { Link } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'

interface SettingsItem {
  icon: string
  label: string
  description: string
  to: string
}

interface SettingsGroup {
  label: string
  items: SettingsItem[]
}

// Was a single ~1100-line page stacking 10 unrelated sections (profile form,
// equipment, season period, coach personality, tournament date, skills,
// two assessment tests, notifications, admin link, logout, delete account)
// in one endless scroll with no hierarchy -- found confusing enough that it
// got its own redesign pass (2026-08-30). Split into a MorePage-style hub
// (same grouped-rows-with-chevron pattern) linking out to one focused page
// per group, rather than fixing the chaos in place with just visual
// grouping -- each sub-page now only loads and holds the state its own
// section needs.
const GROUPS: SettingsGroup[] = [
  {
    label: 'Профиль и тренировки',
    items: [
      { icon: 'ti-user', label: 'Профиль', description: 'Имя, фамилия, игровой номер', to: '/settings/profile' },
      {
        icon: 'ti-barbell',
        label: 'Оборудование',
        description: 'Доступ в зал и свой инвентарь',
        to: '/settings/equipment',
      },
      {
        icon: 'ti-adjustments-horizontal',
        label: 'Тренировочный процесс',
        description: 'Период сезона, дата турнира, навыки, тон тренера',
        to: '/settings/training',
      },
      {
        icon: 'ti-clipboard-list',
        label: 'Тестирование',
        description: 'Оценка физподготовки и катания',
        to: '/settings/assessments',
      },
    ],
  },
  {
    label: 'Система',
    items: [
      {
        icon: 'ti-bell',
        label: 'Уведомления',
        description: 'Напоминания о тренировках',
        to: '/settings/notifications',
      },
      {
        icon: 'ti-user-circle',
        label: 'Аккаунт',
        description: 'Выход, удаление аккаунта',
        to: '/settings/account',
      },
    ],
  },
]

export function SettingsPage() {
  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-10">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Настройки</h1>
        </div>

        <div className="flex flex-col gap-4">
          {GROUPS.map((group) => (
            <div key={group.label} className="flex flex-col gap-2">
              <div className="flex items-center gap-2 px-1">
                <span className="h-px w-4 shrink-0 bg-accent-ice/60" aria-hidden="true" />
                <span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">
                  {group.label}
                </span>
                <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
              </div>
              {group.items.map((item) => (
                <Link
                  key={item.label}
                  to={item.to}
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
              ))}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
