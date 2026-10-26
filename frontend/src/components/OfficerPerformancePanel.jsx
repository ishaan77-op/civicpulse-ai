import { useCallback, useEffect, useRef, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getMyFollowUp, getMyFollowUps, getMyRatings, submitCorrection } from '../services/performanceservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'
import { IMAGE_ACCEPT, toFormData } from '../utils/resolution.js'
import { PAGE_SIZE, followUpActions, followUpTone, stars as starText, validateCorrection } from '../utils/performance.js'
import FollowUpEvents from './FollowUpEvents.jsx'
import ProtectedImage from './ProtectedImage.jsx'
import Pager from './Pager.jsx'

// The Officer's own original submission for the job being corrected (loaded on demand).
function WorkContext({ followUpId }) {
  const [state, setState] = useState({ status: 'idle', work: null, error: '' })
  const open = async () => {
    setState({ status: 'loading', work: null, error: '' })
    try {
      const { data } = await getMyFollowUp(followUpId)
      setState({ status: 'ready', work: data.follow_up.work, error: '' })
    } catch (err) {
      setState({ status: 'error', work: null, error: apiErrorMessage(err, 'Could not load the original submission.') })
    }
  }
  if (state.status === 'idle') return <button type="button" className="button" onClick={open}>Show the original submission</button>
  if (state.status === 'loading') return <p className="page-state">Loading…</p>
  if (state.status === 'error') return <p className="form-message error" role="alert">{state.error}</p>
  return (
    <div className="rate-evidence">
      <ProtectedImage path={state.work.image_path} alt={state.work.by_this_officer ? 'Your completion evidence' : 'Completion evidence from the original submission'} />
      <p><strong>{state.work.by_this_officer ? 'Your completion note' : 'Completion note on the original submission'}:</strong> {state.work.completion_note}</p>
      <p className="resolution-muted">Submitted {formatDateTime(state.work.submitted_at)} • approved {formatDateTime(state.work.approved_at)}</p>
    </div>
  )
}

function CorrectionForm({ followUp, onSubmitted }) {
  const [note, setNote] = useState('')
  const [file, setFile] = useState(null)
  const [fileKey, setFileKey] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)

  const submit = async (event) => {
    event.preventDefault()
    if (inFlight.current) return
    const problem = validateCorrection(note)
    if (problem) { setError(problem); return }
    inFlight.current = true
    setBusy(true)
    setError('')
    try {
      await submitCorrection(followUp.id, toFormData({ note: note.trim(), image: file }))
      setNote('')
      setFile(null)
      setFileKey((value) => value + 1)
      await onSubmitted()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not submit the correction.'))
      if (err.response?.status === 409) await onSubmitted()
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <form className="app-form resolution-form" onSubmit={submit}>
      <h3>Submit your correction</h3>
      <p className="resolution-muted">Submitting sends your correction to the Chief Officer for verification. It does not close the case; only the Chief Officer can do that.</p>
      <label>What did you correct?<textarea rows="3" value={note} disabled={busy} onChange={(event) => setNote(event.target.value)} /></label>
      <label>Photo evidence (optional)
        <input key={fileKey} type="file" accept={IMAGE_ACCEPT} disabled={busy} onChange={(event) => setFile(event.target.files?.[0] || null)} />
      </label>
      {error && <p className="form-message error" role="alert">{error}</p>}
      <button type="submit" className="button button-primary" disabled={busy}>{busy ? 'Submitting…' : 'Submit correction'}</button>
    </form>
  )
}

// An Officer's own ratings and the corrections assigned to them. The API only
// ever returns this Officer's records.
export default function OfficerPerformancePanel() {
  const empty = { items: [], total: 0, limit: PAGE_SIZE, offset: 0 }
  const [state, setState] = useState({ status: 'loading', ratings: empty, followUps: empty, error: '' })
  const [offsets, setOffsets] = useState({ ratings: 0, followUps: 0 })
  const [paging, setPaging] = useState(false)

  const load = useCallback(async () => {
    try {
      const [ratings, followUps] = await Promise.all([
        getMyRatings({ limit: PAGE_SIZE, offset: offsets.ratings }),
        getMyFollowUps({ limit: PAGE_SIZE, offset: offsets.followUps }),
      ])
      const page = (data, key) => ({ items: data[key] || [], total: data.total ?? (data[key] || []).length, limit: data.limit ?? PAGE_SIZE, offset: data.offset ?? 0 })
      setState({ status: 'ready', ratings: page(ratings.data, 'ratings'), followUps: page(followUps.data, 'follow_ups'), error: '' })
    } catch (err) {
      setState((current) => ({ ...current, status: 'error', error: apiErrorMessage(err, 'Could not load your ratings and corrections.') }))
    } finally {
      setPaging(false)
    }
  }, [offsets])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const goTo = (key) => (offset) => { setPaging(true); setOffsets((current) => ({ ...current, [key]: offset })) }

  if (state.status === 'loading') return <p className="page-state">Loading your ratings and corrections…</p>
  if (state.status === 'error') {
    return <div><p className="form-message error" role="alert">{state.error}</p><button type="button" className="button" onClick={load}>Try again</button></div>
  }

  const open = state.followUps.items.filter((f) => f.status !== 'Closed')
  const done = state.followUps.items.filter((f) => f.status === 'Closed')
  return (
    <section className="officer-performance">
      <p className="resolution-kicker">Only you can see this page's contents. Ratings come from the Chief Officer and never affect your account by themselves.</p>

      <h2>Corrections assigned to you ({state.followUps.total})</h2>
      {state.followUps.total === 0 ? <p className="resolution-muted">Nothing needs correcting.</p> : (
        <>
          {open.length > 0 && (
            <div className="officer-complaint-list">
              {open.map((item) => (
                <article className="officer-card" key={item.id}>
                  <span className={`resolution-banner banner-${followUpTone(item.status)} follow-up-status`}>{item.status}</span>
                  <h3>{item.issue.category} • {item.issue.location_label || 'no location'}</h3>
                  <p><strong>Rated {starText(item.rating.stars)}:</strong> {item.rating.explanation}</p>
                  <WorkContext followUpId={item.id} />
                  <FollowUpEvents events={item.events} />
                  {item.status === 'Correction Submitted' && <p className="resolution-muted">Waiting for the Chief Officer to verify.</p>}
                  {followUpActions(item.status, 'Officer').includes('submitCorrection') && <CorrectionForm followUp={item} onSubmitted={load} />}
                </article>
              ))}
            </div>
          )}
          {done.length > 0 && (
            <details>
              <summary>Finished corrections on this page ({done.length})</summary>
              <ul className="resolution-log">{done.map((f) => <li key={f.id}><strong>{f.status}</strong> • {f.issue.category} • {formatDateTime(f.closed_at || f.updated_at)}</li>)}</ul>
            </details>
          )}
          <Pager total={state.followUps.total} limit={state.followUps.limit} offset={state.followUps.offset} disabled={paging} onChange={goTo('followUps')} />
        </>
      )}

      <h2>Your ratings ({state.ratings.total})</h2>
      {state.ratings.total === 0 ? <p className="resolution-muted">No ratings yet.</p> : (
        <>
          <ul className="resolution-log">
            {state.ratings.items.map((rating) => (
              <li key={rating.id}>
                <strong>{starText(rating.stars)}</strong>
                {!rating.is_effective && <span className="resolution-chip chip-blocked">Superseded</span>}
                <p className="resolution-muted">{rating.issue.category} • {rating.issue.location_label || 'no location'} • {formatDateTime(rating.created_at)}</p>
                {rating.explanation && <p>{rating.explanation}</p>}
              </li>
            ))}
          </ul>
          <Pager total={state.ratings.total} limit={state.ratings.limit} offset={state.ratings.offset} disabled={paging} onChange={goTo('ratings')} />
        </>
      )}
    </section>
  )
}
