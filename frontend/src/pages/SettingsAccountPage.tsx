import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { TextField } from '../components/ui/TextField'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

export function SettingsAccountPage() {
  const { user, accessToken, logout } = useAuth()
  const navigate = useNavigate()

  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  function openDeleteModal() {
    setDeletePassword('')
    setDeleteError(null)
    setShowDeleteModal(true)
  }

  async function handleDeleteAccount(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null) {
      return
    }
    setDeleteError(null)
    setIsDeleting(true)
    try {
      await usersApi.deleteAccount(deletePassword, accessToken)
      logout()
      navigate('/login', { replace: true })
    } catch (err) {
      setDeleteError(
        err instanceof ApiError ? err.message : 'Не удалось удалить аккаунт. Попробуйте ещё раз.',
      )
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Аккаунт</h1>
        </div>

        {user?.is_admin === true && (
          <Link
            to="/admin"
            className="self-start rounded px-4 py-2.5 font-medium text-accent-ice transition-colors hover:underline"
          >
            Админ-панель
          </Link>
        )}

        <Button variant="neutral" onClick={handleLogout} className="self-start">
          Выйти из аккаунта
        </Button>

        <section className="flex flex-col gap-4">
          <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
            <i className="ti ti-alert-triangle text-accent-persimmon" aria-hidden="true" />
            Удаление аккаунта
            <span className="h-px flex-1 bg-accent-persimmon/20" aria-hidden="true" />
          </h2>
          <div className="flex flex-col gap-3 rounded-md border border-accent-persimmon/40 bg-accent-persimmon/10 p-4">
            <p className="text-sm text-[#F5F7FA]">
              Аккаунт и все связанные данные — тренировки, прогресс, статистика, навыки — будут
              удалены безвозвратно. Это действие нельзя отменить.
            </p>
            <Button
              variant="neutral"
              onClick={openDeleteModal}
              className="self-start border-accent-persimmon/60 text-accent-persimmon hover:bg-accent-persimmon/10"
            >
              Удалить аккаунт
            </Button>
          </div>
        </section>
      </div>

      {showDeleteModal && (
        <Modal title="Удалить аккаунт?" onClose={() => setShowDeleteModal(false)}>
          <form onSubmit={handleDeleteAccount} className="flex flex-col gap-4">
            <p className="text-sm text-text-secondary">
              Это действие необратимо. Введите пароль, чтобы подтвердить удаление аккаунта и
              всех связанных данных.
            </p>
            <TextField
              label="Пароль"
              name="delete_password"
              type="password"
              autoComplete="current-password"
              value={deletePassword}
              onChange={(event) => setDeletePassword(event.target.value)}
              required
            />
            <FormError message={deleteError} />
            <div className="flex gap-3">
              <Button type="submit" isLoading={isDeleting}>
                Удалить аккаунт
              </Button>
              <Button
                type="button"
                variant="neutral"
                onClick={() => setShowDeleteModal(false)}
                disabled={isDeleting}
              >
                Отмена
              </Button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  )
}
