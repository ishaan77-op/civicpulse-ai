import { useEffect, useState } from 'react'
import { getEvidenceImage } from '../services/performanceservice.js'
import { evidenceErrorMessage } from '../utils/performance.js'

// A staff-only photo. It cannot be an <img src> to the API (the browser would not
// send the login token), so the bytes are fetched with the token and shown from an
// object URL, which is released when the photo goes away or its path changes.
export default function ProtectedImage({ path, alt }) {
  const [state, setState] = useState({ status: 'loading', url: '', message: '' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl = ''
    getEvidenceImage(path, controller.signal)
      .then(({ data }) => {
        objectUrl = URL.createObjectURL(data)
        setState({ status: 'ready', url: objectUrl, message: '' })
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setState({ status: 'error', url: '', message: evidenceErrorMessage(err.response?.status) })
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path, attempt])

  if (state.status === 'loading') return <p className="resolution-muted" role="status">Loading photo…</p>
  if (state.status === 'error') {
    return (
      <p className="resolution-muted" role="alert">
        {state.message}{' '}
        <button type="button" className="button" onClick={() => { setState({ status: 'loading', url: '', message: '' }); setAttempt((n) => n + 1) }}>Try again</button>
      </p>
    )
  }
  return <img src={state.url} alt={alt} />
}
