// Reusable icy backdrop: dark base + a handful of radial "glare" gradients
// plus thin scratch lines. Coordinates live in a 0-100 percentage space
// (preserveAspectRatio="none") so the same markup fills any container.
// Pinned to the viewport via `fixed inset-0` rather than `absolute inset-0`
// -- an absolute backdrop stretches to match its `relative` parent's height,
// so it visibly re-stretches/shifts whenever page content grows (a modal
// opening, a skills/week block expanding). `fixed` sizes it to the viewport
// once and leaves it alone regardless of content height; page content still
// scrolls over it because the content wrapper sits in a later stacking
// context (z-[1]). pointer-events-none so this purely-decorative layer (also
// aria-hidden) never intercepts clicks/scroll from the content above it.
// Meant to sit at z-0 behind page content, e.g.:
//
//   <div className="relative min-h-svh overflow-hidden">
//     <IceGlowBackground />
//     <div className="relative z-[1]">...</div>
//   </div>
export function IceGlowBackground() {
  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className="fixed inset-0 z-0 h-screen w-screen pointer-events-none"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="ice-glow-top-left" cx="8" cy="6" r="55" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3D6E96" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#3D6E96" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ice-glow-top-right" cx="92" cy="4" r="35" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#D7EFFF" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#D7EFFF" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ice-glow-left-mid" cx="0" cy="50" r="45" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3D6E96" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#3D6E96" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ice-glow-right-mid" cx="100" cy="50" r="38" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#D7EFFF" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#D7EFFF" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ice-glow-bottom-left" cx="6" cy="96" r="50" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#3D6E96" stopOpacity="0.45" />
          <stop offset="100%" stopColor="#3D6E96" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="ice-glow-bottom-right" cx="94" cy="98" r="32" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#D7EFFF" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#D7EFFF" stopOpacity="0" />
        </radialGradient>
      </defs>

      <rect x="0" y="0" width="100" height="100" fill="#0D1420" />
      <rect x="0" y="0" width="100" height="100" fill="url(#ice-glow-top-left)" />
      <rect x="0" y="0" width="100" height="100" fill="url(#ice-glow-top-right)" />
      <rect x="0" y="0" width="100" height="100" fill="url(#ice-glow-left-mid)" />
      <rect x="0" y="0" width="100" height="100" fill="url(#ice-glow-right-mid)" />
      <rect x="0" y="0" width="100" height="100" fill="url(#ice-glow-bottom-left)" />
      <rect x="0" y="0" width="100" height="100" fill="url(#ice-glow-bottom-right)" />

      {/* Scratches -- thin, irregular, clustered near the glows above, deliberately not mirrored */}
      <g stroke="#D7EFFF" strokeLinecap="round">
        <line x1="12" y1="4" x2="29" y2="15" strokeWidth="0.25" opacity="0.18" />
        <line x1="19" y1="17" x2="24" y2="31" strokeWidth="0.15" opacity="0.12" />
        <line x1="80" y1="2" x2="91" y2="8" strokeWidth="0.2" opacity="0.15" />
        <line x1="0" y1="45" x2="15" y2="56" strokeWidth="0.25" opacity="0.2" />
        <line x1="2" y1="59" x2="8" y2="71" strokeWidth="0.15" opacity="0.1" />
        <line x1="97" y1="41" x2="87" y2="53" strokeWidth="0.2" opacity="0.14" />
        <line x1="7" y1="87" x2="27" y2="95" strokeWidth="0.25" opacity="0.22" />
        <line x1="83" y1="91" x2="94" y2="97" strokeWidth="0.15" opacity="0.16" />
      </g>
    </svg>
  )
}
