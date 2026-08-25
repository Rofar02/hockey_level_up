import { useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ShieldIcon } from '../components/ui/ShieldIcon'
import * as authApi from '../api/auth'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'

type Status = 'checking' | 'success' | 'error' | 'missing-token'

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token')
  const { accessToken, updateUser } = useAuth()

  const [status, setStatus] = useState<Status>(token === null ? 'missing-token' : 'checking')
  const [message, setMessage] = useState<string | null>(null)
  // StrictMode/re-render guard -- confirming the same token twice would hit
  // the backend's single-use check and surface a spurious "already used".
  const hasConfirmed = useRef(false)

  useEffect(() => {
    if (token === null || hasConfirmed.current) {
      return
    }
    hasConfirmed.current = true

    authApi
      .confirmEmailVerification(token)
      .then((result) => {
        setStatus('success')
        setMessage(result.detail)
        // Best-effort only -- if nobody's logged in here (a different
        // device/browser than where the account was created), there's
        // nothing to refresh, and that's fine.
        if (accessToken !== null) {
          authApi.getCurrentUser(accessToken).then(updateUser).catch(() => {})
        }
      })
      .catch((err: unknown) => {
        setStatus('error')
        setMessage(err instanceof ApiError ? err.message : 'Не удалось подтвердить email.')
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  return (
    <div className="relative flex min-h-svh items-center justify-center overflow-hidden px-4">
      <div className="absolute inset-0 bg-[url('/images/arena-bg.webp')] bg-cover bg-center" />
      <div className="absolute inset-0 bg-dark-bg/80" />
      <Card className="relative w-full max-w-sm text-center">
        {status === 'checking' && (
          <>
            <h1 className="mb-2 flex items-center justify-center gap-2 text-xl font-semibold">
              <ShieldIcon />
              Подтверждаем email...
            </h1>
            <p className="text-sm text-text-secondary">Это займёт пару секунд.</p>
          </>
        )}
        {status === 'missing-token' && (
          <>
            <h1 className="mb-2 flex items-center justify-center gap-2 text-xl font-semibold">
              <ShieldIcon />
              Ссылка неполная
            </h1>
            <p className="text-sm text-text-secondary">
              В ссылке нет кода подтверждения. Откройте ссылку из письма ещё раз.
            </p>
          </>
        )}
        {status === 'success' && (
          <>
            <i className="ti ti-circle-check-filled mb-3 block text-3xl text-accent-ice" aria-hidden="true" />
            <h1 className="mb-2 text-xl font-semibold">Email подтверждён</h1>
            <p className="text-sm text-text-secondary">{message}</p>
          </>
        )}
        {status === 'error' && (
          <>
            <i className="ti ti-alert-circle mb-3 block text-3xl text-red-400" aria-hidden="true" />
            <h1 className="mb-2 text-xl font-semibold">Не получилось подтвердить</h1>
            <p className="text-sm text-text-secondary">{message}</p>
          </>
        )}
        <Link to="/" className="mt-6 block">
          <Button type="button" className="w-full">
            На главную
          </Button>
        </Link>
      </Card>
    </div>
  )
}
