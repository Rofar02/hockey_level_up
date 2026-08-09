import { Link } from 'react-router-dom'
import { AdminLayout } from '../../components/admin/AdminLayout'

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
      </div>
    </AdminLayout>
  )
}
