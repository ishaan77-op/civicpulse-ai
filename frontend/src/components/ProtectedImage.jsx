import { useProtectedImage } from '../hooks/useProtectedImage.js'

// A private photo (field work, completion evidence, corrections). See useProtectedImage.
export default function ProtectedImage({ path, alt }) {
  const image = useProtectedImage(path)

  if (image.status === 'loading') return <p className="resolution-muted" role="status">Loading photo…</p>
  if (image.status === 'error' || image.status === 'none') {
    return (
      <p className="resolution-muted" role="alert">
        {image.message || 'The photo could not be loaded.'}{' '}
        {image.status === 'error' && <button type="button" className="button" onClick={image.retry}>Try again</button>}
      </p>
    )
  }
  return <img src={image.url} alt={alt} />
}
