import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import { TextField } from '../components/ui/TextField'
import * as authApi from '../api/auth'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { pendingCount, sendQueueNow } from '../utils/writeQueue'
import { getActivePushSubscription } from '../push'
import { pluralRu } from '../utils/boardPlan'

export function SettingsAccountPage() {
  const { user, accessToken, logout, adoptTokens } = useAuth()
  const navigate = useNavigate()

  const [showDeleteModal, setShowDeleteModal] = useState(false)
  const [deletePassword, setDeletePassword] = useState('')
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [isChangingPassword, setIsChangingPassword] = useState(false)
  const [passwordChanged, setPasswordChanged] = useState(false)

  const [showLogoutAllModal, setShowLogoutAllModal] = useState(false)
  const [logoutAllError, setLogoutAllError] = useState<string | null>(null)
  const [isLoggingOutAll, setIsLoggingOutAll] = useState(false)

  // Б2 review 14.10 (12): workout actions still waiting to be sent -- asked
  // about before signing out, since signing out drops them.
  const [unsentOnLogout, setUnsentOnLogout] = useState<number | null>(null)
  const [isSendingQueue, setIsSendingQueue] = useState(false)
  const [sendQueueFailed, setSendQueueFailed] = useState(false)
  // Which sign-out the «Не всё отправлено» question is about (15.10: «Выйти
  // на всех устройствах» used to drop the unsent actions without asking).
  const [unsentFor, setUnsentFor] = useState<'here' | 'everywhere'>('here')

  function openPasswordModal() {
    setCurrentPassword('')
    setNewPassword('')
    setPasswordError(null)
    setShowPasswordModal(true)
  }

  async function handleChangePassword(event: FormEvent) {
    event.preventDefault()
    if (accessToken === null) {
      return
    }
    setPasswordError(null)
    setIsChangingPassword(true)
    try {
      const subscription = await getActivePushSubscription().catch(() => null)
      const tokens = await authApi.changePassword(currentPassword, newPassword, accessToken, subscription?.endpoint ?? null)
      adoptTokens(tokens.access_token, tokens.refresh_token)
      setShowPasswordModal(false)
      setPasswordChanged(true)
    } catch (err) {
      setPasswordError(
        err instanceof ApiError ? err.message : 'Не удалось сменить пароль. Попробуйте ещё раз.',
      )
    } finally {
      setIsChangingPassword(false)
    }
  }

  function handleLogoutAll() {
    const unsent = pendingCount()
    if (unsent > 0) {
      setShowLogoutAllModal(false)
      setSendQueueFailed(false)
      setUnsentFor('everywhere')
      setUnsentOnLogout(unsent)
      return
    }
    void performLogoutAll()
  }

  async function performLogoutAll() {
    if (accessToken === null) {
      return
    }
    setLogoutAllError(null)
    setIsLoggingOutAll(true)
    try {
      await authApi.logoutAll(accessToken)
      logout()
      navigate('/login', { replace: true })
    } catch (err) {
      setLogoutAllError(
        err instanceof ApiError ? err.message : 'Не удалось выйти на всех устройствах. Попробуйте ещё раз.',
      )
      setIsLoggingOutAll(false)
      // Came here from the unsent question: back to the dialog that shows it.
      setUnsentOnLogout(null)
      setShowLogoutAllModal(true)
    }
  }

  function signOut() {
    logout()
    navigate('/login', { replace: true })
  }

  // After the unsent question: the sign-out the player asked for.
  function finishSignOut() {
    if (unsentFor === 'everywhere') {
      void performLogoutAll()
      return
    }
    signOut()
  }

  function handleLogout() {
    const unsent = pendingCount()
    if (unsent > 0) {
      setSendQueueFailed(false)
      setUnsentFor('here')
      setUnsentOnLogout(unsent)
      return
    }
    signOut()
  }

  async function sendThenSignOut() {
    setIsSendingQueue(true)
    setSendQueueFailed(false)
    const allSent = await sendQueueNow()
    setIsSendingQueue(false)
    if (allSent) {
      finishSignOut()
      return
    }
    setUnsentOnLogout(pendingCount())
    setSendQueueFailed(true)
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

        <section className="flex flex-col gap-3">
          <h2 className="flex items-center gap-2 text-sm font-medium text-[#8A94A6]">
            <i className="ti ti-shield-lock text-accent-ice" aria-hidden="true" />
            Безопасность
            <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
          </h2>
          <div className="flex flex-wrap gap-3">
            <Button variant="neutral" onClick={openPasswordModal}>
              Сменить пароль
            </Button>
            <Button
              variant="neutral"
              onClick={() => {
                setLogoutAllError(null)
                setShowLogoutAllModal(true)
              }}
            >
              Выйти на всех устройствах
            </Button>
          </div>
          {passwordChanged && (
            <p className="text-sm text-accent-ice">
              Пароль изменён. На других устройствах нужно войти заново.
            </p>
          )}
        </section>

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

      {showPasswordModal && (
        <Modal title="Сменить пароль" onClose={() => setShowPasswordModal(false)}>
          <form onSubmit={handleChangePassword} className="flex flex-col gap-4">
            <TextField
              label="Текущий пароль"
              name="current_password"
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
              required
            />
            <TextField
              label="Новый пароль"
              name="new_password"
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
              required
            />
            <p className="text-sm text-text-secondary">
              Не короче 8 символов. На других устройствах после смены нужно будет войти заново.
            </p>
            <FormError message={passwordError} />
            <div className="flex gap-3">
              <Button type="submit" isLoading={isChangingPassword}>
                Сменить пароль
              </Button>
              <Button
                type="button"
                variant="neutral"
                onClick={() => setShowPasswordModal(false)}
                disabled={isChangingPassword}
              >
                Отмена
              </Button>
            </div>
          </form>
        </Modal>
      )}

      {showLogoutAllModal && (
        <Modal title="Выйти на всех устройствах?" onClose={() => setShowLogoutAllModal(false)}>
          <div className="flex flex-col gap-4">
            <p className="text-sm text-text-secondary">
              Аккаунт закроется на всех телефонах и компьютерах, включая этот. Войти можно будет
              снова по паролю.
            </p>
            <FormError message={logoutAllError} />
            <div className="flex gap-3">
              <Button onClick={handleLogoutAll} isLoading={isLoggingOutAll}>
                Выйти везде
              </Button>
              <Button
                type="button"
                variant="neutral"
                onClick={() => setShowLogoutAllModal(false)}
                disabled={isLoggingOutAll}
              >
                Отмена
              </Button>
            </div>
          </div>
        </Modal>
      )}

      {unsentOnLogout !== null && (
        <Modal title="Не всё отправлено" onClose={() => setUnsentOnLogout(null)}>
          <div className="flex flex-col gap-4">
            <p className="text-sm text-text-secondary">
              {unsentOnLogout} {pluralRu(unsentOnLogout, ['действие', 'действия', 'действий'])} с тренировки ещё
              не {unsentOnLogout === 1 ? 'отправлено' : 'отправлены'} на сервер. Если выйти сейчас, они пропадут.
            </p>
            {sendQueueFailed && (
              <FormError message="Не получилось отправить — проверь связь и попробуй ещё раз." />
            )}
            <div className="flex flex-col gap-3 sm:flex-row">
              <Button onClick={() => void sendThenSignOut()} isLoading={isSendingQueue}>
                Отправить и выйти
              </Button>
              <Button
                type="button"
                variant="neutral"
                onClick={finishSignOut}
                disabled={isSendingQueue}
                isLoading={isLoggingOutAll}
              >
                Выйти без них
              </Button>
            </div>
          </div>
        </Modal>
      )}

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
