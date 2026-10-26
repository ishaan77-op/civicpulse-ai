import { useRef, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { submitResolutionReview } from '../services/resolutionservice.js'
import {
  DISPOSITIONS,
  IMAGE_ACCEPT,
  buildDispositions,
  eligibleComplaintIds,
  reviewToSupersede,
  submissionBlocker,
  toFormData,
} from '../utils/resolution.js'

// Submits completion evidence plus an audited disposition for every eligible
// linked complaint. The Chief Officer, not this form, resolves the issue.
export default function ResolutionSubmitForm({ context, userId, onSubmitted, onRefresh }) {
  const { issue, complaints, review_checklist: checklist, reviews } = context
  const eligibleIds = eligibleComplaintIds(checklist)
  const blocker = submissionBlocker({ issue, checklist, reviews }, userId)
  const replaced = reviewToSupersede(reviews, userId)

  const [note, setNote] = useState('')
  const [file, setFile] = useState(null)
  const [fileKey, setFileKey] = useState(0)
  const [entries, setEntries] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const inFlight = useRef(false)

  if (blocker) {
    return (
      <div className="resolution-form">
        <h3>Submit for Chief Officer review</h3>
        <p className="resolution-muted">{blocker}</p>
      </div>
    )
  }

  const entryFor = (id) => entries[id] || { disposition: 'Addressed', note: '' }
  const setEntry = (id, patch) => setEntries((current) => ({ ...current, [id]: { ...entryFor(id), ...patch } }))
  const titleOf = (id) => complaints.find((complaint) => complaint.id === id)?.title || `Complaint #${id}`

  const submit = async (event) => {
    event.preventDefault()
    if (inFlight.current) return
    if (!note.trim()) { setError('Add a completion note describing the finished work.'); return }
    if (!file) { setError('A final evidence photo is required.'); return }
    const { dispositions, error: dispositionError } = buildDispositions(
      eligibleIds,
      Object.fromEntries(eligibleIds.map((id) => [id, entryFor(id)])),
    )
    if (dispositionError) { setError(dispositionError); return }

    inFlight.current = true
    setSubmitting(true)
    setError('')
    setMessage('')
    try {
      const { data } = await submitResolutionReview(issue.id, toFormData({
        completion_note: note.trim(),
        image: file,
        dispositions: JSON.stringify(dispositions),
        supersedes_review_id: replaced?.id,
      }))
      setNote('')
      setFile(null)
      setFileKey((value) => value + 1)
      setEntries({})
      setMessage(data.message || 'Resolution review submitted')
      await onSubmitted?.()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not submit the resolution review.'))
      // A 409 means the issue changed underneath this form; show the latest.
      if (err.response?.status === 409) await onRefresh?.()
    } finally {
      inFlight.current = false
      setSubmitting(false)
    }
  }

  return (
    <form className="app-form resolution-form" onSubmit={submit}>
      <h3>{replaced ? 'Resubmit for Chief Officer review' : 'Submit for Chief Officer review'}</h3>
      <p className="resolution-muted">
        Only the Chief Officer can mark the issue Resolved. Once approved, the final photo and your completion note are shown to the
        citizens who reported it, so write the note for them; the per-report notes below stay internal.{replaced && ' This replaces your earlier submission, which stays in the history.'}
      </p>
      <label>
        Completion note
        <textarea rows="3" value={note} onChange={(event) => setNote(event.target.value)} disabled={submitting} />
      </label>
      <label>
        Final evidence photo (required)
        <input key={fileKey} type="file" accept={IMAGE_ACCEPT} disabled={submitting}
          onChange={(event) => setFile(event.target.files?.[0] || null)} />
      </label>
      <fieldset className="resolution-fieldset" disabled={submitting}>
        <legend>Outcome for each linked report</legend>
        {eligibleIds.map((id) => {
          const entry = entryFor(id)
          return (
            <div className="resolution-disposition-row" key={id}>
              <strong>{titleOf(id)}</strong>
              <select aria-label={`Outcome for ${titleOf(id)}`} value={entry.disposition} onChange={(event) => setEntry(id, { disposition: event.target.value })}>
                {DISPOSITIONS.map((value) => <option key={value} value={value}>{value}</option>)}
              </select>
              <input aria-label={`Note for ${titleOf(id)}`} type="text" placeholder="Short note" value={entry.note}
                onChange={(event) => setEntry(id, { note: event.target.value })} />
            </div>
          )
        })}
      </fieldset>
      {error && <p className="form-message error" role="alert">{error}</p>}
      {message && <p className="resolution-success" role="status">{message}</p>}
      <button type="submit" className="button button-primary" disabled={submitting}>
        {submitting ? 'Submitting…' : replaced ? 'Resubmit for review' : 'Submit for review'}
      </button>
    </form>
  )
}
