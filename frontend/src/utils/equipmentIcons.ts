import type { EquipmentItem } from '../types/exercise'

// Tabler Icons class names, verified to actually exist in the loaded
// webfont (curl'd the real CSS and grepped it, not guessed from names
// that merely sound plausible -- .ti-kettlebell and .ti-vest do NOT
// exist in this icon set, despite sounding like they should). Closest
// available substitutes picked for those two: a generic weight for
// kettlebell, a jacket for the weighted vest.
export const EQUIPMENT_ICONS: Record<EquipmentItem, string> = {
  kettlebell: 'ti-weight',
  dumbbells: 'ti-dumbbell',
  barbell: 'ti-barbell',
  resistance_band: 'ti-yoga',
  pull_up_bar: 'ti-arrow-bar-to-up',
  jump_rope: 'ti-jump-rope',
  foam_roller: 'ti-massage',
  step_platform: 'ti-stairs',
  slide_board: 'ti-arrows-left-right',
  medicine_ball: 'ti-exercise-ball',
  weighted_vest: 'ti-jacket',
}

export const EQUIPMENT_ITEM_DESCRIPTIONS: Record<EquipmentItem, string> = {
  kettlebell: 'Гиря — маховые и силовые упражнения со смещённым центром тяжести.',
  dumbbells: 'Гантели — базовый снаряд для большинства силовых упражнений.',
  barbell: 'Штанга — тяжёлые базовые движения с большим рабочим весом.',
  resistance_band: 'Резина/эспандер — лёгкое сопротивление, удобно брать с собой.',
  pull_up_bar: 'Турник — подтягивания и вис.',
  jump_rope: 'Скакалка — кардио и координация.',
  foam_roller: 'Мяч для раскатки/МФР-ролик — самомассаж и восстановление мышц.',
  step_platform: 'Степ-платформа — степ-апы и плиометрика.',
  slide_board: 'Слайд-борд — латеральные скользящие движения, как на льду.',
  medicine_ball: 'Медбол — бросковые и взрывные упражнения.',
  weighted_vest: 'Утяжелительный жилет — добавляет вес к упражнениям с собственным телом.',
}
