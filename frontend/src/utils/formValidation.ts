// The browser's own validation bubbles (15.10) speak the phone's language,
// look different on every phone and vanish after a second. Forms with
// `noValidate` call this on submit instead: the first field that fails its
// HTML constraints (required, type=email, minLength, min/max) gets focus and
// one Russian sentence comes back for the form's FormError.

type Field = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement

function fieldLabel(field: Field): string {
  const label = field.labels?.[0]?.textContent?.trim()
  return label !== undefined && label !== '' ? label : 'Поле'
}

function messageFor(field: Field): string {
  const label = fieldLabel(field)
  const { validity } = field
  const input = field instanceof HTMLInputElement ? field : null
  if (validity.valueMissing) {
    if (input?.type === 'checkbox') {
      return 'Отметьте согласие, чтобы продолжить'
    }
    return field instanceof HTMLSelectElement ? `Выберите: «${label}»` : `Заполните поле «${label}»`
  }
  if (validity.typeMismatch && input?.type === 'email') {
    return 'Проверьте email: в нём должны быть @ и домен, например name@mail.ru'
  }
  if (validity.tooShort && input !== null) {
    return `${label} — минимум ${input.minLength} символов`
  }
  if (validity.tooLong && input !== null) {
    return `${label} — не больше ${input.maxLength} символов`
  }
  if (validity.badInput) {
    return input?.type === 'date' ? `${label}: проверьте дату` : `${label}: нужно число`
  }
  if (validity.rangeUnderflow && input !== null) {
    return input.type === 'date' ? `${label}: слишком ранняя дата` : `${label} — не меньше ${input.min}`
  }
  if (validity.rangeOverflow && input !== null) {
    return input.type === 'date' ? `${label}: дата не может быть в будущем` : `${label} — не больше ${input.max}`
  }
  if (validity.stepMismatch) {
    return `${label}: нужно целое число`
  }
  return `Проверьте поле «${label}»`
}

export function firstInvalidMessage(form: HTMLFormElement): string | null {
  for (const element of Array.from(form.elements)) {
    if (
      (element instanceof HTMLInputElement ||
        element instanceof HTMLSelectElement ||
        element instanceof HTMLTextAreaElement) &&
      !element.disabled &&
      !element.validity.valid
    ) {
      element.focus()
      return messageFor(element)
    }
  }
  return null
}
