import { HockeyStickIcon } from './EquipmentIcon'
import type { TargetStat } from '../../types/exercise'

// Real Tabler classes for every stat except agility, which has no good
// generic-icon-set match for "change-of-direction speed" -- verified live in
// the running app (font is loaded from the CDN, not bundled locally, so a
// plain CSS-file grep gives false negatives -- `ti-ice-skating` and
// `ti-brain` both looked "absent" that way despite rendering fine).
const TABLER_CLASSES: Partial<Record<TargetStat, string>> = {
  strength: 'ti-barbell',
  intellect: 'ti-brain',
  endurance: 'ti-heartbeat',
  on_ice_skating: 'ti-ice-skating',
}

type IconProps = { size: number; className?: string }

function AgilityIcon({ size, className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M4 17l5-8 3 4 4-9 4 13" />
    </svg>
  )
}

// Renders a TargetStat's icon regardless of whether it comes from the
// Tabler webfont or a hand-drawn SVG -- callers (HomePage's StatsRow,
// ProfilePage's stat grid) don't need to know which. `size` is required
// (not defaulted) so every call site picks a value deliberately for its own
// tile size rather than inheriting a guess that only happens to fit one caller.
export function StatIcon({ stat, size, className }: { stat: TargetStat; size: number; className?: string }) {
  if (stat === 'agility') {
    return <AgilityIcon size={size} className={className} />
  }
  if (stat === 'puck_handling') {
    return <HockeyStickIcon size={size} className={className} />
  }
  return (
    <i className={`ti ${TABLER_CLASSES[stat]} ${className ?? ''}`} style={{ fontSize: size }} aria-hidden="true" />
  )
}
