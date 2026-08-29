export const QUEST_TYPES = ['one_time', 'weekly', 'long_term'] as const
export type QuestType = (typeof QUEST_TYPES)[number]

export const QUEST_TYPE_LABELS: Record<QuestType, string> = {
  one_time: 'Разовое',
  weekly: 'Недельное',
  long_term: 'Долгосрочное',
}

export interface QuestStatusRead {
  id: string
  type: QuestType
  title: string
  description: string
  xp_reward: number
  completed: boolean
  // Set for weekly/long_term (the Monday the current period is tracked
  // under), null for one_time -- see app/schemas/quest.py.
  period_start: string | null
}
