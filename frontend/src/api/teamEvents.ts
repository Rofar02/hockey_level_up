import {
  apiDeleteAuth,
  apiGet,
  apiPatchAuth,
  apiPostAuth,
  apiPutAuth,
} from './client'
import type {
  TeamEventAttendanceRead,
  TeamEventAttendanceRosterRead,
  TeamEventAttendanceSetPayload,
  TeamEventCreatePayload,
  TeamEventDiaryEntryRead,
  TeamEventDiaryEntrySavePayload,
  TeamEventDrillCreatePayload,
  TeamEventDrillRead,
  TeamEventDrillSectionRead,
  TeamEventDrillUpdatePayload,
  TeamEventLineupGroupCreatePayload,
  TeamEventLineupGroupRead,
  TeamEventLineupGroupUpdatePayload,
  TeamEventLineupRead,
  TeamEventNudgeResult,
  TeamEventRead,
  TeamEventReschedulePayload,
  TeamIceScheduleTemplateCreatePayload,
  TeamIceScheduleTemplateRead,
} from '../types/teamEvent'

// -- TeamEvent --

export function listTeamEvents(teamId: string, accessToken: string): Promise<TeamEventRead[]> {
  return apiGet<TeamEventRead[]>(`/teams/${teamId}/events`, accessToken)
}

export function getTeamEvent(
  teamId: string,
  eventId: string,
  accessToken: string,
): Promise<TeamEventRead> {
  return apiGet<TeamEventRead>(`/teams/${teamId}/events/${eventId}`, accessToken)
}

export function createTeamEvent(
  teamId: string,
  payload: TeamEventCreatePayload,
  accessToken: string,
): Promise<TeamEventRead> {
  return apiPostAuth<TeamEventRead>(`/teams/${teamId}/events`, payload, accessToken)
}

// Captain-only -- the backend 403s for anyone else.
export function rescheduleTeamEvent(
  teamId: string,
  eventId: string,
  payload: TeamEventReschedulePayload,
  accessToken: string,
): Promise<TeamEventRead> {
  return apiPutAuth<TeamEventRead>(`/teams/${teamId}/events/${eventId}/schedule`, payload, accessToken)
}

// Captain-only. 409s if already cancelled.
export function cancelTeamEvent(
  teamId: string,
  eventId: string,
  accessToken: string,
): Promise<TeamEventRead> {
  return apiPostAuth<TeamEventRead>(`/teams/${teamId}/events/${eventId}/cancel`, {}, accessToken)
}

// -- board --

// Captain-only, TRAINING only (409 for a game). Idempotent.
export function publishBoard(
  teamId: string,
  eventId: string,
  accessToken: string,
): Promise<TeamEventRead> {
  return apiPostAuth<TeamEventRead>(`/teams/${teamId}/events/${eventId}/board/publish`, {}, accessToken)
}

// Captain-only. Deleting a section deletes its drills too.
export function addSection(
  teamId: string,
  eventId: string,
  name: string,
  accessToken: string,
): Promise<TeamEventDrillSectionRead> {
  return apiPostAuth<TeamEventDrillSectionRead>(`/teams/${teamId}/events/${eventId}/sections`, { name }, accessToken)
}

export function renameSection(
  teamId: string,
  eventId: string,
  sectionId: string,
  name: string,
  accessToken: string,
): Promise<TeamEventDrillSectionRead> {
  return apiPatchAuth<TeamEventDrillSectionRead>(
    `/teams/${teamId}/events/${eventId}/sections/${sectionId}`,
    { name },
    accessToken,
  )
}

export function deleteSection(
  teamId: string,
  eventId: string,
  sectionId: string,
  accessToken: string,
): Promise<void> {
  return apiDeleteAuth<void>(`/teams/${teamId}/events/${eventId}/sections/${sectionId}`, accessToken)
}

export function reorderSections(
  teamId: string,
  eventId: string,
  sectionIds: string[],
  accessToken: string,
): Promise<void> {
  return apiPutAuth<void>(
    `/teams/${teamId}/events/${eventId}/sections/order`,
    { section_ids: sectionIds },
    accessToken,
  )
}

export function addDrill(
  teamId: string,
  eventId: string,
  payload: TeamEventDrillCreatePayload,
  accessToken: string,
): Promise<TeamEventDrillRead> {
  return apiPostAuth<TeamEventDrillRead>(`/teams/${teamId}/events/${eventId}/drills`, payload, accessToken)
}

export function updateDrill(
  teamId: string,
  eventId: string,
  drillId: string,
  payload: TeamEventDrillUpdatePayload,
  accessToken: string,
): Promise<TeamEventDrillRead> {
  return apiPatchAuth<TeamEventDrillRead>(
    `/teams/${teamId}/events/${eventId}/drills/${drillId}`,
    payload,
    accessToken,
  )
}

export function deleteDrill(
  teamId: string,
  eventId: string,
  drillId: string,
  accessToken: string,
): Promise<void> {
  return apiDeleteAuth<void>(`/teams/${teamId}/events/${eventId}/drills/${drillId}`, accessToken)
}

// Order within one section -- drillIds must be exactly that section's drills.
export function reorderDrills(
  teamId: string,
  eventId: string,
  sectionId: string,
  drillIds: string[],
  accessToken: string,
): Promise<TeamEventDrillRead[]> {
  return apiPutAuth<TeamEventDrillRead[]>(
    `/teams/${teamId}/events/${eventId}/drills/order`,
    { section_id: sectionId, drill_ids: drillIds },
    accessToken,
  )
}

// -- attendance --

export function getAttendanceRoster(
  teamId: string,
  eventId: string,
  accessToken: string,
): Promise<TeamEventAttendanceRosterRead> {
  return apiGet<TeamEventAttendanceRosterRead>(`/teams/${teamId}/events/${eventId}/attendance`, accessToken)
}

// 409s past the -2h deadline.
export function setMyAttendance(
  teamId: string,
  eventId: string,
  payload: TeamEventAttendanceSetPayload,
  accessToken: string,
): Promise<TeamEventAttendanceRead> {
  return apiPutAuth<TeamEventAttendanceRead>(
    `/teams/${teamId}/events/${eventId}/attendance/me`,
    payload,
    accessToken,
  )
}

export function clearMyAttendance(
  teamId: string,
  eventId: string,
  accessToken: string,
): Promise<void> {
  return apiDeleteAuth<void>(`/teams/${teamId}/events/${eventId}/attendance/me`, accessToken)
}

// Captain-only, rate-limited server-side to once/hour (429 otherwise).
export function sendAttendanceNudge(
  teamId: string,
  eventId: string,
  accessToken: string,
): Promise<TeamEventNudgeResult> {
  return apiPostAuth<TeamEventNudgeResult>(`/teams/${teamId}/events/${eventId}/attendance/nudge`, {}, accessToken)
}

// -- lineup --

export function getLineup(
  teamId: string,
  eventId: string,
  accessToken: string,
): Promise<TeamEventLineupRead> {
  return apiGet<TeamEventLineupRead>(`/teams/${teamId}/events/${eventId}/lineup`, accessToken)
}

// Captain-only. Idempotent, same as publishBoard.
export function publishLineup(
  teamId: string,
  eventId: string,
  accessToken: string,
): Promise<TeamEventLineupRead> {
  return apiPostAuth<TeamEventLineupRead>(`/teams/${teamId}/events/${eventId}/lineup/publish`, {}, accessToken)
}

// Captain-only. `color` 400s for a GAME event.
export function createLineupGroup(
  teamId: string,
  eventId: string,
  payload: TeamEventLineupGroupCreatePayload,
  accessToken: string,
): Promise<TeamEventLineupGroupRead> {
  return apiPostAuth<TeamEventLineupGroupRead>(
    `/teams/${teamId}/events/${eventId}/lineup/groups`,
    payload,
    accessToken,
  )
}

export function updateLineupGroup(
  teamId: string,
  eventId: string,
  groupId: string,
  payload: TeamEventLineupGroupUpdatePayload,
  accessToken: string,
): Promise<TeamEventLineupGroupRead> {
  return apiPatchAuth<TeamEventLineupGroupRead>(
    `/teams/${teamId}/events/${eventId}/lineup/groups/${groupId}`,
    payload,
    accessToken,
  )
}

// Its slots cascade -- those players become unassigned, not deleted.
export function deleteLineupGroup(
  teamId: string,
  eventId: string,
  groupId: string,
  accessToken: string,
): Promise<void> {
  return apiDeleteAuth<void>(`/teams/${teamId}/events/${eventId}/lineup/groups/${groupId}`, accessToken)
}

// Upsert -- moves the player if they were already placed in a different
// group for this event.
export function assignLineupPlayer(
  teamId: string,
  eventId: string,
  targetUserId: string,
  groupId: string,
  accessToken: string,
): Promise<TeamEventLineupGroupRead> {
  return apiPutAuth<TeamEventLineupGroupRead>(
    `/teams/${teamId}/events/${eventId}/lineup/players/${targetUserId}`,
    { group_id: groupId },
    accessToken,
  )
}

export function unassignLineupPlayer(
  teamId: string,
  eventId: string,
  targetUserId: string,
  accessToken: string,
): Promise<void> {
  return apiDeleteAuth<void>(
    `/teams/${teamId}/events/${eventId}/lineup/players/${targetUserId}`,
    accessToken,
  )
}

// -- diary / rewards --

export function getMyDiaryEntry(
  teamId: string,
  eventId: string,
  accessToken: string,
): Promise<TeamEventDiaryEntryRead | null> {
  return apiGet<TeamEventDiaryEntryRead | null>(`/teams/${teamId}/events/${eventId}/diary/me`, accessToken)
}

// note=null is an explicit skip -- either way, the FIRST save grants the
// three on-ice stats + a fixed XP bonus; re-saving to edit the note never
// re-grants. 400s for a GAME event.
export function saveMyDiaryEntry(
  teamId: string,
  eventId: string,
  payload: TeamEventDiaryEntrySavePayload,
  accessToken: string,
): Promise<TeamEventDiaryEntryRead> {
  return apiPutAuth<TeamEventDiaryEntryRead>(`/teams/${teamId}/events/${eventId}/diary/me`, payload, accessToken)
}

// -- ice schedule template --

export function listIceScheduleTemplates(
  teamId: string,
  accessToken: string,
): Promise<TeamIceScheduleTemplateRead[]> {
  return apiGet<TeamIceScheduleTemplateRead[]>(`/teams/${teamId}/ice-schedule-templates`, accessToken)
}

// Captain-only. TRAINING only -- the background scheduler stamps future
// TeamEvent rows from this on its own, nothing is created synchronously.
export function createIceScheduleTemplate(
  teamId: string,
  payload: TeamIceScheduleTemplateCreatePayload,
  accessToken: string,
): Promise<TeamIceScheduleTemplateRead> {
  return apiPostAuth<TeamIceScheduleTemplateRead>(
    `/teams/${teamId}/ice-schedule-templates`,
    payload,
    accessToken,
  )
}

// Captain-only. Deactivating never touches TeamEvent rows already stamped.
export function setIceScheduleTemplateActive(
  teamId: string,
  templateId: string,
  active: boolean,
  accessToken: string,
): Promise<TeamIceScheduleTemplateRead> {
  return apiPatchAuth<TeamIceScheduleTemplateRead>(
    `/teams/${teamId}/ice-schedule-templates/${templateId}`,
    { active },
    accessToken,
  )
}

// Captain-only. Already-stamped TeamEvent rows survive.
export function deleteIceScheduleTemplate(
  teamId: string,
  templateId: string,
  accessToken: string,
): Promise<void> {
  return apiDeleteAuth<void>(`/teams/${teamId}/ice-schedule-templates/${templateId}`, accessToken)
}
