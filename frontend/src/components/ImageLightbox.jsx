import { useEffect, useRef } from 'react'

// Full-size image viewer. Uses the same overlay/dialog pattern as the other
// modals; Escape or the Close button dismisses it, focus moves in on open and
// back to whatever opened it on close.
export default function ImageLightbox({ src, alt, caption, onClose }) {
  const closeRef = useRef(null)

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
        <img src={src} alt={alt} />
        {caption && <p>{caption}</p>}
        <button ref={closeRef} type="button" className="button button-primary" onClick={onClose}>Close</button>
      </div>
    </div>
  )
}
