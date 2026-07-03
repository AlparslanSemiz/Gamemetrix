import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import './TrailerModal.css'

interface TrailerModalProps {
  title: string
  videoId: string | null
  loading: boolean
  onClose: () => void
}

export function TrailerModal({ title, videoId, loading, onClose }: TrailerModalProps) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const searchUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(`${title} official trailer game`)}`

  return createPortal(
    <div className="trailer-modal" role="dialog" aria-modal="true" aria-label={`${title} trailer`}>
      <button
        type="button"
        className="trailer-modal-backdrop"
        aria-label="Close trailer"
        onClick={onClose}
      />
      <div className="trailer-modal-panel">
        <div className="trailer-modal-heading">
          <h2>{title}</h2>
          <button type="button" aria-label="Close trailer" onClick={onClose}>
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {loading ? (
          <div className="trailer-modal-msg">Loading trailer…</div>
        ) : videoId ? (
          <iframe
            title={`${title} trailer`}
            src={`https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0`}
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        ) : (
          <a
            className="trailer-modal-msg trailer-modal-fallback"
            href={searchUrl}
            target="_blank"
            rel="noreferrer"
          >
            Open trailer search on YouTube
          </a>
        )}
      </div>
    </div>,
    document.body,
  )
}
