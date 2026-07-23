/* eslint-disable react-hooks/set-state-in-effect */
import {
  useEffect,
  useState,
  type CSSProperties,
  type SyntheticEvent,
} from 'react'
import { createPortal } from 'react-dom'
import type { Game } from '../../types/game'
import {
  fallbackCoverUrl,
  galleryImages,
  looksLikePlaceholderImage,
  thumbnailUrl,
} from '../../utils/coverImage'

const GALLERY_INLINE_LIMIT = 14
const GALLERY_EAGER_LIMIT = 4

function thumbErrorHandler(fullUrl: string) {
  return (event: SyntheticEvent<HTMLImageElement>) => {
    const image = event.currentTarget
    if (image.src !== fullUrl) {
      image.src = fullUrl
      return
    }
    image.parentElement?.style.setProperty('display', 'none')
  }
}

function useGalleryLightbox(images: string[]) {
  const [index, setIndex] = useState<number | null>(null)
  const [naturalSize, setNaturalSize] = useState<{
    width: number
    height: number
  } | null>(null)

  useEffect(() => {
    if (index === null) return
    setNaturalSize(null)
    document.body.style.overflow = 'hidden'
    const count = images.length
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setIndex(null)
      else if (event.key === 'ArrowRight') {
        setIndex((current) => current === null ? null : (current + 1) % count)
      } else if (event.key === 'ArrowLeft') {
        setIndex((current) => current === null ? null : (current - 1 + count) % count)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = ''
      window.removeEventListener('keydown', onKey)
    }
  }, [images.length, index])

  useEffect(() => {
    if (index === null) return
    const image = new Image()
    image.onload = () => setNaturalSize({
      width: image.naturalWidth,
      height: image.naturalHeight,
    })
    image.src = images[index]
  }, [images, index])

  useEffect(() => {
    if (index === null || images.length < 2) return
    for (const offset of [1, -1]) {
      const neighbour = new Image()
      neighbour.src = images[(index + offset + images.length) % images.length]
    }
  }, [images, index])

  return { index, naturalSize, setIndex }
}

function GalleryLightbox({
  images,
  index,
  naturalSize,
  onClose,
  onNavigate,
  title,
}: {
  images: string[]
  index: number
  naturalSize: { width: number; height: number } | null
  onClose: () => void
  onNavigate: (index: number) => void
  title: string
}) {
  return createPortal(
    <div className="dp-lightbox" role="dialog" aria-modal="true">
      <button type="button" className="dp-lightbox-backdrop" aria-label="Close" onClick={onClose} />
      <div className="dp-lightbox-stage">
        <img
          src={images[index]}
          alt={`${title} ${index === 0 ? 'cover' : `screenshot ${index}`}`}
          className="dp-lightbox-img"
          style={naturalSize ? {
            '--natural-width': `${naturalSize.width}px`,
            '--natural-height': `${naturalSize.height}px`,
          } as CSSProperties : undefined}
        />
      </div>
      <button type="button" className="dp-lightbox-close" onClick={onClose}>✕</button>
      {images.length > 1 ? (
        <>
          <button type="button" className="dp-lightbox-nav dp-lightbox-prev" onClick={() => onNavigate((index - 1 + images.length) % images.length)} aria-label="Previous image">‹</button>
          <button type="button" className="dp-lightbox-nav dp-lightbox-next" onClick={() => onNavigate((index + 1) % images.length)} aria-label="Next image">›</button>
        </>
      ) : null}
      <div className="dp-lightbox-counter">{index + 1} / {images.length}</div>
    </div>,
    document.body,
  )
}

function GalleryGrid({
  game,
  images,
  onOpen,
}: {
  game: Game
  images: string[]
  onOpen: (index: number) => void
}) {
  const inlineImages = images.slice(0, Math.min(images.length, GALLERY_INLINE_LIMIT))
  const overflowCount = Math.max(0, images.length - GALLERY_INLINE_LIMIT)
  const overflowImage = overflowCount > 0 ? images[GALLERY_INLINE_LIMIT] : null
  const [first, ...rest] = inlineImages
  const [heroFallback, setHeroFallback] = useState<string | null>(null)

  return (
    <div className="dp-gallery">
      <div className="dp-gallery-heading">
        <span>Media</span>
        <div className="dp-gallery-count-wrap">
          <button type="button" className="dp-gallery-count" onClick={() => onOpen(0)}>
            {images.length} {images.length === 1 ? 'image' : 'images'}
          </button>
          <div className="dp-gallery-strip" aria-label={`${game.title} media thumbnails`}>
            {images.map((url, index) => (
              <button type="button" key={`${url}-${index}`} className="dp-gallery-strip-item" onClick={() => onOpen(index)} aria-label={`Open image ${index + 1}`}>
                <img src={thumbnailUrl(url)} alt="" loading="lazy" decoding="async" onError={thumbErrorHandler(url)} />
              </button>
            ))}
          </div>
        </div>
      </div>
      <button type="button" className="dp-gallery-main" onClick={() => onOpen(0)}>
        <img
          src={heroFallback ?? first}
          alt={`${game.title} cover`}
          className="dp-gallery-hero"
          loading="eager"
          decoding="async"
          fetchPriority="high"
          onLoad={(event) => {
            if (heroFallback) return
            if (looksLikePlaceholderImage(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)) {
              setHeroFallback(images.find((url) => url !== first) ?? fallbackCoverUrl(game.title))
            }
          }}
          onError={() => setHeroFallback(fallbackCoverUrl(game.title))}
        />
        <div className="dp-gallery-zoom-hint">🔍</div>
      </button>
      {rest.length > 0 || overflowImage ? (
        <div className="dp-gallery-rest">
          {rest.map((url, index) => (
            <button type="button" key={url} className="dp-gallery-img" onClick={() => onOpen(index + 1)}>
              <img src={thumbnailUrl(url)} alt={`${game.title} screenshot ${index + 2}`} loading={index + 1 < GALLERY_EAGER_LIMIT ? 'eager' : 'lazy'} decoding="async" onError={thumbErrorHandler(url)} />
            </button>
          ))}
          {overflowImage ? (
            <button type="button" className="dp-gallery-img dp-gallery-more" onClick={() => onOpen(GALLERY_INLINE_LIMIT)} aria-label={`Open ${overflowCount} more images`}>
              <img src={thumbnailUrl(overflowImage)} alt={`${game.title} screenshot ${GALLERY_INLINE_LIMIT + 1}`} loading="lazy" decoding="async" onError={thumbErrorHandler(overflowImage)} />
              <span>+{overflowCount}</span>
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

export function Gallery({ game }: { game: Game }) {
  const images = galleryImages(game)
  const lightbox = useGalleryLightbox(images)
  if (images.length === 0) return null

  return (
    <>
      <GalleryGrid game={game} images={images} onOpen={lightbox.setIndex} />
      {lightbox.index !== null ? (
        <GalleryLightbox
          images={images}
          index={lightbox.index}
          naturalSize={lightbox.naturalSize}
          onClose={() => lightbox.setIndex(null)}
          onNavigate={lightbox.setIndex}
          title={game.title}
        />
      ) : null}
    </>
  )
}
