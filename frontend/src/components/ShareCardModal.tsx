import { useEffect, useState } from 'react'
import { Button } from './ui/Button'
import { Modal } from './ui/Modal'

// The finished card picture, then the ways out. Two taps on purpose: Safari
// opens the share sheet only straight from a tap, and rendering the picture
// takes a moment -- calling navigator.share() after that wait from the first
// tap is refused on an iPhone. Here the picture is ready and "Отправить"
// shares it right in its own tap.

const FILE_NAME = 'icelevel-card.png'

export function ShareCardModal({
  image,
  onClose,
  title = 'Карточка игрока',
  shareTitle = 'Моя карточка IceLevel',
}: {
  image: Blob
  onClose: () => void
  title?: string
  shareTitle?: string
}) {
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [file] = useState(() => new File([image], FILE_NAME, { type: 'image/png' }))
  // The share sheet exists only over https (and not on every desktop).
  const canShareFile = typeof navigator.canShare === 'function' && navigator.canShare({ files: [file] })

  // Created and revoked by the same effect, StrictMode-safe.
  useEffect(() => {
    const url = URL.createObjectURL(image)
    setImageUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [image])

  function handleShare() {
    setError(null)
    navigator.share({ files: [file], title: shareTitle }).catch((err: unknown) => {
      // Closing the sheet without picking anything isn't an error.
      if (!(err instanceof DOMException && err.name === 'AbortError')) {
        setError(`Не удалось открыть меню «Поделиться» (${err instanceof Error ? err.name : 'ошибка'}).`)
      }
    })
  }

  function handleDownload() {
    if (imageUrl === null) {
      return
    }
    const link = document.createElement('a')
    link.href = imageUrl
    link.download = FILE_NAME
    link.click()
  }

  return (
    <Modal title={title} onClose={onClose}>
      <div className="flex flex-col items-center gap-4">
        {imageUrl !== null && (
          <img src={imageUrl} alt={title} className="max-h-[44dvh] w-auto max-w-full rounded-xl" />
        )}
        <p className="text-center text-xs text-[#8A94A6]">
          На iPhone можно нажать на картинку и подержать — «Сохранить в Фото».
        </p>
        {error !== null && <p className="text-center text-xs text-accent-persimmon">{error}</p>}
        <div className="flex w-full gap-2">
          <Button type="button" variant="neutral" onClick={handleDownload} className="flex-1">
            Скачать
          </Button>
          {canShareFile && (
            <Button type="button" onClick={handleShare} className="flex-1">
              Отправить
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}
