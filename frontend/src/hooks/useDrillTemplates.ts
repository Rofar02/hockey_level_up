import { useEffect, useState } from 'react'
import * as teamEventsApi from '../api/teamEvents'
import { useAuth } from './useAuth'
import type { DrillTemplateRead } from '../types/teamEvent'

// The coach's own templates, loaded once per open sheet. null while
// loading (or without a token); a failed load reads as "no templates" --
// the sheet still works for a plain new drill.
export function useDrillTemplates() {
  const { accessToken } = useAuth()
  const [templates, setTemplates] = useState<DrillTemplateRead[] | null>(null)
  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    teamEventsApi
      .listDrillTemplates(accessToken)
      .then((loaded) => {
        if (!cancelled) {
          setTemplates(loaded)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTemplates([])
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])
  return [templates, setTemplates] as const
}
