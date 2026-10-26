import { useCallback, useEffect, useRef, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { decideResolutionReview, getResolutionQueue } from '../services/resolutionservice.js'
import { formatDateTime as formatDate } from '../utils/formatDateTime.js'
import { statusClass, statusIcon, validateRejectionReason } from '../utils/resolution.js'
import ResolutionEvidence from './ResolutionEvidence.jsx'

// Approve/reject controls for ONE pending review. Stale reviews never get
// these: the backend refuses to approve them, and the UI does not offer it.
function DecisionControls({ entry, onDecided }) {
  const { review } = entry
  const eligibleCount = entry.review_checklist.filter((item) => item.eligible).length
  const [mode, setMode] = useState('idle') // 'idle' | 'approve' | 'reject'
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)

  const decide = async (decision) => {
    if (inFlight.current) return
    if (decision === 'Rejected') {
      const problem = validateRejectionReason(reason)
      if (problem) { setError(problem); return }
    }
    inFlight.current = true
    setBusy(true)
    setError('')
    try {
      const { data } = await decideResolutionReview(review.id, decision, reason.trim())
      await onDecided(data.message || 'Decision recorded')
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not record the decision.'))
      // 404/409: the review changed under us (decided, or gone stale) - show the latest queue.
      if ([404, 409].includes(err.response?.status)) await onDecided(null)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <div className="resolution-decision">
      {mode === 'idle' && (
        <div className="resolution-actions">
          <button type="button" className="button button-primary" onClick={() => setMode('approve')}>Approve…</button>
          <button type="button" className="button button-outline-danger" onClick={() => setMode('reject')}>Reject…</button>
        </div>
      )}
      {mode === 'approve' && (
        <div className="resolution-confirm">
          <p>
            Approving marks this issue and its {eligibleCount} eligible complaint{eligibleCount === 1 ? '' : 's'} <strong>Resolved</strong>,
            rewards the reporters and notifies citizens. Excluded reports are left unchanged.
          </p>
          <div className="resolution-actions">
            <button type="button" className="button button-primary" disabled={busy} onClick={() => decide('Approved')}>
              {busy ? 'Approving…' : 'Confirm approval'}
            </button>
            <button type="button" className="button" disabled={busy} onClick={() => { setMode('idle'); setError('') }}>Cancel</button>
          </div>
        </div>
      )}
      {mode === 'reject' && (
        <div className="resolution-confirm">
          <label>
            Why is this not resolved? (sent back to the officer)
            <textarea rows="3" value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} />
          </label>
          <div className="resolution-actions">
            <button type="button" className="button button-outline-danger" disabled={busy} onClick={() => decide('Rejected')}>
              {busy ? 'Rejecting…' : 'Reject and return for more work'}
            </button>
            <button type="button" className="button" disabled={busy} onClick={() => { setMode('idle'); setError('') }}>Cancel</button>
          </div>
        </div>
      )}
      {error && <p className="form-message error" role="alert">{error}</p>}
    </div>
  )
}

function QueueCard({ entry, children }) {
  const { issue, review } = entry
  return (
    <article className="officer-card resolution-card">
      <div className="officer-card-header">
        <div>
          <span className="complaint-category">{issue.category || 'General'}</span>
          <span className={`status-pill ${statusClass(issue.status)}`}>{statusIcon(issue.status)} {issue.status}</span>
          <h2>{issue.location_label || 'Location not provided'}</h2>
          <p className="officer-meta">
            {issue.report_count} report{issue.report_count === 1 ? '' : 's'} &bull; Review #{review.id} submitted {formatDate(review.submitted_at)}
          </p>
        </div>
      </div>
      {children}
      <details>
        <summary>Reports and evidence</summary>
        <ResolutionEvidence complaints={entry.complaints} checklist={entry.review_checklist} review={review} />
      </details>
    </article>
  )
}

export default function ResolutionQueue() {
  const [state, setState] = useState({ status: 'loading', queue: [], stale: [], error: '', code: null })
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const { data } = await getResolutionQueue()
      setState({ status: 'ready', queue: data.queue || [], stale: data.stale || [], error: '', code: null })
    } catch (err) {
      setState((current) => ({
        ...current,
        status: 'error',
        code: err.response?.status ?? null,
        error: err.response?.status === 403
          ? 'Only a Chief Officer can review resolutions. If your role changed recently, sign out and back in.'
          : apiErrorMessage(err, 'Could not load the resolution queue.'),
      }))
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const decided = async (message) => {
    if (message) setNotice(message)
    await load()
  }

  if (state.status === 'loading') return <p className="page-state">Loading resolution reviews…</p>
  if (state.status === 'error') {
    return (
      <div>
        <p className="form-message error" role="alert">{state.error}</p>
        {state.code !== 403 && <button type="button" className="button" onClick={load}>Try again</button>}
      </div>
    )
  }

  const { queue, stale } = state
  return (
    <div className="resolution-queue">
      {notice && <p className="resolution-success" role="status">{notice}</p>}

      <section aria-labelledby="pending-heading">
        <h2 id="pending-heading">Awaiting your decision ({queue.length})</h2>
        {queue.length === 0 ? (
          <div className="empty-state">
            <h2>Nothing is waiting for approval</h2>
            <p>Officers’ completed work will appear here for your decision.</p>
          </div>
        ) : (
          <div className="officer-complaint-list">
            {queue.map((entry) => (
              <QueueCard key={entry.review.id} entry={entry}>
                <DecisionControls entry={entry} onDecided={decided} />
              </QueueCard>
            ))}
          </div>
        )}
      </section>

      <section aria-labelledby="stale-heading">
        <h2 id="stale-heading">Withdrawn: new information arrived ({stale.length})</h2>
        <p className="resolution-muted">
          These reviews can no longer be approved. The issue stays in Pending Review until the officer resubmits.
        </p>
        {stale.length === 0 ? <p className="resolution-muted">No withdrawn reviews.</p> : (
          <div className="officer-complaint-list">
            {stale.map((entry) => (
              <QueueCard key={entry.review.id} entry={entry}>
                <div className="resolution-banner banner-stale" role="status">
                  <strong>Cannot be approved</strong> <span className="resolution-muted">withdrawn {formatDate(entry.review.stale_at)}</span>
                  <p>{entry.review.stale_reason || 'The issue changed after this review was submitted.'}</p>
                </div>
              </QueueCard>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
