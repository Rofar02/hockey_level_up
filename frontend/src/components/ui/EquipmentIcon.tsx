import { EQUIPMENT_ICONS } from '../../utils/equipmentIcons'
import type { EquipmentItem } from '../../types/exercise'

// 2026-08-22: no hockey-stick/puck glyph exists in the loaded Tabler
// webfont (checked the real CSS, same way kettlebell/vest were checked) --
// a hand-drawn inline SVG instead of the ".ti-golf" placeholder previously
// used there. Same stroke style as Tabler's own icons (24x24 viewBox, 2px
// round stroke, currentColor) so it blends in next to the font icons.
// width/height are a fixed 24 (not "1em") -- an em-unit SVG size attribute
// didn't actually track the text-2xl font-size utility on `className` in
// testing, rendering a barely-visible sliver instead. `className` is
// still applied for color (currentColor) and any layout classes.
function HockeyStickIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="24"
      height="24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M17 2.5 L6.5 17" />
      <path d="M6.5 17 Q6.2 19 8.5 19.3 L15 18.5" />
      <circle cx="19.5" cy="19.5" r="1.8" fill="currentColor" stroke="none" />
    </svg>
  )
}

// Renders an equipment item's icon regardless of whether it comes from the
// Tabler webfont (EQUIPMENT_ICONS) or a hand-drawn SVG override like
// HockeyStickIcon above -- callers (ProfilePage's inventory grid) don't
// need to know which.
export function EquipmentIcon({ item, className }: { item: EquipmentItem; className?: string }) {
  if (item === 'hockey_stick') {
    return <HockeyStickIcon className={className} />
  }
  return <i className={`ti ${EQUIPMENT_ICONS[item]} ${className ?? ''}`} aria-hidden="true" />
}
