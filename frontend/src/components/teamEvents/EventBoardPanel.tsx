import { useState } from 'react'
import type { FormEvent } from 'react'
import { Button } from '../ui/Button'
import { CARD_CLASS } from '../ui/cardStyle'
import { EmptyState } from '../ui/EmptyState'
import { FormError } from '../ui/FormError'
import { Modal } from '../ui/Modal'
import { SelectField } from '../ui/SelectField'
import { TextField } from '../ui/TextField'
import { BoardPlanView } from './BoardPlanView'
import * as teamEventsApi from '../../api/teamEvents'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { formatMinutes, totalMinutes } from '../../utils/boardPlan'
import { DRILL_SECTION_PRESETS } from '../../types/teamEvent'
import type { TeamEventDrillRead, TeamEventDrillSectionRead, TeamEventRead } from '../../types/teamEvent'

interface EventBoardPanelProps {
  teamId: string
  event: TeamEventRead
  isCaptain: boolean
  onEventChange: (event: TeamEventRead) => void
}

interface DrillFormValues {
  sectionId: string
  title: string
  description: string
  minutes: string
}

const ICON_BUTTON_CLASS = 'text-[#8A94A6] transition-colors hover:text-[#F5F7FA] disabled:opacity-30'

function parseMinutes(value: string): number | null {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed > 0 ? Math.min(parsed, 180) : null
}

export function EventBoardPanel({ teamId, event, isCaptain, onEventChange }: EventBoardPanelProps) {
  const { accessToken } = useAuth()
  const [actionError, setActionError] = useState<string | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [isPublishing, setIsPublishing] = useState(false)
  const [sectionToDelete, setSectionToDelete] = useState<TeamEventDrillSectionRead | null>(null)

  async function refresh() {
    if (accessToken === null) {
      return
    }
    onEventChange(await teamEventsApi.getTeamEvent(teamId, event.id, accessToken))
  }

  // One mutation at a time: marks `key` busy, refreshes the event after,
  // and turns an API failure into the panel's error line.
  async function run(key: string, failure: string, action: (token: string) => Promise<unknown>): Promise<boolean> {
    if (accessToken === null) {
      return false
    }
    setBusyKey(key)
    setActionError(null)
    try {
      await action(accessToken)
      await refresh()
      return true
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : failure)
      return false
    } finally {
      setBusyKey(null)
    }
  }

  async function handlePublish() {
    if (accessToken === null) {
      return
    }
    setIsPublishing(true)
    setActionError(null)
    try {
      onEventChange(await teamEventsApi.publishBoard(teamId, event.id, accessToken))
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Не удалось опубликовать план.')
    } finally {
      setIsPublishing(false)
    }
  }

  if (!isCaptain) {
    if (event.sections === null) {
      return (
        <EmptyState
          icon="ti-clipboard-off"
          title="Тренер ещё готовит план"
          hint="Как только план будет опубликован, ты увидишь все упражнения."
        />
      )
    }
    return <BoardPlanView sections={event.sections} />
  }

  const sections = event.sections ?? []
  const sectionOptions = sections.map((section) => ({ value: section.id, label: section.name }))

  function moveSection(index: number, direction: -1 | 1) {
    const ids = sections.map((section) => section.id)
    const target = index + direction
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    return run(`section-${ids[target]}`, 'Не удалось изменить порядок.', (token) =>
      teamEventsApi.reorderSections(teamId, event.id, ids, token),
    )
  }

  function moveDrill(section: TeamEventDrillSectionRead, index: number, direction: -1 | 1) {
    const ids = section.drills.map((drill) => drill.id)
    const target = index + direction
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    return run(`drill-${ids[target]}`, 'Не удалось изменить порядок.', (token) =>
      teamEventsApi.reorderDrills(teamId, event.id, section.id, ids, token),
    )
  }

  function saveDrill(drillId: string | null, values: DrillFormValues) {
    const payload = {
      section_id: values.sectionId,
      title: values.title.trim(),
      description: values.description.trim() || null,
      duration_minutes: parseMinutes(values.minutes),
    }
    return drillId === null
      ? run(`add-${values.sectionId}`, 'Не удалось добавить упражнение.', (token) =>
          teamEventsApi.addDrill(teamId, event.id, payload, token),
        )
      : run(`drill-${drillId}`, 'Не удалось сохранить изменения.', (token) =>
          teamEventsApi.updateDrill(teamId, event.id, drillId, payload, token),
        )
  }

  const boardMinutes = totalMinutes(sections.flatMap((section) => section.drills))

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-medium uppercase tracking-wide ${
            event.board_status === 'published' ? 'bg-accent-ice/15 text-accent-ice' : 'bg-white/10 text-[#8A94A6]'
          }`}
        >
          {event.board_status === 'published' ? 'План опубликован' : 'Черновик -- видно только тебе'}
        </span>
        {event.board_status !== 'published' && (
          <Button type="button" onClick={handlePublish} isLoading={isPublishing} className="!px-3 !py-1.5 !text-xs">
            Опубликовать
          </Button>
        )}
      </div>
      {boardMinutes !== null && (
        <p className="text-sm text-[#8A94A6]">Всего по плану: {formatMinutes(boardMinutes)}</p>
      )}

      <FormError message={actionError} />

      {sections.length === 0 && (
        <EmptyState
          icon="ti-clipboard-list"
          title="Разбей тренировку на разделы"
          hint="Например: разминка, броски, игровые. Упражнения добавляются внутрь раздела."
        />
      )}

      {sections.map((section, index) => (
        <SectionEditor
          key={section.id}
          section={section}
          isFirst={index === 0}
          isLast={index === sections.length - 1}
          sectionOptions={sectionOptions}
          busyKey={busyKey}
          onMove={(direction) => moveSection(index, direction)}
          onRename={(name) =>
            run(`section-${section.id}`, 'Не удалось переименовать раздел.', (token) =>
              teamEventsApi.renameSection(teamId, event.id, section.id, name, token),
            )
          }
          onDelete={() => setSectionToDelete(section)}
          onMoveDrill={(drillIndex, direction) => moveDrill(section, drillIndex, direction)}
          onSaveDrill={saveDrill}
          onDeleteDrill={(drillId) =>
            run(`drill-${drillId}`, 'Не удалось удалить упражнение.', (token) =>
              teamEventsApi.deleteDrill(teamId, event.id, drillId, token),
            )
          }
        />
      ))}

      <AddSectionForm
        existingNames={sections.map((section) => section.name)}
        isBusy={busyKey === 'add-section'}
        onAdd={(name) =>
          run('add-section', 'Не удалось добавить раздел.', (token) =>
            teamEventsApi.addSection(teamId, event.id, name, token),
          )
        }
      />

      {sectionToDelete !== null && (
        <Modal title="Удалить раздел?" onClose={() => setSectionToDelete(null)}>
          <div className="flex flex-col gap-4">
            <p className="text-sm text-[#8A94A6]">
              «{sectionToDelete.name}»
              {sectionToDelete.drills.length > 0
                ? ` удалится вместе с упражнениями (${sectionToDelete.drills.length}).`
                : ' пустой — удалится только сам раздел.'}
            </p>
            <div className="flex gap-2">
              <Button variant="neutral" className="flex-1" onClick={() => setSectionToDelete(null)}>
                Отмена
              </Button>
              <Button
                className="flex-1"
                isLoading={busyKey === `section-${sectionToDelete.id}`}
                onClick={async () => {
                  const target = sectionToDelete
                  await run(`section-${target.id}`, 'Не удалось удалить раздел.', (token) =>
                    teamEventsApi.deleteSection(teamId, event.id, target.id, token),
                  )
                  setSectionToDelete(null)
                }}
              >
                Удалить
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

function SectionEditor({
  section,
  isFirst,
  isLast,
  sectionOptions,
  busyKey,
  onMove,
  onRename,
  onDelete,
  onMoveDrill,
  onSaveDrill,
  onDeleteDrill,
}: {
  section: TeamEventDrillSectionRead
  isFirst: boolean
  isLast: boolean
  sectionOptions: { value: string; label: string }[]
  busyKey: string | null
  onMove: (direction: -1 | 1) => Promise<boolean>
  onRename: (name: string) => Promise<boolean>
  onDelete: () => void
  onMoveDrill: (index: number, direction: -1 | 1) => Promise<boolean>
  onSaveDrill: (drillId: string | null, values: DrillFormValues) => Promise<boolean>
  onDeleteDrill: (drillId: string) => Promise<boolean>
}) {
  const [isRenaming, setIsRenaming] = useState(false)
  const [name, setName] = useState(section.name)
  const [isAdding, setIsAdding] = useState(false)
  const [editingDrillId, setEditingDrillId] = useState<string | null>(null)
  const busy = busyKey !== null
  const minutes = totalMinutes(section.drills)

  async function handleRename(e: FormEvent) {
    e.preventDefault()
    if (name.trim() === '') {
      return
    }
    if (await onRename(name.trim())) {
      setIsRenaming(false)
    }
  }

  return (
    <section className={`flex flex-col gap-3 p-3 ${CARD_CLASS}`}>
      {isRenaming ? (
        <form onSubmit={handleRename} className="flex items-end gap-2">
          <div className="flex-1">
            <TextField label="Название раздела" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          </div>
          <Button type="button" variant="neutral" className="!py-2 !text-xs" onClick={() => setIsRenaming(false)}>
            Отмена
          </Button>
          <Button type="submit" className="!py-2 !text-xs" isLoading={busyKey === `section-${section.id}`}>
            Ок
          </Button>
        </form>
      ) : (
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-semibold uppercase tracking-wide text-[#F5F7FA]">{section.name}</h3>
            <p className="text-xs text-[#5B6472]">
              {section.drills.length === 0 ? 'Пусто' : `Упражнений: ${section.drills.length}`}
              {minutes !== null && ` · ${formatMinutes(minutes)}`}
            </p>
          </div>
          <button type="button" disabled={isFirst || busy} onClick={() => onMove(-1)} aria-label="Раздел выше" className={ICON_BUTTON_CLASS}>
            <i className="ti ti-chevron-up" aria-hidden="true" />
          </button>
          <button type="button" disabled={isLast || busy} onClick={() => onMove(1)} aria-label="Раздел ниже" className={ICON_BUTTON_CLASS}>
            <i className="ti ti-chevron-down" aria-hidden="true" />
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setName(section.name)
              setIsRenaming(true)
            }}
            aria-label="Переименовать раздел"
            className={ICON_BUTTON_CLASS}
          >
            <i className="ti ti-pencil" aria-hidden="true" />
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onDelete}
            aria-label="Удалить раздел"
            className="text-[#8A94A6] transition-colors hover:text-red-400 disabled:opacity-30"
          >
            <i className="ti ti-trash" aria-hidden="true" />
          </button>
        </div>
      )}

      {section.drills.length > 0 && (
        <ul className="flex flex-col gap-2">
          {section.drills.map((drill, index) => (
            <li key={drill.id} className="rounded-lg border border-white/5 bg-white/[0.02] p-2.5">
              {editingDrillId === drill.id ? (
                <DrillForm
                  initial={{
                    sectionId: section.id,
                    title: drill.title,
                    description: drill.description ?? '',
                    minutes: drill.duration_minutes?.toString() ?? '',
                  }}
                  sectionOptions={sectionOptions}
                  submitLabel="Сохранить"
                  isBusy={busyKey === `drill-${drill.id}`}
                  onCancel={() => setEditingDrillId(null)}
                  onSubmit={async (values) => {
                    if (await onSaveDrill(drill.id, values)) {
                      setEditingDrillId(null)
                    }
                  }}
                />
              ) : (
                <DrillRow
                  drill={drill}
                  index={index}
                  isLast={index === section.drills.length - 1}
                  busy={busy}
                  onMove={(direction) => onMoveDrill(index, direction)}
                  onEdit={() => setEditingDrillId(drill.id)}
                  onDelete={() => onDeleteDrill(drill.id)}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      {isAdding ? (
        <DrillForm
          initial={{ sectionId: section.id, title: '', description: '', minutes: '' }}
          submitLabel="Добавить"
          isBusy={busyKey === `add-${section.id}`}
          onCancel={() => setIsAdding(false)}
          onSubmit={async (values) => {
            if (await onSaveDrill(null, values)) {
              setIsAdding(false)
            }
          }}
        />
      ) : (
        <button
          type="button"
          disabled={busy}
          onClick={() => setIsAdding(true)}
          className="flex items-center gap-1.5 self-start text-sm text-accent-ice transition-opacity hover:opacity-80 disabled:opacity-40"
        >
          <i className="ti ti-plus" aria-hidden="true" />
          Упражнение
        </button>
      )}
    </section>
  )
}

function DrillRow({
  drill,
  index,
  isLast,
  busy,
  onMove,
  onEdit,
  onDelete,
}: {
  drill: TeamEventDrillRead
  index: number
  isLast: boolean
  busy: boolean
  onMove: (direction: -1 | 1) => void
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="flex items-start gap-3">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs text-[#8A94A6]">
        {index + 1}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-medium text-[#F5F7FA]">
          {drill.title}
          {drill.duration_minutes !== null && (
            <span className="ml-2 text-xs font-normal text-[#8A94A6]">{formatMinutes(drill.duration_minutes)}</span>
          )}
        </span>
        {drill.description !== null && drill.description !== '' && (
          <span className="line-clamp-2 text-xs text-[#8A94A6]">{drill.description}</span>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <button type="button" disabled={index === 0 || busy} onClick={() => onMove(-1)} aria-label="Выше" className={ICON_BUTTON_CLASS}>
          <i className="ti ti-chevron-up" aria-hidden="true" />
        </button>
        <button type="button" disabled={isLast || busy} onClick={() => onMove(1)} aria-label="Ниже" className={ICON_BUTTON_CLASS}>
          <i className="ti ti-chevron-down" aria-hidden="true" />
        </button>
        <button type="button" disabled={busy} onClick={onEdit} aria-label="Редактировать" className={ICON_BUTTON_CLASS}>
          <i className="ti ti-pencil" aria-hidden="true" />
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onDelete}
          aria-label="Удалить"
          className="text-[#8A94A6] transition-colors hover:text-red-400 disabled:opacity-30"
        >
          <i className="ti ti-trash" aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

// Add and edit share one form; the section picker only shows when editing
// (moving a drill between sections) -- a new drill goes into the section
// whose "+ Упражнение" was tapped.
function DrillForm({
  initial,
  sectionOptions,
  submitLabel,
  isBusy,
  onCancel,
  onSubmit,
}: {
  initial: DrillFormValues
  sectionOptions?: { value: string; label: string }[]
  submitLabel: string
  isBusy: boolean
  onCancel: () => void
  onSubmit: (values: DrillFormValues) => void
}) {
  const [values, setValues] = useState(initial)

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (values.title.trim() !== '') {
      onSubmit(values)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <TextField
        label="Название"
        value={values.title}
        maxLength={200}
        onChange={(e) => setValues({ ...values, title: e.target.value })}
        placeholder="Например, розыгрыш 2 в 1"
        required
      />
      <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
        Что делать (необязательно)
        <textarea
          value={values.description}
          onChange={(e) => setValues({ ...values, description: e.target.value })}
          placeholder="Расстановка, задача, на что обратить внимание"
          className="min-h-20 w-full resize-y rounded border border-white/10 bg-dark-bg p-3 text-sm text-text-primary outline-none placeholder:text-text-secondary/60 focus:border-accent-ice"
        />
      </label>
      <div className="flex gap-2">
        <div className="w-28">
          <TextField
            label="Минут"
            numeric
            inputMode="numeric"
            value={values.minutes}
            onChange={(e) => setValues({ ...values, minutes: e.target.value.replace(/\D/g, '').slice(0, 3) })}
            placeholder="—"
          />
        </div>
        {sectionOptions !== undefined && sectionOptions.length > 1 && (
          <div className="min-w-0 flex-1">
            <SelectField
              label="Раздел"
              options={sectionOptions}
              value={values.sectionId}
              onChange={(e) => setValues({ ...values, sectionId: e.target.value })}
            />
          </div>
        )}
      </div>
      <div className="flex gap-2">
        <Button type="button" variant="neutral" className="flex-1 !py-1.5 !text-xs" onClick={onCancel}>
          Отмена
        </Button>
        <Button type="submit" isLoading={isBusy} disabled={values.title.trim() === ''} className="flex-1 !py-1.5 !text-xs">
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}

function AddSectionForm({
  existingNames,
  isBusy,
  onAdd,
}: {
  existingNames: string[]
  isBusy: boolean
  onAdd: (name: string) => Promise<boolean>
}) {
  const [customName, setCustomName] = useState('')
  const presets = DRILL_SECTION_PRESETS.filter((preset) => !existingNames.includes(preset))

  async function handleCustom(e: FormEvent) {
    e.preventDefault()
    if (customName.trim() !== '' && (await onAdd(customName.trim()))) {
      setCustomName('')
    }
  }

  return (
    <div className={`flex flex-col gap-3 p-3 ${CARD_CLASS}`}>
      <span className="text-xs font-medium uppercase tracking-wide text-[#8A94A6]">Добавить раздел</span>
      {presets.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {presets.map((preset) => (
            <button
              key={preset}
              type="button"
              disabled={isBusy}
              onClick={() => onAdd(preset)}
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-[#F5F7FA] transition-colors hover:border-accent-ice/50 disabled:opacity-40"
            >
              + {preset}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={handleCustom} className="flex items-end gap-2">
        <div className="flex-1">
          <TextField
            label="Своё название"
            value={customName}
            maxLength={100}
            onChange={(e) => setCustomName(e.target.value)}
            placeholder="Например, спецбригады"
          />
        </div>
        <Button type="submit" variant="neutral" isLoading={isBusy} disabled={customName.trim() === ''} className="!py-2">
          Добавить
        </Button>
      </form>
    </div>
  )
}
