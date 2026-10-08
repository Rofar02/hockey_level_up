import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import * as friendsApi from '../api/friends'
import { ApiError } from '../api/client'
import { PublicPlayerCard } from '../components/PublicPlayerCard'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { useAuth } from '../hooks/useAuth'
import type { UserPublicRead } from '../types/user'
import { friendRequestErrorText, savePendingFriendCode } from '../utils/pendingFriendInvite'

// /f/:code -- a friend's invite link (2026-10-08). Open to anyone: their
// player card and one button. Logged in, it sends the request; not yet, the
// code waits until the account exists (PendingFriendInvite sends it).
export function InvitePage() {
  const { code = '' } = useParams<{ code: string }>()
  const navigate = useNavigate()
  const { user, accessToken, isAuthenticated, isInitializing } = useAuth()
  const [inviter, setInviter] = useState<UserPublicRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isSending, setIsSending] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    friendsApi
      .getInvite(code)
      .then((found) => {
        if (!cancelled) {
          setInviter(found)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось открыть приглашение.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [code])

  async function add() {
    if (accessToken === null) {
      return
    }
    setSendError(null)
    setIsSending(true)
    try {
      const sent = await friendsApi.sendFriendRequest({ code }, accessToken)
      setResult(
        sent.status === 'accepted'
          ? `Вы теперь друзья с ${sent.receiver_first_name}`
          : `Заявка отправлена — ${sent.receiver_first_name} останется её принять`,
      )
    } catch (err) {
      setSendError(err instanceof ApiError ? friendRequestErrorText(err.message) : 'Не удалось отправить заявку.')
    } finally {
      setIsSending(false)
    }
  }

  function goWithAccount(path: '/register' | '/login') {
    savePendingFriendCode(code)
    navigate(path)
  }

  const isOwnLink = user !== null && inviter !== null && user.id === inviter.id

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex min-h-svh max-w-md flex-col items-center gap-5 px-4 pb-8 pt-10">
        <span className="font-display text-[15px] font-bold uppercase tracking-[2px] text-accent-ice">IceLevel</span>
        <FormError message={loadError} />
        {inviter === null && loadError === null && <p className="text-sm text-text-secondary">Загрузка...</p>}

        {inviter !== null && (
          <>
            <h1 className="text-balance text-center text-xl font-semibold">
              {isOwnLink
                ? 'Это твоя ссылка — отправь её другу'
                : `${inviter.first_name} ${inviter.last_name} зовёт тебя в друзья`}
            </h1>
            <div className="w-full max-w-[340px]">
              <PublicPlayerCard profile={inviter} />
            </div>

            <div className="mt-auto flex w-full flex-col gap-2.5">
              {isInitializing ? null : isOwnLink ? (
                <Link to="/friends" className="text-center text-sm font-medium text-accent-ice">
                  К друзьям
                </Link>
              ) : isAuthenticated ? (
                result !== null ? (
                  <>
                    <p className="text-center text-sm text-accent-ice">{result}</p>
                    <Link to="/friends" className="text-center text-sm font-medium text-text-secondary">
                      К друзьям
                    </Link>
                  </>
                ) : (
                  <>
                    <Button type="button" onClick={() => void add()} isLoading={isSending} className="w-full">
                      Добавить в друзья
                    </Button>
                    <FormError message={sendError} />
                  </>
                )
              ) : (
                <>
                  <Button type="button" onClick={() => goWithAccount('/register')} className="w-full">
                    Создать аккаунт и добавить
                  </Button>
                  <Button type="button" variant="neutral" onClick={() => goWithAccount('/login')} className="w-full">
                    У меня есть аккаунт — войти
                  </Button>
                  <p className="text-center text-xs leading-relaxed text-text-secondary">
                    После входа заявка отправится сама — {inviter.first_name} останется её принять.
                  </p>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
