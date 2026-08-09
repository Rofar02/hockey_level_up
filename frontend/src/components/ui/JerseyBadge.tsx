interface JerseyBadgeProps {
  number: number | string
  label: string
  accentColor: 'ice' | 'persimmon'
  // Optional nameplate above the number (e.g. the player-number badge, not
  // the rating one). Grows the viewBox/box height to make room and shifts
  // the number down to match -- see NUMBER_Y_BY_VARIANT below.
  surname?: string
}

// One class per accent, applied to the <svg> itself (sets CSS `color`) --
// both the outline strokes and the number's/surname's fill read it via
// currentColor, so there's a single source of truth for the accent instead
// of separate stroke-*/text-* classes.
const ACCENT_CLASSES: Record<JerseyBadgeProps['accentColor'], string> = {
  ice: 'text-accent-ice',
  persimmon: 'text-accent-persimmon',
}

const JERSEY_PATH =
  'M46 4 L38 12 L10 21 C5 23 4 27 6 32 L17 50 C19 53 24 54 27 52 L38 46 L38 96 C38 98 40 100 42 100 L88 100 C90 100 92 98 92 96 L92 46 L103 52 C106 54 111 53 113 50 L124 32 C126 27 125 23 120 21 L92 12 L84 4 C80 8 72 10 65 10 C58 10 50 8 46 4 Z'
const COLLAR_PATH = 'M48 6 C53 9 58 10.5 65 10.5 C72 10.5 77 9 82 6'

// Fixed hockey-jersey silhouette (round collar, no stripes, rectangular
// torso with raglan sleeves), scaled to whatever size the wrapping div is
// given. Unlike the old ShieldBadge, the number/surname are real SVG
// <text> here (not an HTML overlay) on purpose: x/y/font-size are unitless
// SVG attributes, so they live in the viewBox's own coordinate space and
// scale automatically with the SVG's rendered size -- an HTML overlay's
// font size is a fixed CSS pixel value that would only look right at the
// one pixel size it was tuned for.
export function JerseyBadge({ number, label, accentColor, surname }: JerseyBadgeProps) {
  // "" is treated the same as absent -- User.last_name can be "" for
  // legacy profiles created before the field existed (DB server_default),
  // and an empty uppercase nameplate would just be a stray line.
  const hasSurname = surname !== undefined && surname.trim() !== ''
  const viewBoxHeight = hasSurname ? 110 : 100
  // Shifted up 8 viewBox units from the original 76/70 (and surname from
  // 42 to 34 below, same 8-unit shift) -- the gap between the two lines
  // stays 34 either way, only their shared vertical position moved.
  const numberY = hasSurname ? 68 : 62

  return (
    <div className="flex flex-col items-center">
      <div className={`relative w-[90px] ${hasSurname ? 'aspect-[130/110]' : 'aspect-[130/100]'}`}>
        <svg
          viewBox={`0 0 130 ${viewBoxHeight}`}
          className={`absolute inset-0 h-full w-full ${ACCENT_CLASSES[accentColor]}`}
          aria-hidden="true"
        >
          <path
            d={JERSEY_PATH}
            className="fill-dark-card"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinejoin="round"
          />
          <path d={COLLAR_PATH} fill="none" stroke="currentColor" strokeWidth={2} />
          {hasSurname && (
            <text
              x={65}
              y={34}
              textAnchor="middle"
              fontSize={11}
              letterSpacing={0.5}
              fill="currentColor"
              className="font-sans font-bold uppercase"
            >
              {surname}
            </text>
          )}
          <text
            x={65}
            y={numberY}
            textAnchor="middle"
            fontSize={26}
            fill="currentColor"
            className="font-mono font-bold"
          >
            {number}
          </text>
        </svg>
      </div>
      <span className="mt-1 text-[10px] uppercase tracking-wide text-text-secondary">{label}</span>
    </div>
  )
}
