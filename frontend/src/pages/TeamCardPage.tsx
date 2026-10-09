import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import * as teamsApi from '../api/teams'
import { ApiError } from '../api/client'
import { ShareCardModal } from '../components/ShareCardModal'
import { TeamCard, teamCardStyle } from '../components/teams/TeamCard'
import { getPlayerCardLook } from '../components/playerCardLook'
import { BackLink } from '../components/ui/BackLink'
import { FormError } from '../components/ui/FormError'
import { IceGlowBackground } from '../components/ui/IceGlowBackground'
import { useAuth } from '../hooks/useAuth'
import type { TeamCardRead } from '../types/team'
import { renderCardImage } from '../utils/cardImage'

// The team card page (2026-10-09): the card, a share button (the same PNG
// path as the player card), and the way into the roster and the games.
// Open to anyone signed in -- a player card's emblem links here.
export function TeamCardPage() {
  const { teamId } = useParams<{ teamId: string }>()
  const { accessToken } = useAuth()
  const [card, setCard] = useState<TeamCardRead | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [shareError, setShareError] = useState<string | null>(null)
  const [isSharing, setIsSharing] = useState(false)
  const [sharedImage, setSharedImage] = useState<Blob | null>(null)
  const cardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (accessToken === null || teamId === undefined) {
      return
    }
    let cancelled = false
    teamsApi
      .getTeamCard(teamId, accessToken)
      .then((result) => {
        if (!cancelled) {
          setCard(result)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Не удалось загрузить карточку команды.')
        }
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, teamId])

  async function handleShare() {
    const frame = cardRef.current?.querySelector<HTMLElement>('[data-card="frame"]')
    if (frame == null || card === null) {
      return
    }
    setShareError(null)
    setIsSharing(true)
    try {
      setSharedImage(await renderCardImage(frame, getPlayerCardLook(teamCardStyle(card.rating))))
    } catch (err) {
      setShareError(
        `Не удалось подготовить карточку (${err instanceof Error ? `${err.name}: ${err.message}` : String(err)}). Попробуйте ещё раз.`,
      )
    } finally {
      setIsSharing(false)
    }
  }

  return (
    <div className="relative min-h-svh overflow-hidden">
      <IceGlowBackground />
      <div className="relative z-[1] mx-auto flex max-w-md flex-col gap-4 px-4 py-6">
        <BackLink />
        <div className="flex items-center justify-between gap-3">
          <h1 className="font-display text-2xl font-semibold text-[#F5F7FA]">Команда</h1>
          {card !== null && (
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={handleShare}
                disabled={isSharing}
                aria-label="Поделиться карточкой команды"
                className="flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-white/5 text-accent-ice transition-colors hover:bg-white/10 disabled:cursor-wait"
              >
                <i className={`ti ${isSharing ? 'ti-loader-2 animate-spin' : 'ti-share'} text-lg`} aria-hidden="true" />
              </button>
              {card.is_captain && (
                <Link
                  to={`/teams/${card.id}`}
                  aria-label="Настройки команды"
                  className="flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-white/5 text-[#8A94A6] transition-colors hover:text-[#F5F7FA]"
                >
                  <i className="ti ti-settings text-lg" aria-hidden="true" />
                </Link>
              )}
            </div>
          )}
        </div>

        <FormError message={loadError} />
        <FormError message={shareError} />
        {card === null && loadError === null && <p className="text-sm text-text-secondary">Загрузка...</p>}

        {card !== null && (
          <>
            <div ref={cardRef}>
              <TeamCard card={card} />
            </div>
            {card.is_member && (
              <div className="grid grid-cols-2 gap-2.5">
                <Link
                  to={`/teams/${card.id}/lineup`}
                  className="flex h-[52px] items-center justify-center gap-2 rounded-[14px] bg-accent-persimmon font-semibold text-dark-bg"
                >
                  <i className="ti ti-users text-lg" aria-hidden="true" />
                  Состав и звенья
                </Link>
                <Link
                  to={`/teams/${card.id}/events`}
                  className="flex h-[52px] items-center justify-center gap-2 rounded-[14px] border border-accent-ice/25 font-semibold text-accent-ice"
                >
                  <i className="ti ti-calendar text-lg" aria-hidden="true" />
                  Календарь игр
                </Link>
              </div>
            )}
            {card.most_stable_line != null && (
              <div className="flex items-center gap-3 rounded-[14px] border border-white/5 bg-dark-card px-3.5 py-3">
                <i className="ti ti-link text-lg text-accent-ice" aria-hidden="true" />
                <span className="flex flex-col">
                  <span className="text-xs text-[#8A94A6]">Самое стабильное звено сезона</span>
                  <span className="text-sm font-semibold text-[#F5F7FA]">{card.most_stable_line.join(' — ')}</span>
                </span>
              </div>
            )}
            <p className="text-xs text-text-secondary">
              Победы и голы считаются по играм, где капитан внёс счёт. Рейтинг — средний «Общий» игроков команды.
            </p>
          </>
        )}
      </div>
      {sharedImage !== null && <ShareCardModal
          image={sharedImage}
          onClose={() => setSharedImage(null)}
          title="Карточка команды"
          shareTitle={card !== null ? `${card.name} — карточка команды IceLevel` : 'Карточка команды IceLevel'}
        />}
    </div>
  )
}
