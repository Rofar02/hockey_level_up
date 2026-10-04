import { useEffect, useState } from 'react'
import * as feedbackApi from '../../api/feedback'
import { AdminLayout } from '../../components/admin/AdminLayout'
import { FormError } from '../../components/ui/FormError'
import { Modal } from '../../components/ui/Modal'
import { useAuth } from '../../hooks/useAuth'
import { FEEDBACK_KIND_LABELS, FEEDBACK_STATUS_LABELS } from '../../types/feedback'
import type { FeedbackAdminRead, FeedbackStatus } from '../../types/feedback'

// Player feedback (2026-10-04): bug reports, ideas, messages -- newest
// first, with the page trail / device context and an optional screenshot.

const FILTERS: { value: FeedbackStatus | null; label: string }[] = [
  { value: 'new', label: 'Новые' },
  { value: 'seen', label: 'Прочитанные' },
  { value: 'done', label: 'Сделано' },
  { value: null, label: 'Все' },
]

const KIND_STYLES: Record<FeedbackAdminRead['kind'], string> = {
  bug: 'bg-accent-persimmon/15 text-[#FF8A6B]',
  idea: 'bg-accent-ice/15 text-accent-ice',
  other: 'bg-white/10 text-text-secondary',
}

export function AdminFeedbackPage() {
  const { accessToken } = useAuth()
  const [filter, setFilter] = useState<FeedbackStatus | null>('new')
  const [items, setItems] = useState<FeedbackAdminRead[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    setItems(null)
    feedbackApi
      .listFeedbackAdmin(filter, accessToken)
      .then((result) => !cancelled && setItems(result))
      .catch(() => !cancelled && setError('Не удалось загрузить обратную связь.'))
    return () => {
      cancelled = true
    }
  }, [accessToken, filter])

  useEffect(() => {
    return () => {
      if (screenshotUrl !== null) {
        URL.revokeObjectURL(screenshotUrl)
      }
    }
  }, [screenshotUrl])

  async function changeStatus(item: FeedbackAdminRead, status: FeedbackStatus) {
    if (accessToken === null) {
      return
    }
    try {
      await feedbackApi.setFeedbackStatus(item.id, status, accessToken)
      setItems((current) =>
        (current ?? [])
          .map((entry) => (entry.id === item.id ? { ...entry, status } : entry))
          .filter((entry) => filter === null || entry.status === filter),
      )
    } catch {
      setError('Не удалось поменять статус.')
    }
  }

  async function openScreenshot(item: FeedbackAdminRead) {
    if (accessToken === null) {
      return
    }
    try {
      const blob = await feedbackApi.fetchFeedbackScreenshot(item.id, accessToken)
      setScreenshotUrl(URL.createObjectURL(blob))
    } catch {
      setError('Не удалось загрузить скриншот.')
    }
  }

  return (
    <AdminLayout title="Обратная связь">
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((option) => (
          <button
            key={option.label}
            type="button"
            onClick={() => setFilter(option.value)}
            className={`min-h-9 rounded-full border px-3 text-sm transition-colors ${
              filter === option.value ? 'border-accent-ice bg-accent-ice/10 text-accent-ice' : 'border-white/10 text-text-secondary'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <FormError message={error} />

      {items === null ? (
        <p className="text-sm text-text-secondary">Загрузка…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-text-secondary">Здесь пока пусто.</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((item) => (
            <li key={item.id} className="flex flex-col gap-3 rounded-md border border-white/10 bg-dark-card p-4">
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className={`rounded px-2 py-0.5 font-semibold ${KIND_STYLES[item.kind]}`}>
                  {FEEDBACK_KIND_LABELS[item.kind]}
                </span>
                <span className="text-text-secondary">
                  {new Date(item.created_at).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })}
                </span>
                <span className="text-text-secondary">·</span>
                <span className="text-text-secondary">
                  {item.user_name || '—'} ({item.user_email})
                </span>
                <span className="ml-auto text-text-secondary">{FEEDBACK_STATUS_LABELS[item.status]}</span>
              </div>
              <p className="whitespace-pre-wrap text-sm leading-relaxed">{item.text}</p>
              <dl className="grid grid-cols-[auto,1fr] gap-x-3 gap-y-1 text-xs text-text-secondary">
                <dt>Экраны</dt>
                <dd className="break-all">{String(item.context.page ?? '—')}</dd>
                <dt>Устройство</dt>
                <dd className="break-all">{String(item.context.user_agent ?? '—')}</dd>
                <dt>Экран</dt>
                <dd>
                  {String(item.context.screen ?? '—')}
                  {item.context.standalone === true ? ' · с главного экрана' : ''}
                </dd>
                <dt>Игрок</dt>
                <dd>
                  уровень {String(item.context.level ?? '—')}
                  {item.context.premium === true ? ' · премиум' : ''}
                </dd>
              </dl>
              <div className="flex flex-wrap gap-2">
                {item.has_screenshot && (
                  <button
                    type="button"
                    onClick={() => void openScreenshot(item)}
                    className="min-h-9 rounded border border-white/15 px-3 text-sm hover:bg-white/5"
                  >
                    <i className="ti ti-photo mr-1" aria-hidden="true" />
                    Скриншот
                  </button>
                )}
                {(['new', 'seen', 'done'] as FeedbackStatus[])
                  .filter((status) => status !== item.status)
                  .map((status) => (
                    <button
                      key={status}
                      type="button"
                      onClick={() => void changeStatus(item, status)}
                      className="min-h-9 rounded border border-white/15 px-3 text-sm hover:bg-white/5"
                    >
                      {FEEDBACK_STATUS_LABELS[status]}
                    </button>
                  ))}
              </div>
            </li>
          ))}
        </ul>
      )}

      {screenshotUrl !== null && (
        <Modal title="Скриншот" onClose={() => setScreenshotUrl(null)}>
          <img src={screenshotUrl} alt="Скриншот от игрока" className="w-full rounded" />
        </Modal>
      )}
    </AdminLayout>
  )
}
