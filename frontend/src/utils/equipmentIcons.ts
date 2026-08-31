import type { EquipmentItem } from '../types/exercise'

// Tabler Icons class names, verified to actually exist in the loaded
// webfont (curl'd the real CSS and grepped it, not guessed from names
// that merely sound plausible -- .ti-kettlebell and .ti-vest do NOT
// exist in this icon set, despite sounding like they should). Closest
// available substitutes picked for those two: a generic weight for
// kettlebell, a jacket for the weighted vest.
//
// hockey_stick is deliberately absent -- no real stick/puck glyph exists
// in this webfont either, and unlike kettlebell/vest a generic substitute
// (previously .ti-golf) didn't actually read as a hockey stick. Rendered
// by a hand-drawn SVG instead -- see components/ui/EquipmentIcon.tsx,
// the only place that should ever read this map.
export const EQUIPMENT_ICONS: Record<Exclude<EquipmentItem, 'hockey_stick'>, string> = {
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
  // No dedicated "gym machine" glyph in this webfont either -- .ti-gym-
  // machine/.ti-machine don't exist (checked the same way as the two
  // substitutes above). .ti-treadmill does exist and reads as generic gym
  // equipment closely enough for a catch-all category.
  gym_machine: 'ti-treadmill',
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
  gym_machine: 'Тренажёр — блок, платформа, Смит-машина и т.п. фиксированное оборудование зала.',
  hockey_stick:
    'Клюшка — своё снаряжение, не покрывается доступом в зал. Нужна для упражнений на владение шайбой.',
}
