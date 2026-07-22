/* eslint-disable react-hooks/set-state-in-effect */
import { type CSSProperties, type SyntheticEvent, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import type { Game } from '../../types/game'
import { fallbackCoverUrl, galleryImages, looksLikePlaceholderImage, thumbnailUrl } from '../../utils/coverImage'

const GALLERY_INLINE_LIMIT = 14
// Screenshots above the fold are worth the extra connections; the rest wait for
// the scroll so a 14-image gallery does not compete with the hero.
const GALLERY_EAGER_LIMIT = 4

// A CDN can miss the scaled variant even when the original exists, so retry with
// the full-size URL once before giving up on the frame.
function thumbErrorHandler(fullUrl: string) {
  return (event: SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget
    if (img.src !== fullUrl) {
      img.src = fullUrl
      return
    }
    img.parentElement?.style.setProperty('display', 'none')
  }
}

export function Gallery({ game }: { game: Game }) {
  const images = galleryImages(game)
  const inlineImages = images.slice(0, Math.min(images.length, GALLERY_INLINE_LIMIT))
  const overflowCount = Math.max(0, images.length - GALLERY_INLINE_LIMIT)
  const overflowImage = overflowCount > 0 ? images[GALLERY_INLINE_LIMIT] : null

  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null)
  const [naturalSize, setNaturalSize] = useState<{ width: number; height: number } | null>(null)
  // Steam serves a grey logo capsule for apps with no key art; its URL looks
  // ordinary, so we only learn it is a placeholder once it decodes small/square.
  const [heroFallback, setHeroFallback] = useState<string | null>(null)

  useEffect(() => {
    if (lightboxIndex === null) return
    setNaturalSize(null)
    document.body.style.overflow = 'hidden'
    const count = images.length
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setLightboxIndex(null)
      else if (e.key === 'ArrowRight') setLightboxIndex((p) => p === null ? null : (p + 1) % count)
      else if (e.key === 'ArrowLeft')  setLightboxIndex((p) => p === null ? null : (p - 1 + count) % count)
    }
    window.addEventListener('keydown', onKey)
    return () => { document.body.style.overflow = ''; window.removeEventListener('keydown', onKey) }
  }, [lightboxIndex, images.length])

  useEffect(() => {
    if (lightboxIndex === null) return
    const img = new Image()
    img.onload = () => setNaturalSize({ width: img.naturalWidth, height: img.naturalHeight })
    img.src = images[lightboxIndex]
  }, [images, lightboxIndex])

  // Warm the neighbours so arrow-key browsing does not blank out between frames.
  useEffect(() => {
    if (lightboxIndex === null || images.length < 2) return
    const count = images.length
    for (const offset of [1, -1]) {
      const neighbour = new Image()
      neighbour.src = images[(lightboxIndex + offset + count) % count]
    }
  }, [images, lightboxIndex])

  if (images.length === 0) return null

  const [first, ...rest] = inlineImages
  const lightbox = lightboxIndex !== null
    ? createPortal(
        <div className="dp-lightbox" role="dialog" aria-modal="true">
          <button
            type="button"
            className="dp-lightbox-backdrop"
            aria-label="Close"
            onClick={() => setLightboxIndex(null)}
          />
          <div className="dp-lightbox-stage">
            <img
              src={images[lightboxIndex]}
              alt={`${game.title} ${lightboxIndex === 0 ? 'cover' : `screenshot ${lightboxIndex}`}`}
              className="dp-lightbox-img"
              style={naturalSize ? {
                '--natural-width': `${naturalSize.width}px`,
                '--natural-height': `${naturalSize.height}px`,
              } as CSSProperties : undefined}
            />
          </div>
          <button type="button" className="dp-lightbox-close" onClick={() => setLightboxIndex(null)}>✕</button>
          {images.length > 1 && (
            <>
              <button
                type="button"
                className="dp-lightbox-nav dp-lightbox-prev"
                onClick={() => setLightboxIndex((lightboxIndex - 1 + images.length) % images.length)}
                aria-label="Previous image"
              >‹</button>
              <button
                type="button"
                className="dp-lightbox-nav dp-lightbox-next"
                onClick={() => setLightboxIndex((lightboxIndex + 1) % images.length)}
                aria-label="Next image"
              >›</button>
            </>
          )}
          <div className="dp-lightbox-counter">{lightboxIndex + 1} / {images.length}</div>
        </div>,
        document.body,
      )
    : null

  return (
    <>
      <div className="dp-gallery">
        <div className="dp-gallery-heading">
          <span>Media</span>
          <div className="dp-gallery-count-wrap">
            <button type="button" className="dp-gallery-count" onClick={() => setLightboxIndex(0)}>
              {images.length} {images.length === 1 ? 'image' : 'images'}
            </button>
            <div className="dp-gallery-strip" aria-label={`${game.title} media thumbnails`}>
              {images.map((url, index) => (
                <button
                  type="button"
                  key={`${url}-${index}`}
                  className="dp-gallery-strip-item"
                  onClick={() => setLightboxIndex(index)}
                  aria-label={`Open image ${index + 1}`}
                >
                  {/* Same thumbnail URL as the grid below, so the strip costs no extra bytes. */}
                  <img
                    src={thumbnailUrl(url)}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    onError={thumbErrorHandler(url)}
                  />
                </button>
              ))}
            </div>
          </div>
        </div>
        <button type="button" className="dp-gallery-main" onClick={() => setLightboxIndex(0)}>
          <img
            src={heroFallback ?? first}
            alt={`${game.title} cover`}
            className="dp-gallery-hero"
            loading="eager"
            decoding="async"
            fetchPriority="high"
            onLoad={(e) => {
              if (heroFallback) return
              if (looksLikePlaceholderImage(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)) {
                setHeroFallback(images.find((url) => url !== first) ?? fallbackCoverUrl(game.title))
              }
            }}
            onError={() => setHeroFallback(fallbackCoverUrl(game.title))}
          />
          <div className="dp-gallery-zoom-hint">🔍</div>
        </button>
        {(rest.length > 0 || overflowImage) && (
          <div className="dp-gallery-rest">
            {rest.map((url, i) => (
              <button type="button" key={url} className="dp-gallery-img" onClick={() => setLightboxIndex(i + 1)}>
                <img
                  src={thumbnailUrl(url)}
                  alt={`${game.title} screenshot ${i + 2}`}
                  loading={i + 1 < GALLERY_EAGER_LIMIT ? 'eager' : 'lazy'}
                  decoding="async"
                  onError={thumbErrorHandler(url)}
                />
              </button>
            ))}
            {overflowImage && (
              <button
                type="button"
                className="dp-gallery-img dp-gallery-more"
                onClick={() => setLightboxIndex(GALLERY_INLINE_LIMIT)}
                aria-label={`Open ${overflowCount} more images`}
              >
                <img
                  src={thumbnailUrl(overflowImage)}
                  alt={`${game.title} screenshot ${GALLERY_INLINE_LIMIT + 1}`}
                  loading="lazy"
                  decoding="async"
                  onError={thumbErrorHandler(overflowImage)}
                />
                <span>+{overflowCount}</span>
              </button>
            )}
          </div>
        )}
      </div>

      {lightbox}
    </>
  )
}
