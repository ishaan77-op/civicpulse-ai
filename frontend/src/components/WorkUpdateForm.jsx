import { useRef, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { createWorkUpdate } from '../services/resolutionservice.js'
import { IMAGE_ACCEPT, OFFICER_SETTABLE_STATUSES, newIdempotencyKey, toFormData, validateWorkUpdate } from '../utils/resolution.js'

// Records field-work progress against the shared issue. Completion evidence
// for the Chief Officer is submitted separately (ResolutionSubmitForm).
export default function WorkUpdateForm({ issueId, complaints, onSaved }) {
  const [note, setNote] = useState('')
  const [status, setStatus] = useState('In Progress')
  const [complaintId, setComplaintId] = useState('')
  const [file, setFile] = useState(null)
  const [fileKey, setFileKey] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const inFlight = useRef(false)
  // One key per distinct payload: a retry after a network failure replays the
  // same key (the server answers with the stored update instead of a copy);
  // editing any field starts a new key.
  const keyRef = useRef(null)

  const edit = (setter) => (event) => {
    keyRef.current = null
    setMessage('')
    setter(event.target.value)
  }

  const submit = async (event) => {
    event.preventDefault()
    if (inFlight.current) return
    const problem = validateWorkUpdate({ note, status })
    if (problem) { setError(problem); return }

    inFlight.current = true
    setSubmitting(true)
    setError('')
    setMessage('')
    if (!keyRef.current) keyRef.current = newIdempotencyKey()
    try {
      const { data } = await createWorkUpdate(
        issueId,
        toFormData({ note: note.trim(), status, complaint_id: complaintId, image: file }),
        keyRef.current,
      )
      keyRef.current = null
      setNote('')
      setComplaintId('')
      setFile(null)
      setFileKey((value) => value + 1)
      setMessage(data.message || 'Work update recorded')
      await onSaved?.()
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not record the work update.'))
    } finally {
      inFlight.current = false
      setSubmitting(false)
    }
  }

  return (
    <form className="app-form resolution-form" onSubmit={submit}>
      <h3>Record field work</h3>
      <p className="resolution-muted">
        Progress notes and photos are internal to NMC staff. Saving an update withdraws any
        review still awaiting the Chief Officer, because the evidence has changed.
      </p>
      <label>
        What was done
        <textarea rows="3" value={note} onChange={edit(setNote)} disabled={submitting} />
      </label>
      <div className="resolution-form-row">
        <label>
          Issue status
          <select value={status} onChange={edit(setStatus)} disabled={submitting}>
            {OFFICER_SETTABLE_STATUSES.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
        </label>
        <label>
          About
          <select value={complaintId} onChange={edit(setComplaintId)} disabled={submitting}>
            <option value="">Whole issue</option>
            {complaints.map((complaint) => <option key={complaint.id} value={complaint.id}>{complaint.title}</option>)}
          </select>
        </label>
      </div>
      <label>
        Progress photo (optional)
        <input
          key={fileKey}
          type="file"
          accept={IMAGE_ACCEPT}
          disabled={submitting}
          onChange={(event) => { keyRef.current = null; setMessage(''); setFile(event.target.files?.[0] || null) }}
        />
      </label>
      {error && <p className="form-message error" role="alert">{error}</p>}
      {message && <p className="resolution-success" role="status">{message}</p>}
      <button type="submit" className="button button-primary" disabled={submitting}>
        {submitting ? 'Saving…' : 'Save work update'}
      </button>
    </form>
  )
}
