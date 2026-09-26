import { useState } from 'react'
import { Button } from '../ui/Button'
import { FormError } from '../ui/FormError'
import { TextField } from '../ui/TextField'
import { RinkDiagram } from './diagram/RinkDiagram'
import * as teamEventsApi from '../../api/teamEvents'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { formatMinutes } from '../../utils/boardPlan'
import type { DrillTemplateRead } from '../../types/teamEvent'

// "Мои шаблоны" inside the new-drill sheet: tap one to put a copy on the
// board; rename or delete from the row's own menu.
export function DrillTemplatePicker({
  templates,
  onTemplatesChange,
  busy,
  onPick,
  onBack,
}: {
  templates: DrillTemplateRead[]
  onTemplatesChange: (templates: DrillTemplateRead[]) => void
  busy: boolean
  onPick: (template: DrillTemplateRead) => void
  onBack: () => void
}) {
  const { accessToken } = useAuth()
  const [openId, setOpenId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [working, setWorking] = useState(false)

  async function act(failure: string, action: (token: string) => Promise<void>) {
    if (accessToken === null) {
      return
    }
    setWorking(true)
    setError(null)
    try {
      await action(accessToken)
      setOpenId(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : failure)
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-1 self-start text-sm text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
      >
        <i className="ti ti-chevron-left" aria-hidden="true" />
        Новое упражнение
      </button>
      <FormError message={error} />
      {templates.length === 0 ? (
        <p className="rounded-xl border border-dashed border-white/15 p-4 text-sm text-[#8A94A6]">
          Шаблонов пока нет. Открой любое упражнение и нажми «Сохранить как шаблон».
        </p>
      ) : (
        <ul className="flex flex-col gap-2" aria-label="Мои шаблоны">
          {templates.map((template) => (
            <li key={template.id} className="rounded-xl border border-white/10 bg-white/[0.03]">
              <div className="flex items-stretch">
                <button
                  type="button"
                  disabled={busy || working}
                  onClick={() => onPick(template)}
                  aria-label={`Взять шаблон ${template.title}`}
                  className="flex min-h-14 min-w-0 flex-1 items-center gap-3 p-2.5 text-left disabled:opacity-50"
                >
                  <span className="flex h-[60px] w-9 shrink-0 items-center justify-center overflow-hidden rounded-md bg-[#0B0F14]/60">
                    {template.diagram !== null ? (
                      <RinkDiagram diagram={template.diagram} className="h-[60px] w-auto" />
                    ) : (
                      <i className="ti ti-clipboard-text text-base text-[#5B6472]" aria-hidden="true" />
                    )}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="line-clamp-2 text-sm font-medium text-[#F5F7FA]">{template.title}</span>
                    <span className="truncate text-xs text-[#8A94A6]">
                      {[
                        template.duration_minutes !== null ? formatMinutes(template.duration_minutes) : null,
                        template.diagram !== null ? 'схема' : null,
                        template.description || null,
                      ]
                        .filter(Boolean)
                        .join(' · ') || 'Без описания'}
                    </span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setOpenId(openId === template.id ? null : template.id)}
                  aria-label={`Действия с шаблоном ${template.title}`}
                  aria-expanded={openId === template.id}
                  className="flex w-11 shrink-0 items-center justify-center text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
                >
                  <i className="ti ti-dots-vertical" aria-hidden="true" />
                </button>
              </div>
              {openId === template.id && (
                <TemplateActions
                  key={template.id}
                  template={template}
                  working={working}
                  onRename={(title) =>
                    act('Не удалось переименовать шаблон.', async (token) => {
                      const renamed = await teamEventsApi.renameDrillTemplate(template.id, title, token)
                      onTemplatesChange([renamed, ...templates.filter((candidate) => candidate.id !== template.id)])
                    })
                  }
                  onDelete={() =>
                    act('Не удалось удалить шаблон.', async (token) => {
                      await teamEventsApi.deleteDrillTemplate(template.id, token)
                      onTemplatesChange(templates.filter((candidate) => candidate.id !== template.id))
                    })
                  }
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function TemplateActions({
  template,
  working,
  onRename,
  onDelete,
}: {
  template: DrillTemplateRead
  working: boolean
  onRename: (title: string) => void
  onDelete: () => void
}) {
  const [title, setTitle] = useState(template.title)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const trimmed = title.trim()
  return (
    <div className="flex flex-col gap-2 border-t border-white/5 p-2.5">
      <div className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <TextField label="Название шаблона" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <Button
          type="button"
          variant="neutral"
          disabled={working || trimmed === '' || trimmed === template.title}
          onClick={() => onRename(trimmed)}
        >
          Переименовать
        </Button>
      </div>
      {confirmDelete ? (
        <div className="flex gap-2">
          <Button type="button" variant="neutral" className="flex-1" onClick={() => setConfirmDelete(false)}>
            Оставить
          </Button>
          <Button type="button" className="flex-1 !bg-red-500/90 hover:!bg-red-500" isLoading={working} onClick={onDelete}>
            Удалить шаблон
          </Button>
        </div>
      ) : (
        <button
          type="button"
          disabled={working}
          onClick={() => setConfirmDelete(true)}
          className="flex min-h-11 items-center justify-center gap-2 rounded-xl border border-white/10 text-sm text-red-400 transition-colors hover:border-red-400/40 hover:bg-red-500/10 disabled:opacity-40"
        >
          <i className="ti ti-trash" aria-hidden="true" />
          Удалить шаблон
        </button>
      )}
    </div>
  )
}
