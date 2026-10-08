import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import * as friendsApi from '../../api/friends'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { friendRequestErrorText, takePendingFriendCode } from '../../utils/pendingFriendInvite'

// Sends the request from an invite link opened before logging in, once
// the player is in, and says so in a strip at the top.
export function PendingFriendInvite() {
  const { accessToken } = useAuth()
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    const code = takePendingFriendCode()
    if (code === null) {
      return
    }
    friendsApi
      .sendFriendRequest({ code }, accessToken)
      .then((sent) =>
        setMessage(
          sent.status === 'accepted'
            ? `Вы теперь друзья с ${sent.receiver_first_name} ${sent.receiver_last_name}`
            : `Заявка отправлена: ${sent.receiver_first_name} ${sent.receiver_last_name}`,
        ),
      )
      .catch((err: unknown) => {
        if (err instanceof ApiError) {
          setMessage(friendRequestErrorText(err.message))
        }
      })
  }, [accessToken])

  if (message === null) {
    return null
  }
  return (
    <div
      role="status"
      className="fixed inset-x-3 top-[calc(env(safe-area-inset-top,0px)+12px)] z-50 mx-auto flex max-w-md items-center gap-3 rounded-xl border border-accent-ice/30 bg-dark-card px-4 py-3 text-sm shadow-lg"
    >
      <i className="ti ti-user-plus text-lg text-accent-ice" aria-hidden="true" />
      <span className="min-w-0 flex-1">{message}</span>
      <Link to="/friends" onClick={() => setMessage(null)} className="shrink-0 font-medium text-accent-ice">
        Друзья
      </Link>
      <button
        type="button"
        onClick={() => setMessage(null)}
        aria-label="Закрыть"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-text-secondary hover:text-text-primary"
      >
        <i className="ti ti-x" aria-hidden="true" />
      </button>
    </div>
  )
}
