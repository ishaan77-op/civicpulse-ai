import { useCallback, useEffect, useState } from 'react'
import { getEvidenceImage } from '../services/performanceservice.js'
import { evidenceErrorMessage } from '../utils/performance.js'

// Loads a staff-only or approved-evidence photo with the login token and exposes it as an object
// URL. An <img src> pointing at the API would be sent without the token, so the bytes are fetched
// and shown locally. The object URL is released when the component goes away, the path changes,
// or the load is retried, and a response that arrives after that is discarded, never turned into
// a URL nobody will release.
export function useProtectedImage(path) {
  const [result, setResult] = useState({ path: null, status: 'loading', url: '', message: '' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!path) return undefined
    const controller = new AbortController()
    let objectUrl = ''
    getEvidenceImage(path, controller.signal)
      .then(({ data }) => {
        if (controller.signal.aborted) return
        objectUrl = URL.createObjectURL(data)
        setResult({ path, status: 'ready', url: objectUrl, message: '' })
      })
      .catch((err) => {
        if (controller.signal.aborted) return
        setResult({ path, status: 'error', url: '', message: evidenceErrorMessage(err.response?.status) })
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [path, attempt])

  const retry = useCallback(() => {
    setResult({ path: null, status: 'loading', url: '', message: '' })
    setAttempt((count) => count + 1)
  }, [])

  if (!path) return { status: 'none', url: '', message: '', retry }
  if (result.path !== path) return { status: 'loading', url: '', message: '', retry }
  return { status: result.status, url: result.url, message: result.message, retry }
}
