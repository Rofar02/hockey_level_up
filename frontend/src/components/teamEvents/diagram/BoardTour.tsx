import { useState } from 'react'

const TOUR_KEY = 'board-tour-seen'

const STEPS: { title: string; text: string }[] = [
  {
    title: 'Расставьте игроков',
    text: 'Кнопки внизу: «Свой», «Соперник», «Шайба». Фишку можно тянуть пальцем по площадке.',
  },
  {
    title: 'Ведите пальцем',
    text: 'Нажмите на фишку и выберите стрелку — кат без шайбы, кат с шайбой, пас, перепас или бросок. Потом проведите пальцем по траектории.',
  },
  {
    title: 'Делите на кадры',
    text: '«Новый кадр» — следующий шаг упражнения. Игроки продолжат с того места, где закончили в прошлом кадре.',
  },
  {
    title: 'Проиграйте схему',
    text: 'Кнопка ▶ показывает упражнение как мультик — так его увидят игроки в плане тренировки.',
  },
]

function alreadySeen(): boolean {
  try {
    return window.localStorage.getItem(TOUR_KEY) !== null
  } catch {
    return true
  }
}

// First open of the rink scheme editor (2026-10-08): four short steps on how
// to draw. The editor covers the whole app and keeps the app-wide coachmark
// tour suppressed, so it has its own card -- at the top, over the far end of
// the rink, so the palette, frames and toolbar below stay usable. Once per
// device.
export function BoardTour() {
  const [step, setStep] = useState<number | null>(() => (alreadySeen() ? null : 0))
  if (step === null) {
    return null
  }

  function close() {
    try {
      window.localStorage.setItem(TOUR_KEY, '1')
    } catch {
      // Hidden for this visit only.
    }
    setStep(null)
  }

  const current = STEPS[step]
  const isLast = step === STEPS.length - 1
  return (
    <div className="pointer-events-none absolute inset-x-3 top-[calc(92px+env(safe-area-inset-top,0px))] z-20 flex justify-center">
      <section
        role="dialog"
        aria-label="Как рисовать схему"
        className="pointer-events-auto w-full max-w-sm rounded-2xl bg-[#F2F5F8] p-4 text-[#111827] shadow-[0_18px_40px_rgba(0,0,0,0.5)]"
      >
        <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#A33B2B]">
          Схема · шаг {step + 1} из {STEPS.length}
        </p>
        <p className="mt-1.5 text-base font-semibold">{current.title}</p>
        <p className="mt-1 text-sm leading-relaxed text-[#3B4659]">{current.text}</p>
        <div className="mt-3 flex items-center justify-between">
          <div className="flex gap-1.5" aria-hidden="true">
            {STEPS.map((item, index) => (
              <span
                key={item.title}
                className={`h-1.5 rounded-full ${index === step ? 'w-4 bg-[#111827]' : 'w-1.5 bg-[#9FB4C7]'}`}
              />
            ))}
          </div>
          <div className="flex gap-1">
            {!isLast && (
              <button type="button" onClick={close} className="min-h-11 px-3 text-sm text-[#5B6678]">
                Пропустить
              </button>
            )}
            <button
              type="button"
              onClick={() => (isLast ? close() : setStep(step + 1))}
              className="min-h-11 rounded-xl bg-[#111827] px-4 text-sm font-semibold text-[#F2F5F8]"
            >
              {isLast ? 'Понятно' : 'Далее'}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
