import { useId, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Button } from '../ui/Button'
import { CardGlow } from '../ui/CardGlow'
import { CARD_CLASS } from '../ui/cardStyle'
import { EmptyState } from '../ui/EmptyState'
import { FormError } from '../ui/FormError'
import { Modal } from '../ui/Modal'
import { SelectField } from '../ui/SelectField'
import { TextField } from '../ui/TextField'
import { BoardPlanModal, BoardPlanView } from './BoardPlanView'
import { DrillTemplatePicker } from './DrillTemplatePicker'
import { DiagramEditor } from './diagram/DiagramEditor'
import { RinkDiagram } from './diagram/RinkDiagram'
import * as teamEventsApi from '../../api/teamEvents'
import { ApiError } from '../../api/client'
import { useAuth } from '../../hooks/useAuth'
import { useDrillTemplates } from '../../hooks/useDrillTemplates'
import { DRILL_SECTION_PRESETS } from '../../types/teamEvent'
import type { DrillTemplateRead, TeamEventDrillRead, TeamEventDrillSectionRead, TeamEventRead } from '../../types/teamEvent'
import { boardStats, formatMinutes, pluralRu, totalMinutes } from '../../utils/boardPlan'

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

// What the drill sheet is showing: a new drill for a section, or an
// existing one (looked up fresh from `event` on every render so it never
// shows stale data after a refresh).
type DrillSheet = { mode: 'create'; sectionId: string } | { mode: 'edit'; drillId: string } | null

interface FoundDrill {
  section: TeamEventDrillSectionRead
  drill: TeamEventDrillRead
  index: number
}

function parseMinutes(value: string): number | null {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) && parsed > 0 ? Math.min(parsed, 180) : null
}

function findDrill(sections: TeamEventDrillSectionRead[], drillId: string): FoundDrill | null {
  for (const section of sections) {
    const index = section.drills.findIndex((drill) => drill.id === drillId)
    if (index >= 0) {
      return { section, drill: section.drills[index], index }
    }
  }
  return null
}

export function EventBoardPanel({ teamId, event, isCaptain, onEventChange }: EventBoardPanelProps) {
  const { accessToken } = useAuth()
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [isPublishing, setIsPublishing] = useState(false)
  const [isPreview, setIsPreview] = useState(false)
  const [drillSheet, setDrillSheet] = useState<DrillSheet>(null)
  const [sectionMenuId, setSectionMenuId] = useState<string | null>(null)
  const [diagramDrillId, setDiagramDrillId] = useState<string | null>(null)

  async function refresh() {
    if (accessToken === null) {
      return
    }
    onEventChange(await teamEventsApi.getTeamEvent(teamId, event.id, accessToken))
  }

  // One mutation at a time: runs it, refreshes the event, and turns an API
  // failure into the panel's error line. Resolves to the action's result
  // (true for void actions), or undefined when it failed.
  async function run<T>(failure: string, action: (token: string) => Promise<T>): Promise<T | true | undefined> {
    if (accessToken === null) {
      return undefined
    }
    setBusy(true)
    setActionError(null)
    try {
      const result = await action(accessToken)
      await refresh()
      return result ?? true
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : failure)
      return undefined
    } finally {
      setBusy(false)
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
  const addSection = (name: string) =>
    run('Не удалось добавить раздел.', (token) => teamEventsApi.addSection(teamId, event.id, name, token))

  const editing = drillSheet?.mode === 'edit' ? findDrill(sections, drillSheet.drillId) : null
  const diagramTarget = diagramDrillId !== null ? findDrill(sections, diagramDrillId) : null
  const menuSectionIndex = sections.findIndex((section) => section.id === sectionMenuId)

  function saveDrill(values: DrillFormValues) {
    const payload = {
      section_id: values.sectionId,
      title: values.title.trim(),
      description: values.description.trim() || null,
      duration_minutes: parseMinutes(values.minutes),
    }
    if (drillSheet?.mode === 'edit') {
      const drillId = drillSheet.drillId
      return run('Не удалось сохранить упражнение.', (token) =>
        teamEventsApi.updateDrill(teamId, event.id, drillId, payload, token),
      )
    }
    return run('Не удалось добавить упражнение.', (token) => teamEventsApi.addDrill(teamId, event.id, payload, token))
  }

  function moveDrill(found: FoundDrill, direction: -1 | 1) {
    const ids = found.section.drills.map((drill) => drill.id)
    const target = found.index + direction
    ;[ids[found.index], ids[target]] = [ids[target], ids[found.index]]
    return run('Не удалось изменить порядок.', (token) =>
      teamEventsApi.reorderDrills(teamId, event.id, found.section.id, ids, token),
    )
  }

  function moveSection(index: number, direction: -1 | 1) {
    const ids = sections.map((section) => section.id)
    const target = index + direction
    ;[ids[index], ids[target]] = [ids[target], ids[index]]
    return run('Не удалось изменить порядок.', (token) => teamEventsApi.reorderSections(teamId, event.id, ids, token))
  }

  return (
    <div className="flex flex-col gap-4">
      <BoardHeader
        event={event}
        sections={sections}
        isPublishing={isPublishing}
        onPublish={handlePublish}
        onOpenPreview={() => setIsPreview(true)}
      />

      <FormError message={actionError} />

      {isPreview && (
        // The same modal the player opens from the home card -- an honest
        // preview, with the scheme right at the top of a tapped drill.
        <BoardPlanModal sections={sections} onClose={() => setIsPreview(false)} />
      )}

      <>
          {sections.length === 0 ? (
            <StartCard busy={busy} onAdd={addSection} />
          ) : (
            sections.map((section, index) => (
              <SectionBlock
                key={section.id}
                section={section}
                index={index}
                busy={busy}
                onOpenMenu={() => setSectionMenuId(section.id)}
                onOpenDrill={(drill) => setDrillSheet({ mode: 'edit', drillId: drill.id })}
                onDrawDiagram={(drill) => setDiagramDrillId(drill.id)}
                onAddDrill={() => setDrillSheet({ mode: 'create', sectionId: section.id })}
              />
            ))
          )}

          {sections.length > 0 && (
            <AddSectionCard existingNames={sections.map((section) => section.name)} busy={busy} onAdd={addSection} />
          )}
      </>

      {drillSheet !== null && (drillSheet.mode === 'create' || editing !== null) && (
        <DrillSheetModal
          key={drillSheet.mode === 'edit' ? drillSheet.drillId : `new-${drillSheet.sectionId}`}
          editing={editing}
          initialSectionId={drillSheet.mode === 'create' ? drillSheet.sectionId : (editing?.section.id ?? '')}
          sectionOptions={sectionOptions}
          busy={busy}
          onClose={() => setDrillSheet(null)}
          onPickTemplate={async (template, sectionId) => {
            const added = await run('Не удалось добавить упражнение из шаблона.', (token) =>
              teamEventsApi.addDrill(
                teamId,
                event.id,
                {
                  section_id: sectionId,
                  title: template.title,
                  description: template.description,
                  duration_minutes: template.duration_minutes,
                  diagram: template.diagram,
                },
                token,
              ),
            )
            if (added !== undefined) {
              setDrillSheet(null)
            }
          }}
          onSaveTemplate={async (values) => {
            if (accessToken === null || editing === null) {
              return false
            }
            await teamEventsApi.createDrillTemplate(
              {
                title: values.title.trim() || editing.drill.title,
                description: values.description.trim() || null,
                duration_minutes: parseMinutes(values.minutes),
                diagram: editing.drill.diagram,
              },
              accessToken,
            )
            return true
          }}
          onSave={async (values, thenDraw) => {
            const saved = await saveDrill(values)
            if (saved !== undefined) {
              setDrillSheet(null)
              if (thenDraw && saved !== true) {
                setDiagramDrillId(saved.id)
              }
            }
          }}
          onDrawDiagram={() => {
            if (editing !== null) {
              setDrillSheet(null)
              setDiagramDrillId(editing.drill.id)
            }
          }}
          onMove={(direction) => {
            if (editing !== null) {
              void moveDrill(editing, direction)
            }
          }}
          onDelete={async () => {
            if (editing === null) {
              return
            }
            const drillId = editing.drill.id
            const ok = await run('Не удалось удалить упражнение.', (token) =>
              teamEventsApi.deleteDrill(teamId, event.id, drillId, token),
            )
            if (ok !== undefined) {
              setDrillSheet(null)
            }
          }}
        />
      )}

      {menuSectionIndex >= 0 && (
        <SectionMenuModal
          key={sections[menuSectionIndex].id}
          section={sections[menuSectionIndex]}
          isFirst={menuSectionIndex === 0}
          isLast={menuSectionIndex === sections.length - 1}
          busy={busy}
          onClose={() => setSectionMenuId(null)}
          onRename={async (name) => {
            const sectionId = sections[menuSectionIndex].id
            const ok = await run('Не удалось переименовать раздел.', (token) =>
              teamEventsApi.renameSection(teamId, event.id, sectionId, name, token),
            )
            if (ok !== undefined) {
              setSectionMenuId(null)
            }
          }}
          onMove={(direction) => void moveSection(menuSectionIndex, direction)}
          onDelete={async () => {
            const sectionId = sections[menuSectionIndex].id
            await run('Не удалось удалить раздел.', (token) =>
              teamEventsApi.deleteSection(teamId, event.id, sectionId, token),
            )
            setSectionMenuId(null)
          }}
        />
      )}

      {diagramTarget !== null && (
        <DiagramEditor
          title={diagramTarget.drill.title}
          initial={diagramTarget.drill.diagram}
          onClose={() => setDiagramDrillId(null)}
          onSave={async (diagram) => {
            if (accessToken === null) {
              return
            }
            // Throws on failure -- DiagramEditor shows its own error and
            // stays open so nothing drawn is lost.
            await teamEventsApi.setDrillDiagram(teamId, event.id, diagramTarget.drill.id, diagram, accessToken)
            await refresh()
          }}
        />
      )}
    </div>
  )
}

function BoardHeader({
  event,
  sections,
  isPublishing,
  onPublish,
  onOpenPreview,
}: {
  event: TeamEventRead
  sections: TeamEventDrillSectionRead[]
  isPublishing: boolean
  onPublish: () => void
  onOpenPreview: () => void
}) {
  const stats = boardStats(sections)
  const isPublished = event.board_status === 'published'
  const items: { value: string; label: string }[] = [
    { value: String(stats.sections), label: pluralRu(stats.sections, ['раздел', 'раздела', 'разделов']) },
    { value: String(stats.drills), label: pluralRu(stats.drills, ['упражнение', 'упражнения', 'упражнений']) },
    { value: stats.minutes !== null ? String(stats.minutes) : '—', label: 'минут' },
  ]
  return (
    <section className={`relative flex flex-col gap-4 overflow-hidden p-4 ${CARD_CLASS}`}>
      <CardGlow />
      <div className="relative flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-[#F5F7FA]">План тренировки</h2>
          <p className="mt-0.5 text-xs text-[#8A94A6]">
            {isPublished ? 'Опубликован — команда видит план' : 'Черновик — команда пока не видит'}
          </p>
        </div>
        <span
          className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${
            isPublished ? 'bg-accent-ice/15 text-accent-ice' : 'bg-[#FFCF5C]/15 text-[#FFCF5C]'
          }`}
        >
          {isPublished ? 'Опубликован' : 'Черновик'}
        </span>
      </div>

      <dl className="relative grid grid-cols-3 gap-2">
        {items.map((item) => (
          <div key={item.label} className="flex flex-col-reverse rounded-xl bg-white/[0.04] px-3 py-2">
            <dt className="text-[11px] text-[#8A94A6]">{item.label}</dt>
            <dd className="font-display text-xl font-bold leading-tight text-[#F5F7FA]">{item.value}</dd>
          </div>
        ))}
      </dl>

      <div className="relative flex flex-col gap-2 sm:flex-row">
        {!isPublished && (
          <Button onClick={onPublish} isLoading={isPublishing} disabled={stats.drills === 0} className="w-full sm:flex-1">
            Опубликовать для команды
          </Button>
        )}
        {stats.drills > 0 && (
          <Button variant="neutral" onClick={onOpenPreview} className="w-full sm:flex-1">
            Как видит игрок
          </Button>
        )}
      </div>
      {!isPublished && stats.drills === 0 && (
        <p className="relative -mt-2 text-xs text-[#8A94A6]">Добавь хотя бы одно упражнение, чтобы опубликовать.</p>
      )}
    </section>
  )
}

function StartCard({ busy, onAdd }: { busy: boolean; onAdd: (name: string) => Promise<unknown> }) {
  return (
    <section className={`flex flex-col gap-4 p-5 ${CARD_CLASS}`}>
      <div className="flex flex-col items-center gap-2 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-ice/10">
          <i className="ti ti-layout-list text-2xl text-accent-ice" aria-hidden="true" />
        </span>
        <h3 className="text-base font-semibold text-[#F5F7FA]">Собери тренировку из разделов</h3>
        <p className="max-w-xs text-sm text-[#8A94A6]">
          Выбери первый раздел — например, разминку. Упражнения и схемы добавляются внутрь раздела.
        </p>
      </div>
      <SectionPresetPicker existingNames={[]} busy={busy} onAdd={onAdd} />
    </section>
  )
}

function AddSectionCard({
  existingNames,
  busy,
  onAdd,
}: {
  existingNames: string[]
  busy: boolean
  onAdd: (name: string) => Promise<unknown>
}) {
  return (
    <section className="flex flex-col gap-3 rounded-2xl border border-dashed border-white/15 p-4">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">Добавить раздел</h3>
      <SectionPresetPicker existingNames={existingNames} busy={busy} onAdd={onAdd} />
    </section>
  )
}

function SectionPresetPicker({
  existingNames,
  busy,
  onAdd,
}: {
  existingNames: string[]
  busy: boolean
  onAdd: (name: string) => Promise<unknown>
}) {
  const [customName, setCustomName] = useState('')
  const presets = DRILL_SECTION_PRESETS.filter((preset) => !existingNames.includes(preset))

  async function handleCustom(e: FormEvent) {
    e.preventDefault()
    if (customName.trim() !== '' && (await onAdd(customName.trim())) !== undefined) {
      setCustomName('')
    }
  }

  return (
    <div className="flex flex-col gap-3">
      {presets.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {presets.map((preset) => (
            <button
              key={preset}
              type="button"
              disabled={busy}
              onClick={() => onAdd(preset)}
              className="flex min-h-11 items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-4 text-sm text-[#F5F7FA] transition-colors hover:border-accent-ice/50 hover:bg-accent-ice/10 disabled:opacity-40"
            >
              <i className="ti ti-plus text-accent-ice" aria-hidden="true" />
              {preset}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={handleCustom} className="flex items-end gap-2">
        <div className="min-w-0 flex-1">
          <TextField
            label="Или своё название"
            value={customName}
            maxLength={100}
            onChange={(e) => setCustomName(e.target.value)}
            placeholder="Например, спецбригады"
          />
        </div>
        <Button type="submit" variant="neutral" disabled={busy || customName.trim() === ''} className="!min-h-[42px]">
          Добавить
        </Button>
      </form>
    </div>
  )
}

function SectionBlock({
  section,
  index,
  busy,
  onOpenMenu,
  onOpenDrill,
  onDrawDiagram,
  onAddDrill,
}: {
  section: TeamEventDrillSectionRead
  index: number
  busy: boolean
  onOpenMenu: () => void
  onOpenDrill: (drill: TeamEventDrillRead) => void
  onDrawDiagram: (drill: TeamEventDrillRead) => void
  onAddDrill: () => void
}) {
  const minutes = totalMinutes(section.drills)
  const count = section.drills.length
  return (
    <section className={`flex flex-col gap-3 p-3 ${CARD_CLASS}`} aria-label={`Раздел ${section.name}`}>
      <div className="flex items-center gap-3 pl-1">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-ice/15 text-xs font-bold text-accent-ice">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-[#F5F7FA]">{section.name}</h3>
          <p className="text-xs text-[#8A94A6]">
            {count === 0 ? 'Пока пусто' : `${count} ${pluralRu(count, ['упражнение', 'упражнения', 'упражнений'])}`}
            {minutes !== null && ` · ${formatMinutes(minutes)}`}
          </p>
        </div>
        <button
          type="button"
          disabled={busy}
          onClick={onOpenMenu}
          aria-label={`Действия с разделом ${section.name}`}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-[#8A94A6] transition-colors hover:bg-white/5 hover:text-[#F5F7FA] disabled:opacity-40"
        >
          <i className="ti ti-dots-vertical text-lg" aria-hidden="true" />
        </button>
      </div>

      {count > 0 && (
        <ul className="flex flex-col gap-2">
          {section.drills.map((drill, drillIndex) => (
            <li key={drill.id}>
              <DrillCard
                drill={drill}
                index={drillIndex}
                onOpen={() => onOpenDrill(drill)}
                onDrawDiagram={() => onDrawDiagram(drill)}
              />
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        disabled={busy}
        onClick={onAddDrill}
        className="flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-dashed border-white/15 text-sm text-accent-ice transition-colors hover:border-accent-ice/50 hover:bg-accent-ice/5 disabled:opacity-40"
      >
        <i className="ti ti-plus" aria-hidden="true" />
        Добавить упражнение
      </button>
    </section>
  )
}

function DrillCard({
  drill,
  index,
  onOpen,
  onDrawDiagram,
}: {
  drill: TeamEventDrillRead
  index: number
  onOpen: () => void
  onDrawDiagram: () => void
}) {
  const meta = [
    drill.duration_minutes !== null ? formatMinutes(drill.duration_minutes) : null,
    drill.description !== null && drill.description !== '' ? drill.description : null,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <div className="flex items-stretch gap-1 rounded-xl border border-white/5 bg-white/[0.03] transition-colors hover:border-white/15">
      <button
        type="button"
        onClick={onOpen}
        aria-label={`Упражнение ${drill.title}`}
        className="flex min-h-14 min-w-0 flex-1 items-center gap-3 py-2.5 pl-3 text-left"
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs text-[#8A94A6]">
          {index + 1}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-sm font-medium text-[#F5F7FA]">{drill.title}</span>
          <span className="truncate text-xs text-[#8A94A6]">{meta || 'Нажми, чтобы добавить описание и минуты'}</span>
        </span>
      </button>
      <button
        type="button"
        onClick={onDrawDiagram}
        aria-label={drill.diagram !== null ? `Изменить схему: ${drill.title}` : `Нарисовать схему: ${drill.title}`}
        className="m-1.5 flex w-12 shrink-0 flex-col items-center justify-center gap-0.5 overflow-hidden rounded-lg border border-white/10 bg-[#0B0F14]/60 transition-colors hover:border-accent-ice/50"
      >
        {drill.diagram !== null ? (
          <RinkDiagram diagram={drill.diagram} className="h-[60px] w-auto" />
        ) : (
          <>
            <i className="ti ti-route text-base text-accent-ice" aria-hidden="true" />
            <span className="text-[9px] leading-tight text-[#8A94A6]">схема</span>
          </>
        )}
      </button>
    </div>
  )
}

function DrillSheetModal({
  editing,
  initialSectionId,
  sectionOptions,
  busy,
  onClose,
  onPickTemplate,
  onSaveTemplate,
  onSave,
  onDrawDiagram,
  onMove,
  onDelete,
}: {
  editing: FoundDrill | null
  initialSectionId: string
  sectionOptions: { value: string; label: string }[]
  busy: boolean
  onClose: () => void
  onPickTemplate: (template: DrillTemplateRead, sectionId: string) => void
  // Throws on failure; resolves once the template is saved.
  onSaveTemplate: (values: DrillFormValues) => Promise<boolean>
  onSave: (values: DrillFormValues, thenDraw: boolean) => void
  onDrawDiagram: () => void
  onMove: (direction: -1 | 1) => void
  onDelete: () => void
}) {
  const drill = editing?.drill ?? null
  const [values, setValues] = useState<DrillFormValues>({
    sectionId: initialSectionId,
    title: drill?.title ?? '',
    description: drill?.description ?? '',
    minutes: drill?.duration_minutes?.toString() ?? '',
  })
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [titleError, setTitleError] = useState<string | null>(null)
  const titleId = useId()
  // New drill: the coach's templates, one tap away.
  const [templates, setTemplates] = useDrillTemplates()
  const [isPickingTemplate, setIsPickingTemplate] = useState(false)
  const [templateState, setTemplateState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [templateError, setTemplateError] = useState<string | null>(null)

  async function saveAsTemplate() {
    setTemplateState('saving')
    setTemplateError(null)
    try {
      await onSaveTemplate(values)
      setTemplateState('saved')
    } catch (err) {
      setTemplateState('error')
      setTemplateError(err instanceof ApiError ? err.message : 'Не удалось сохранить шаблон.')
    }
  }

  // The buttons stay tappable with an empty title -- a greyed-out button
  // that silently does nothing reads as broken; say what's missing instead.
  function trySave(thenDraw: boolean) {
    if (busy) {
      return
    }
    if (values.title.trim() === '') {
      setTitleError('Сначала напиши название упражнения')
      document.getElementById(titleId)?.focus()
      return
    }
    onSave(values, thenDraw)
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    trySave(false)
  }

  return (
    <Modal title={drill === null ? (isPickingTemplate ? 'Мои шаблоны' : 'Новое упражнение') : 'Упражнение'} onClose={onClose}>
      {drill === null && isPickingTemplate && templates !== null ? (
        <DrillTemplatePicker
          templates={templates}
          onTemplatesChange={setTemplates}
          busy={busy}
          onPick={(template) => onPickTemplate(template, values.sectionId)}
          onBack={() => setIsPickingTemplate(false)}
        />
      ) : (
      <form onSubmit={submit} className="flex flex-col gap-3">
        {drill === null && templates !== null && templates.length > 0 && (
          <button
            type="button"
            onClick={() => setIsPickingTemplate(true)}
            className="flex min-h-11 items-center gap-3 rounded-xl border border-accent-ice/30 bg-accent-ice/10 px-3 text-left text-sm text-[#F5F7FA] transition-colors hover:bg-accent-ice/15"
          >
            <i className="ti ti-bookmarks text-accent-ice" aria-hidden="true" />
            <span className="flex-1">Взять из моих шаблонов</span>
            <span className="text-xs text-[#8A94A6]">{templates.length}</span>
            <i className="ti ti-chevron-right text-[#8A94A6]" aria-hidden="true" />
          </button>
        )}
        <div className="flex flex-col gap-1">
          <TextField
            id={titleId}
            label="Название"
            value={values.title}
            maxLength={200}
            onChange={(e) => {
              setValues({ ...values, title: e.target.value })
              setTitleError(null)
            }}
            placeholder="Например, розыгрыш 2 в 1"
            aria-invalid={titleError !== null}
            aria-describedby={titleError !== null ? `${titleId}-error` : undefined}
            className={titleError !== null ? '!border-red-400' : ''}
          />
          {titleError !== null && (
            <p id={`${titleId}-error`} role="alert" className="text-xs text-red-400">
              {titleError}
            </p>
          )}
        </div>
        <label className="flex flex-col gap-1.5 text-sm text-text-secondary">
          Что делать
          <textarea
            value={values.description}
            onChange={(e) => setValues({ ...values, description: e.target.value })}
            placeholder="Расстановка, задача, на что обратить внимание"
            className="min-h-24 w-full resize-y rounded border border-white/10 bg-dark-bg p-3 text-sm text-text-primary outline-none placeholder:text-text-secondary/60 focus:border-accent-ice"
          />
        </label>
        <div className="flex gap-2">
          <div className="w-24 shrink-0">
            <TextField
              label="Минут"
              numeric
              inputMode="numeric"
              value={values.minutes}
              onChange={(e) => setValues({ ...values, minutes: e.target.value.replace(/\D/g, '').slice(0, 3) })}
              placeholder="—"
            />
          </div>
          {sectionOptions.length > 1 && (
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

        {drill !== null && <SchemeBlock drill={drill} onDraw={onDrawDiagram} />}

        <Button type="submit" isLoading={busy} className="w-full">
          {drill === null ? 'Добавить' : 'Сохранить'}
        </Button>
        {drill === null && (
          <Button type="button" variant="neutral" disabled={busy} onClick={() => trySave(true)} className="w-full">
            Добавить и нарисовать схему
          </Button>
        )}

        {editing !== null && (
          <div className="flex flex-col gap-2 border-t border-white/5 pt-3">
            <SheetAction
              icon={templateState === 'saved' ? 'ti-check' : 'ti-bookmark'}
              label={
                templateState === 'saved' ? 'Сохранено в мои шаблоны' : templateState === 'saving' ? 'Сохраняю…' : 'Сохранить как шаблон'
              }
              disabled={busy || templateState === 'saving' || templateState === 'saved'}
              onClick={() => void saveAsTemplate()}
            />
            <FormError message={templateError} />
            <div className="grid grid-cols-2 gap-2">
              <SheetAction icon="ti-arrow-up" label="Выше" disabled={busy || editing.index === 0} onClick={() => onMove(-1)} />
              <SheetAction
                icon="ti-arrow-down"
                label="Ниже"
                disabled={busy || editing.index === editing.section.drills.length - 1}
                onClick={() => onMove(1)}
              />
            </div>
            {confirmDelete ? (
              <div className="flex gap-2">
                <Button type="button" variant="neutral" className="flex-1" onClick={() => setConfirmDelete(false)}>
                  Не удалять
                </Button>
                <Button type="button" className="flex-1 !bg-red-500/90 hover:!bg-red-500" isLoading={busy} onClick={onDelete}>
                  Удалить
                </Button>
              </div>
            ) : (
              <SheetAction icon="ti-trash" label="Удалить упражнение" danger disabled={busy} onClick={() => setConfirmDelete(true)} />
            )}
          </div>
        )}
      </form>
      )}
    </Modal>
  )
}

function SchemeBlock({ drill, onDraw }: { drill: TeamEventDrillRead; onDraw: () => void }) {
  return (
    <button
      type="button"
      onClick={onDraw}
      className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-2.5 text-left transition-colors hover:border-accent-ice/50"
    >
      <span className="flex h-[72px] w-10 shrink-0 items-center justify-center overflow-hidden rounded-md bg-[#0B0F14]/60">
        {drill.diagram !== null ? (
          <RinkDiagram diagram={drill.diagram} className="h-[72px] w-auto" />
        ) : (
          <i className="ti ti-route text-xl text-accent-ice" aria-hidden="true" />
        )}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-sm font-medium text-[#F5F7FA]">
          {drill.diagram !== null ? 'Схема на площадке' : 'Нарисовать схему'}
        </span>
        <span className="text-xs text-[#8A94A6]">
          {drill.diagram !== null ? 'Нажми, чтобы изменить' : 'Игроки, стрелки паса и ката'}
        </span>
      </span>
      <i className="ti ti-chevron-right text-[#8A94A6]" aria-hidden="true" />
    </button>
  )
}

function SheetAction({
  icon,
  label,
  onClick,
  disabled = false,
  danger = false,
}: {
  icon: string
  label: string
  onClick: () => void
  disabled?: boolean
  danger?: boolean
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex min-h-11 items-center justify-center gap-2 rounded-xl border border-white/10 px-3 text-sm transition-colors disabled:opacity-40 ${
        danger ? 'text-red-400 hover:border-red-400/40 hover:bg-red-500/10' : 'text-[#F5F7FA] hover:bg-white/5'
      }`}
    >
      <i className={`ti ${icon}`} aria-hidden="true" />
      {label}
    </button>
  )
}

function SectionMenuModal({
  section,
  isFirst,
  isLast,
  busy,
  onClose,
  onRename,
  onMove,
  onDelete,
}: {
  section: TeamEventDrillSectionRead
  isFirst: boolean
  isLast: boolean
  busy: boolean
  onClose: () => void
  onRename: (name: string) => void
  onMove: (direction: -1 | 1) => void
  onDelete: () => void
}) {
  const [name, setName] = useState(section.name)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const drillCount = section.drills.length

  let deleteBlock: ReactNode
  if (confirmDelete) {
    deleteBlock = (
      <div className="flex flex-col gap-2 rounded-xl border border-red-400/30 bg-red-500/5 p-3">
        <p className="text-sm text-[#F5F7FA]">
          {drillCount > 0
            ? `Раздел удалится вместе с ${drillCount} ${pluralRu(drillCount, ['упражнением', 'упражнениями', 'упражнениями'])}.`
            : 'Раздел пустой — удалится только он сам.'}
        </p>
        <div className="flex gap-2">
          <Button type="button" variant="neutral" className="flex-1" onClick={() => setConfirmDelete(false)}>
            Не удалять
          </Button>
          <Button type="button" className="flex-1 !bg-red-500/90 hover:!bg-red-500" isLoading={busy} onClick={onDelete}>
            Удалить
          </Button>
        </div>
      </div>
    )
  } else {
    deleteBlock = (
      <SheetAction icon="ti-trash" label="Удалить раздел" danger disabled={busy} onClick={() => setConfirmDelete(true)} />
    )
  }

  return (
    <Modal title={`Раздел «${section.name}»`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (name.trim() !== '' && name.trim() !== section.name) {
              onRename(name.trim())
            }
          }}
          className="flex items-end gap-2"
        >
          <div className="min-w-0 flex-1">
            <TextField label="Название" value={name} maxLength={100} onChange={(e) => setName(e.target.value)} />
          </div>
          <Button
            type="submit"
            variant="neutral"
            disabled={busy || name.trim() === '' || name.trim() === section.name}
            className="!min-h-[42px]"
          >
            Сохранить
          </Button>
        </form>
        <div className="grid grid-cols-2 gap-2">
          <SheetAction icon="ti-arrow-up" label="Выше" disabled={busy || isFirst} onClick={() => onMove(-1)} />
          <SheetAction icon="ti-arrow-down" label="Ниже" disabled={busy || isLast} onClick={() => onMove(1)} />
        </div>
        {deleteBlock}
      </div>
    </Modal>
  )
}
