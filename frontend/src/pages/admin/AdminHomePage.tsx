import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as teamsApi from '../../api/teams'
import { AdminLayout } from '../../components/admin/AdminLayout'
import { useAuth } from '../../hooks/useAuth'
import type { OtherLeagueNameRead } from '../../types/team'

// What captains type into "Другая лига" -- popular names are candidates
// for the fixed list in app/core/leagues.py.
function OtherLeaguesCard() {
  const { accessToken } = useAuth()
  const [rows, setRows] = useState<OtherLeagueNameRead[] | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamsApi
      .listOtherLeagueNames(accessToken)
      .then((result) => {
        if (!cancelled) {
          setRows(result)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRows([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  return (
    <div className="rounded-md border border-white/10 bg-dark-card p-6 sm:col-span-2">
      <h2 className="text-lg font-semibold">«Другая лига» у команд</h2>
      <p className="mt-1 text-sm text-text-secondary">
        Что капитаны вписывают сами. Популярные лиги стоит добавить в общий список.
      </p>
      {rows !== null && rows.length === 0 && <p className="mt-3 text-sm text-text-secondary">Пока никто не вписал.</p>}
      {rows !== null && rows.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1 text-sm">
          {rows.map((row) => (
            <li key={row.name} className="flex justify-between gap-3">
              <span className="min-w-0 truncate">{row.name}</span>
              <span className="shrink-0 text-text-secondary">{row.team_count}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function AdminHomePage() {
  return (
    <AdminLayout title="Админ-панель">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Link
          to="/admin/exercises"
          className="rounded-md border border-white/10 bg-dark-card p-6 transition-colors hover:border-accent-ice/40"
        >
          <h2 className="text-lg font-semibold">Упражнения</h2>
          <p className="mt-1 text-sm text-text-secondary">
            Каталог упражнений: создание, редактирование, привязка к навыкам.
          </p>
        </Link>
        <Link
          to="/admin/skills"
          className="rounded-md border border-white/10 bg-dark-card p-6 transition-colors hover:border-accent-ice/40"
        >
          <h2 className="text-lg font-semibold">Навыки</h2>
          <p className="mt-1 text-sm text-text-secondary">
            Навыки, веса характеристик и пороги.
          </p>
        </Link>
        <Link
          to="/admin/reference-articles"
          className="rounded-md border border-white/10 bg-dark-card p-6 transition-colors hover:border-accent-ice/40"
        >
          <h2 className="text-lg font-semibold">Справочник</h2>
          <p className="mt-1 text-sm text-text-secondary">Статьи справочника: создание, редактирование, удаление.</p>
        </Link>
        <Link
          to="/admin/users"
          className="rounded-md border border-white/10 bg-dark-card p-6 transition-colors hover:border-accent-ice/40"
        >
          <h2 className="text-lg font-semibold">Пользователи</h2>
          <p className="mt-1 text-sm text-text-secondary">
            Список пользователей, права администратора и премиум-доступ.
          </p>
        </Link>
        <Link
          to="/admin/feedback"
          className="rounded-md border border-white/10 bg-dark-card p-6 transition-colors hover:border-accent-ice/40"
        >
          <h2 className="text-lg font-semibold">Обратная связь</h2>
          <p className="mt-1 text-sm text-text-secondary">Ошибки, идеи и сообщения от игроков, со скриншотами.</p>
        </Link>
        <OtherLeaguesCard />
      </div>
    </AdminLayout>
  )
}
