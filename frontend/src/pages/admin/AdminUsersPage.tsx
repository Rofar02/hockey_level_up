import { Fragment, useEffect, useState } from 'react'
import { AdminLayout } from '../../components/admin/AdminLayout'
import { Button } from '../../components/ui/Button'
import { FormError } from '../../components/ui/FormError'
import { Switch } from '../../components/ui/Switch'
import { TextField } from '../../components/ui/TextField'
import * as adminUsersApi from '../../api/adminUsers'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import type { UserAdminRead, UserAdminUpdate } from '../../types/user'

const PAGE_SIZE = 20
// Debounces the search input before it drives a request -- typing "ivan"
// would otherwise fire 4 requests instead of 1.
const SEARCH_DEBOUNCE_MS = 300

function formatRegisteredAt(iso: string): string {
  const date = new Date(iso)
  const day = String(date.getDate()).padStart(2, '0')
  const month = String(date.getMonth() + 1).padStart(2, '0')
  return `${day}.${month}.${date.getFullYear()}`
}

export function AdminUsersPage() {
  const { accessToken } = useAuth()

  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)

  const [users, setUsers] = useState<UserAdminRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // Per-row: which user currently has a PATCH in flight (both switches on
  // that row disable together while it's saving, to avoid a second toggle
  // racing the first), and the last error for that row, if any.
  const [savingUserIds, setSavingUserIds] = useState<Set<string>>(new Set())
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({})

  // Debounce searchInput -> search, resetting to the first page whenever
  // the search term actually changes (a stale offset from a previous
  // search wouldn't make sense against a new result set).
  useEffect(() => {
    const handle = setTimeout(() => {
      setSearch(searchInput.trim())
      setOffset(0)
    }, SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(handle)
  }, [searchInput])

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    setIsLoading(true)
    adminUsersApi
      .listUsersAdmin({ q: search === '' ? undefined : search, limit: PAGE_SIZE, offset }, accessToken)
      .then((result) => {
        if (!cancelled) {
          setUsers(result)
          setLoadError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить пользователей.')
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, search, offset])

  async function toggleUserField(user: UserAdminRead, field: 'is_admin' | 'has_premium') {
    if (accessToken === null || savingUserIds.has(user.id)) {
      return
    }
    const previousValue = user[field]
    const nextValue = !previousValue
    const payload: UserAdminUpdate =
      field === 'is_admin' ? { is_admin: nextValue } : { has_premium: nextValue }

    setRowErrors((previous) => {
      if (!(user.id in previous)) {
        return previous
      }
      const next = { ...previous }
      delete next[user.id]
      return next
    })
    setSavingUserIds((previous) => new Set(previous).add(user.id))
    setUsers((previous) =>
      previous?.map((row) => (row.id === user.id ? { ...row, ...payload } : row)) ?? previous,
    )

    try {
      const updated = await adminUsersApi.updateUserAdmin(user.id, payload, accessToken)
      setUsers((previous) => previous?.map((row) => (row.id === user.id ? updated : row)) ?? previous)
    } catch (err) {
      const rollback: UserAdminUpdate =
        field === 'is_admin' ? { is_admin: previousValue } : { has_premium: previousValue }
      setUsers((previous) =>
        previous?.map((row) => (row.id === user.id ? { ...row, ...rollback } : row)) ?? previous,
      )
      // The only 400 this endpoint returns is the last-admin guard -- a
      // fixed, translated message reads better here than passing the
      // backend's English `detail` straight through into an otherwise
      // all-Russian admin UI.
      const message =
        err instanceof ApiError
          ? err.status === 400
            ? 'Нельзя снять права администратора с последнего администратора в системе.'
            : err.message
          : 'Не удалось сохранить изменение.'
      setRowErrors((previous) => ({ ...previous, [user.id]: message }))
    } finally {
      setSavingUserIds((previous) => {
        const next = new Set(previous)
        next.delete(user.id)
        return next
      })
    }
  }

  const hasNextPage = users !== null && users.length === PAGE_SIZE

  return (
    <AdminLayout title="Пользователи">
      <div className="mb-4 max-w-xs">
        <TextField
          label="Поиск"
          placeholder="Email, имя или фамилия"
          value={searchInput}
          onChange={(event) => setSearchInput(event.target.value)}
        />
      </div>

      <FormError message={loadError} />
      {isLoading && <p className="text-sm text-text-secondary">Загрузка...</p>}

      {!isLoading && users !== null && (
        <>
          <div className="overflow-x-auto rounded-md border border-white/10">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-white/10 bg-white/5 text-left text-text-secondary">
                  <th className="px-3 py-2 font-medium">Email</th>
                  <th className="px-3 py-2 font-medium">Имя</th>
                  <th className="px-3 py-2 font-medium">Уровень</th>
                  <th className="px-3 py-2 font-medium">Админ</th>
                  <th className="px-3 py-2 font-medium">Премиум</th>
                  <th className="px-3 py-2 font-medium">Регистрация</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-text-secondary">
                      Ничего не найдено.
                    </td>
                  </tr>
                )}
                {users.map((user) => (
                  <Fragment key={user.id}>
                    <tr className="border-b border-white/5 hover:bg-white/5">
                      <td className="px-3 py-2 text-text-primary">{user.email}</td>
                      <td className="px-3 py-2 text-text-secondary">
                        {[user.last_name, user.first_name].filter(Boolean).join(' ') || '—'}
                      </td>
                      <td className="px-3 py-2 font-mono text-text-secondary">{user.level}</td>
                      <td className="px-3 py-2">
                        <Switch
                          checked={user.is_admin}
                          disabled={savingUserIds.has(user.id)}
                          onClick={() => toggleUserField(user, 'is_admin')}
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Switch
                          checked={user.has_premium}
                          disabled={savingUserIds.has(user.id)}
                          onClick={() => toggleUserField(user, 'has_premium')}
                        />
                      </td>
                      <td className="px-3 py-2 font-mono text-text-secondary">
                        {formatRegisteredAt(user.created_at)}
                      </td>
                    </tr>
                    {rowErrors[user.id] !== undefined && (
                      <tr className="border-b border-white/5">
                        <td colSpan={6} className="px-3 pb-2">
                          <FormError message={rowErrors[user.id]} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-4 flex items-center justify-between gap-4">
            <Button
              type="button"
              variant="neutral"
              disabled={offset === 0}
              onClick={() => setOffset((previous) => Math.max(0, previous - PAGE_SIZE))}
            >
              Назад
            </Button>
            <span className="text-sm text-text-secondary">
              {offset + 1}–{offset + users.length}
            </span>
            <Button
              type="button"
              variant="neutral"
              disabled={!hasNextPage}
              onClick={() => setOffset((previous) => previous + PAGE_SIZE)}
            >
              Далее
            </Button>
          </div>
        </>
      )}
    </AdminLayout>
  )
}
