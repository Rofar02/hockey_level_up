import type { Position } from './user'

export const TEAM_EVENT_TYPES = ['training', 'game'] as const
export type TeamEventType = (typeof TEAM_EVENT_TYPES)[number]

export const TEAM_EVENT_STATUSES = ['scheduled', 'cancelled'] as const
export type TeamEventStatus = (typeof TEAM_EVENT_STATUSES)[number]

export const TEAM_EVENT_PUBLISH_STATUSES = ['draft', 'published'] as const
export type TeamEventPublishStatus = (typeof TEAM_EVENT_PUBLISH_STATUSES)[number]

export const TEAM_EVENT_ATTENDANCE_STATUSES = ['going', 'not_going'] as const
export type TeamEventAttendanceStatus = (typeof TEAM_EVENT_ATTENDANCE_STATUSES)[number]

export const TEAM_EVENT_ABSENCE_REASONS = ['work', 'injury', 'study', 'other'] as const
export type TeamEventAbsenceReason = (typeof TEAM_EVENT_ABSENCE_REASONS)[number]

export interface TeamEventDrillRead {
  id: string
  section_id: string
  order: number
  title: string
  description: string | null
  duration_minutes: number | null
}

// A named block of the board -- the coach names it freely; these are just
// the one-tap suggestions the editor offers.
export interface TeamEventDrillSectionRead {
  id: string
  order: number
  name: string
  drills: TeamEventDrillRead[]
}

export const DRILL_SECTION_PRESETS = ['Разминка', 'Катание', 'Броски', 'Игровые', 'Заминка'] as const

// GET/POST /teams/{team_id}/events -- sections is null while the board is a
// draft and the caller isn't the captain (event exists, content hidden),
// [] once published with nothing on it yet. GAME events always have
// board_status=null/sections=null -- games have no board.
export interface TeamEventRead {
  id: string
  team_id: string
  event_type: TeamEventType
  status: TeamEventStatus
  starts_at: string
  opponent_name: string | null
  board_status: TeamEventPublishStatus | null
  sections: TeamEventDrillSectionRead[] | null
  created_at: string
}

export interface TeamEventCreatePayload {
  event_type: TeamEventType
  starts_at: string
  opponent_name?: string | null
}

export interface TeamEventReschedulePayload {
  starts_at: string
}

export interface TeamEventDrillCreatePayload {
  section_id: string
  title: string
  description?: string | null
  duration_minutes?: number | null
}

// A different section_id moves the drill to the end of that section.
export interface TeamEventDrillUpdatePayload {
  section_id: string
  title: string
  description?: string | null
  duration_minutes?: number | null
}

export interface TeamEventAttendanceSetPayload {
  status: TeamEventAttendanceStatus
  reason?: TeamEventAbsenceReason | null
  reason_note?: string | null
}

export interface TeamEventAttendanceRead {
  status: TeamEventAttendanceStatus
  reason: TeamEventAbsenceReason | null
  reason_note: string | null
  responded_at: string
}

export interface TeamEventAttendanceMemberRead {
  user_id: string
  first_name: string
  last_name: string
  avatar_url: string | null
  reason: TeamEventAbsenceReason | null
  reason_note: string | null
  responded_at: string | null
}

export interface TeamEventAttendanceRosterRead {
  is_locked: boolean
  going: TeamEventAttendanceMemberRead[]
  not_going: TeamEventAttendanceMemberRead[]
  unmarked: TeamEventAttendanceMemberRead[]
}

export interface TeamEventNudgeResult {
  notified_count: number
  last_nudge_sent_at: string
}

export interface TeamEventLineupPlayerRead {
  user_id: string
  first_name: string
  last_name: string
  avatar_url: string | null
  position: Position | null
}

export interface TeamEventLineupGroupRead {
  id: string
  name: string | null
  color: string | null
  players: TeamEventLineupPlayerRead[]
}

// groups/unassigned are null while the lineup is a draft and the caller
// isn't the captain -- same visibility contract as TeamEventRead.drills.
export interface TeamEventLineupRead {
  lineup_status: TeamEventPublishStatus
  groups: TeamEventLineupGroupRead[] | null
  unassigned: TeamEventLineupPlayerRead[] | null
}

export interface TeamEventLineupGroupCreatePayload {
  name?: string | null
  color?: string | null
}

export interface TeamEventLineupGroupUpdatePayload {
  name?: string | null
  color?: string | null
}

export interface TeamEventDiaryEntryRead {
  note: string | null
  created_at: string
  updated_at: string
}

export interface TeamEventDiaryEntrySavePayload {
  note?: string | null
}

export interface TeamIceScheduleTemplateRead {
  id: string
  weekday: number
  start_time: string
  active: boolean
}

export interface TeamIceScheduleTemplateCreatePayload {
  weekday: number
  start_time: string
}
