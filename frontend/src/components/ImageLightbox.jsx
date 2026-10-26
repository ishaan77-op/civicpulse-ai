import { useEffect, useRef } from 'react'
import { useProtectedImage } from '../hooks/useProtectedImage.js'

// Full-size image viewer. Uses the same overlay/dialog pattern as the other
// modals; Escape or the Close button dismisses it, focus moves in on open and
// back to whatever opened it on close.
// Pass `src` for a public photo or `path` for a private one (fetched with the login token).
export default function ImageLightbox({ src, path, alt, caption, onClose }) {
  const closeRef = useRef(null)
  const image = useProtectedImage(path)

  useEffect(() => {
    const opener = document.activeElement
    closeRef.current?.focus()
    const onKey = (event) => {
      if (event.key === 'Escape') onClose()
      // The close button is the only control, so keep focus on it.
      if (event.key === 'Tab') { event.preventDefault(); closeRef.current?.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      if (opener instanceof HTMLElement) opener.focus()
    }
  }, [onClose])

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={caption || alt} onClick={onClose}>
      <div className="ba-lightbox" onClick={(event) => event.stopPropagation()}>
        {path
          ? (image.status === 'ready'
            ? <img src={image.url} alt={alt} />
            : <p role={image.status === 'loading' ? 'status' : 'alert'}>{image.status === 'loading' ? 'Loading photo…' : image.message}</p>)
          : <img src={src} alt={alt} />}
        {caption && <p>{caption}</p>}
        <button ref={closeRef} type="button" className="button button-primary" onClick={onClose}>Close</button>
      </div>
    </div>
  )
}
