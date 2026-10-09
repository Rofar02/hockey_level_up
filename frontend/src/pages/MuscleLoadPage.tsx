import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BackLink } from '../components/ui/BackLink'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { MuscleLoadChart } from '../components/MuscleLoadChart'
import * as progressApi from '../api/progress'
import * as restrictionsApi from '../api/userTemporaryRestrictions'
import { useAuth } from '../hooks/useAuth'
import type { MuscleLoadRead } from '../types/progress'
import type { UserTemporaryRestrictionRead } from '../types/userTemporaryRestriction'

// The body map of recent muscle load -- used to be the "Нагрузка" tab of a
// modal on the profile. Restricted areas show red, same as on /restrictions.
export function MuscleLoadPage() {
  const { accessToken } = useAuth()
  const [loads, setLoads] = useState<MuscleLoadRead[] | null>(null)
  const [restrictions, setRestrictions] = useState<UserTemporaryRestrictionRead[]>([])

  useEffect(() => {
    if (accessToken === null) {
      return
    }
    let cancelled = false
    progressApi
      .getMyMuscleLoads(accessToken)
      .then((result) => !cancelled && setLoads(result))
      .catch(() => !cancelled && setLoads([]))
    restrictionsApi
      .listActiveRestrictions(accessToken)
      .then((result) => !cancelled && setRestrictions(result))
      .catch(() => {
        // Best-effort -- the chart just renders with nothing marked restricted.
      })
    return () => {
      cancelled = true
    }
  }, [accessToken])

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-2xl flex-col gap-4 px-4 py-6">
        <div className="flex flex-col gap-2">
          <BackLink />
          <h1 className="text-xl font-semibold">Нагрузка</h1>
          <p className="text-sm text-[#8A94A6]">
            Насколько нагружены мышцы по последним тренировкам — в зале, на льду и в играх (по отчёту после льда). Если что-то болит — отметьте в{' '}
            <Link to="/restrictions" className="text-accent-ice">
              ограничениях
            </Link>
            .
          </p>
        </div>
        {loads === null ? (
          <p className="text-sm text-[#8A94A6]">Загрузка...</p>
        ) : (
          <MuscleLoadChart loads={loads} restrictions={restrictions} />
        )}
      </div>
    </div>
  )
}
