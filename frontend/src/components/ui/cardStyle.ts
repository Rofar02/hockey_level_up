// Card surface shared across the whole app: dark-card fill with a thin icy
// top border ("the rink's blue line" -- see HomePage's own CARD_CLASS_URGENT
// for the red-line status variant, which stays local to Home since it's a
// newer, single-use convention). Centralized here (2026-08-28) after
// finding this exact string hand-duplicated across ~20 files -- any future
// tweak to the convention was a 20-file find-and-replace before this.
export const CARD_BORDER = 'border-t border-[rgba(215,239,255,0.35)]'
export const CARD_CLASS = `rounded-md ${CARD_BORDER} bg-dark-card`
