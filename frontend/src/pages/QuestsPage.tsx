import { useEffect, useState } from 'react'
import { BackLink } from '../components/ui/BackLink'
import { CARD_CLASS } from '../components/ui/cardStyle'
import { EmptyState } from '../components/ui/EmptyState'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import * as questsApi from '../api/quests'
import { ApiError } from '../api/client'
import { useAuth } from '../hooks/useAuth'
import type { QuestStatusRead, QuestType } from '../types/quest'

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
  const { accessToken } = useAuth()

  const [quests, setQuests] = useState<QuestStatusRead[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

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
                    <QuestCard key={quest.id} quest={quest} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function QuestCard({ quest }: { quest: QuestStatusRead }) {
  return (
    <div
      className={`flex items-center gap-3 p-4 ${CARD_CLASS} ${quest.completed ? 'opacity-70' : ''}`}
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
      ) : (
        <span className="font-display shrink-0 text-sm font-semibold text-accent-persimmon">
          +{quest.xp_reward} XP
        </span>
      )}
    </div>
  )
}
