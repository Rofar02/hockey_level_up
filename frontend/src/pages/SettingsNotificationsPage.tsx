import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { SelectField } from '../components/ui/SelectField'
import { Switch } from '../components/ui/Switch'
import * as pushApi from '../api/push'
import * as usersApi from '../api/users'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import { getActivePushSubscription, isIos, isPushSupported, isStandalone, subscribeToPush } from '../push'
import { REMINDER_PREFERENCE_LABELS } from '../types/user'
import type { ReminderPreference } from '../types/user'

export function SettingsNotificationsPage() {
  const { user, accessToken, updateUser } = useAuth()

  const [pushSupported] = useState(() => isPushSupported())
  // Unsupported for the fixable reason (iOS Safari, not installed to the
  // home screen) vs. every other unsupported case, which has no fix to
  // point the user at -- see push.ts for why standalone gates PushManager.
  const [needsIosHomeScreenInstall] = useState(
    () => !isPushSupported() && isIos() && !isStandalone(),
  )
  const [pushPermission, setPushPermission] = useState<NotificationPermission | null>(() =>
    isPushSupported() ? Notification.permission : null,
  )
  const [pushSubscribed, setPushSubscribed] = useState(false)
  const [pushStatusChecked, setPushStatusChecked] = useState(false)
  const [isPushBusy, setIsPushBusy] = useState(false)
  const [pushError, setPushError] = useState<string | null>(null)
  const [isSendingTestPush, setIsSendingTestPush] = useState(false)
  const [testPushSuccess, setTestPushSuccess] = useState(false)
  const [reminderPreference, setReminderPreference] = useState<Exclude<ReminderPreference, 'none'>>(
    user?.reminder_preference !== undefined && user.reminder_preference !== 'none'
      ? user.reminder_preference
      : 'morning',
  )

  useEffect(() => {
    if (!pushSupported) {
      return
    }
    // The server has no record of "is this browser currently subscribed" --
    // permission can be revoked from OS/browser settings behind the app's
    // back, so the only trustworthy source is the browser's own state.
    let cancelled = false
    getActivePushSubscription()
      .then((subscription) => {
        if (!cancelled) {
          setPushSubscribed(subscription !== null)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setPushStatusChecked(true)
        }
      })
    return () => {
      cancelled = true
    }
  }, [pushSupported])

  async function handlePushToggle() {
    if (accessToken === null || isPushBusy) {
      return
    }
    setPushError(null)
    setTestPushSuccess(false)
    setIsPushBusy(true)
    try {
      if (pushSubscribed) {
        const subscription = await getActivePushSubscription()
        if (subscription !== null) {
          await pushApi.deletePushSubscription(subscription.endpoint, accessToken)
          await subscription.unsubscribe()
        }
        setPushSubscribed(false)
        try {
          const updated = await usersApi.updateProfile(
            { reminder_preference: 'none' },
            accessToken,
          )
          updateUser(updated)
        } catch {
          // Best-effort -- the browser subscription is already gone either
          // way, so a stale server-side preference is harmless until the
          // next successful save.
        }
        return
      }

      if (Notification.permission === 'denied') {
        setPushError('Уведомления заблокированы в настройках браузера.')
        return
      }
      const permission = await Notification.requestPermission()
      setPushPermission(permission)
      if (permission !== 'granted') {
        setPushError('Уведомления заблокированы в настройках браузера.')
        return
      }

      const { public_key: vapidPublicKey } = await pushApi.getVapidPublicKey(accessToken)
      const subscription = await subscribeToPush(vapidPublicKey)
      const json = subscription.toJSON()
      if (json.endpoint === undefined || json.keys === undefined) {
        throw new Error('Некорректная push-подписка браузера.')
      }
      await pushApi.savePushSubscription(
        { endpoint: json.endpoint, keys: { p256dh: json.keys.p256dh, auth: json.keys.auth } },
        accessToken,
      )
      const updated = await usersApi.updateProfile(
        {
          reminder_preference: reminderPreference,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        },
        accessToken,
      )
      updateUser(updated)
      setPushSubscribed(true)
    } catch (err) {
      setPushError(
        err instanceof ApiError ? err.message : 'Не удалось изменить настройку уведомлений.',
      )
    } finally {
      setIsPushBusy(false)
    }
  }

  async function handleReminderPreferenceChange(value: Exclude<ReminderPreference, 'none'>) {
    if (accessToken === null || value === reminderPreference) {
      return
    }
    const previous = reminderPreference
    setReminderPreference(value)
    setPushError(null)
    try {
      const updated = await usersApi.updateProfile({ reminder_preference: value }, accessToken)
      updateUser(updated)
    } catch (err) {
      setReminderPreference(previous)
      setPushError(err instanceof ApiError ? err.message : 'Не удалось сохранить выбор.')
    }
  }

  async function handleSendTestPush() {
    if (accessToken === null) {
      return
    }
    setPushError(null)
    setTestPushSuccess(false)
    setIsSendingTestPush(true)
    try {
      await pushApi.sendTestPushNotification(accessToken)
      setTestPushSuccess(true)
    } catch (err) {
      setPushError(
        err instanceof ApiError ? err.message : 'Не удалось отправить тестовое уведомление.',
      )
    } finally {
      setIsSendingTestPush(false)
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink to="/settings" />
          <h1 className="text-xl font-semibold">Уведомления</h1>
        </div>

        {!pushSupported && needsIosHomeScreenInstall && (
          <p className="text-sm text-text-secondary">
            Добавьте приложение на домашний экран (Поделиться → «На экран «Домой»»), чтобы получать
            уведомления.
          </p>
        )}
        {!pushSupported && !needsIosHomeScreenInstall && (
          <p className="text-sm text-text-secondary">
            Этот браузер не поддерживает push-уведомления.
          </p>
        )}
        {pushSupported && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="font-medium text-text-primary">Напоминания о тренировках</p>
                <p className="text-sm text-text-secondary">Push-уведомления в этом браузере</p>
              </div>
              <Switch
                checked={pushSubscribed}
                disabled={isPushBusy || !pushStatusChecked}
                onClick={handlePushToggle}
              />
            </div>
            {pushPermission === 'denied' && (
              <p className="text-sm text-text-secondary">
                Уведомления заблокированы в настройках браузера.
              </p>
            )}
            <FormError message={pushError} />
            {pushSubscribed && (
              <>
                <SelectField
                  label="Когда напоминать"
                  value={reminderPreference}
                  onChange={(event) =>
                    handleReminderPreferenceChange(
                      event.target.value as Exclude<ReminderPreference, 'none'>,
                    )
                  }
                  options={Object.entries(REMINDER_PREFERENCE_LABELS).map(([value, label]) => ({
                    value,
                    label,
                  }))}
                />
                <Button
                  variant="neutral"
                  onClick={handleSendTestPush}
                  isLoading={isSendingTestPush}
                  className="self-start"
                >
                  Отправить тестовое уведомление
                </Button>
                {testPushSuccess && (
                  <p className="text-sm text-accent-ice">Уведомление отправлено.</p>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
