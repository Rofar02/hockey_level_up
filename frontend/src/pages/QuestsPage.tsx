import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { Button } from '../components/ui/Button'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { Modal } from '../components/ui/Modal'
import * as authApi from '../api/auth'
import * as questsApi from '../api/quests'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { CoachTaskRead, QuestStatusRead, QuestType } from '../types/quest'
import { QUEST_TYPE_LABELS } from '../types/quest'

const GROUP_ORDER: QuestType[] = ['weekly', 'long_term', 'one_time']

const GROUP_LABELS: Record<QuestType, string> = {
  weekly: 'На этой неделе',
  long_term: 'Долгосрочные',
  one_time: 'Разовые',
}

function groupByType(quests: QuestStatusRead[]): { type: QuestType; quests: QuestStatusRead[] }[] {
  return GROUP_ORDER.map((type) => ({ type, quests: quests.filter((q) => q.type === type) })).filter(
    (group) => group.quests.length > 0,
  )
}

export function QuestsPage() {
  const { accessToken, updateUser } = useAuth()

  const [quests, setQuests] = useState<QuestStatusRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [selectedQuest, setSelectedQuest] = useState<QuestStatusRead | null>(null)
  const [claimingId, setClaimingId] = useState<string | null>(null)
  const [claimError, setClaimError] = useState<string | null>(null)
  const [coachTasks, setCoachTasks] = useState<CoachTaskRead[] | null>(null)

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    questsApi
      .getCoachTasks(accessToken)
      .then((result) => {
        if (!cancelled) {
          setCoachTasks(result)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function handleClaimTask(task: CoachTaskRead) {
    if (accessToken === null) {
      return
    }
    setClaimingId(task.id)
    setClaimError(null)
    try {
      const updated = await questsApi.claimCoachTask(task.id, accessToken)
      setCoachTasks((prev) => prev?.map((t) => (t.id === updated.id ? updated : t)) ?? prev)
      updateUser(await authApi.getCurrentUser(accessToken))
    } catch (err: unknown) {
      setClaimError(err instanceof ApiError ? err.message : 'Не удалось получить награду.')
    } finally {
      setClaimingId(null)
    }
  }

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    questsApi
      .getQuestStatus(accessToken)
      .then((result) => {
        if (!cancelled) {
          setQuests(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить задания.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  async function handleClaim(quest: QuestStatusRead) {
    if (accessToken === null) {
      return
    }
    setClaimingId(quest.id)
    setClaimError(null)
    try {
      const updated = await questsApi.claimQuest(quest.id, accessToken)
      setQuests((prev) => prev?.map((q) => (q.id === updated.id ? updated : q)) ?? prev)
      setSelectedQuest(updated)
      // The XP/level shown in the header and on Home come from AuthContext's
      // cached user, not a fresh fetch -- without this, claiming a quest
      // here would only show up after a full page reload.
      const freshUser = await authApi.getCurrentUser(accessToken)
      updateUser(freshUser)
    } catch (err: unknown) {
      setClaimError(err instanceof ApiError ? err.message : 'Не удалось получить награду.')
    } finally {
      setClaimingId(null)
    }
  }

  const groups = quests !== null ? groupByType(quests) : null

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-6 px-4 py-8">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Задания</h1>
          <p className="text-sm text-[#8A94A6]">Выполняйте задания, чтобы получать дополнительный опыт.</p>
        </div>

        <FormError message={loadError} />
        {coachTasks !== null && coachTasks.length > 0 && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 px-1">
              <span className="h-px w-4 shrink-0 bg-accent-persimmon/70" aria-hidden="true" />
              <span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">От тренера на неделю</span>
              <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
            </div>
            {coachTasks.map((task) => (
              <div key={task.id} className={`flex flex-col gap-2 p-4 ${CARD_CLASS} ${task.claimed ? 'opacity-70' : ''}`}>
                <div className="flex items-start gap-3">
                  <i className="ti ti-whistle mt-0.5 text-lg text-accent-persimmon" aria-hidden="true" />
                  <span className="flex-1 text-sm font-medium text-[#F5F7FA]">{task.title}</span>
                  <span className="shrink-0 font-display text-sm text-[#8A94A6]">
                    {task.progress}/{task.target}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
                  <div
                    className="h-full rounded-full bg-accent-persimmon"
                    style={{ width: `${Math.round((100 * task.progress) / Math.max(task.target, 1))}%` }}
                  />
                </div>
                {task.claimed ? (
                  <span className="text-xs text-accent-ice">Награда получена</span>
                ) : task.done ? (
                  <Button
                    onClick={() => handleClaimTask(task)}
                    isLoading={claimingId === task.id}
                    className="self-start !px-3 !py-1.5 !text-xs"
                  >
                    Получить +{task.xp_reward} XP
                  </Button>
                ) : (
                  <span className="text-xs text-[#8A94A6]">+{task.xp_reward} XP за выполнение</span>
                )}
              </div>
            ))}
            <FormError message={claimError} />
          </div>
        )}
        {quests === null && loadError === null && <p className="text-sm text-[#8A94A6]">Загрузка...</p>}

        {quests !== null && quests.length === 0 && (
          <EmptyState icon="ti-target-arrow" title="Заданий пока нет" />
        )}

        {groups !== null && groups.length > 0 && (
          <div className="flex flex-col gap-6">
            {groups.map((group) => (
              <div key={group.type} className="flex flex-col gap-2">
                <div className="flex items-center gap-2 px-1">
                  <span className="h-px w-4 shrink-0 bg-accent-ice/60" aria-hidden="true" />
                  <span className="shrink-0 text-xs font-semibold uppercase tracking-wide text-[#8A94A6]">
                    {GROUP_LABELS[group.type]}
                  </span>
                  <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
                </div>
                <div className="flex flex-col gap-2">
                  {group.quests.map((quest) => (
                    <QuestCard
                      key={quest.id}
                      quest={quest}
                      onOpen={() => {
                        setClaimError(null)
                        setSelectedQuest(quest)
                      }}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {selectedQuest !== null && (
        <Modal title={selectedQuest.title} onClose={() => setSelectedQuest(null)}>
          <div className="flex flex-col gap-4">
            <span className="w-fit rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[#8A94A6]">
              {QUEST_TYPE_LABELS[selectedQuest.type]}
            </span>
            <p className="text-sm text-[#F5F7FA]">{selectedQuest.description}</p>
            <FormError message={claimError} />
            {selectedQuest.completed ? (
              <span className="flex items-center gap-1 self-start rounded-full bg-accent-ice/15 px-3 py-1 text-xs font-medium uppercase tracking-wide text-accent-ice">
                <i className="ti ti-check" aria-hidden="true" />
                Награда получена
              </span>
            ) : selectedQuest.claimable ? (
              <Button
                onClick={() => handleClaim(selectedQuest)}
                isLoading={claimingId === selectedQuest.id}
                className="w-full"
              >
                Получить +{selectedQuest.xp_reward} XP
              </Button>
            ) : (
              <p className="font-display text-sm font-semibold text-accent-persimmon">
                +{selectedQuest.xp_reward} XP за выполнение
              </p>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}

function QuestCard({ quest, onOpen }: { quest: QuestStatusRead; onOpen: () => void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={`group flex w-full items-center gap-3 p-4 text-left transition-colors hover:border-white/20 ${CARD_CLASS} ${quest.completed ? 'opacity-70' : ''}`}
    >
      <span
        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-md ${
          quest.completed ? 'bg-accent-ice/15' : 'bg-accent-persimmon/10'
        }`}
      >
        <i
          className={`ti ${quest.completed ? 'ti-check' : 'ti-target-arrow'} text-lg ${
            quest.completed ? 'text-accent-ice' : 'text-accent-persimmon'
          }`}
          aria-hidden="true"
        />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-sm font-medium text-[#F5F7FA]">{quest.title}</span>
        <span className="truncate text-xs text-[#8A94A6]">{quest.description}</span>
      </div>
      {quest.completed ? (
        <span className="flex shrink-0 items-center gap-1 rounded-full bg-accent-ice/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-ice">
          <i className="ti ti-check" aria-hidden="true" />
          Готово
        </span>
      ) : quest.claimable ? (
        <span className="flex shrink-0 items-center gap-1 rounded-full bg-accent-persimmon/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-accent-persimmon">
          Получить
        </span>
      ) : (
        <span className="font-display shrink-0 text-sm font-semibold text-accent-persimmon">
          +{quest.xp_reward} XP
        </span>
      )}
      <i
        className="ti ti-chevron-right shrink-0 text-lg text-[#8A94A6] transition-all group-hover:translate-x-0.5 group-hover:text-accent-ice"
        aria-hidden="true"
      />
    </button>
  )
}
