import { useCallback, useContext, useEffect, useState } from 'react'
import { AuthContext } from '../context/authcontextvalue.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getIssueResolutionContext, getWorkUpdates } from '../services/resolutionservice.js'
import { formatDateTime as formatDate } from '../utils/formatDateTime.js'
import { reviewStateSummary, statusClass, statusIcon } from '../utils/resolution.js'
import ResolutionEvidence from './ResolutionEvidence.jsx'
import ResolutionSubmitForm from './ResolutionSubmitForm.jsx'
import WorkUpdateForm from './WorkUpdateForm.jsx'

// Officer/Admin workspace for one civic issue: the original reports, the
// field-work log, the current review state, and the two submission forms.
export default function IssueWorkPanel({ issueId, onChanged }) {
  const { user } = useContext(AuthContext)
  const [data, setData] = useState({ status: 'loading', context: null, updates: [], error: '' })

  const load = useCallback(async () => {
    try {
      const [contextRes, updatesRes] = await Promise.all([getIssueResolutionContext(issueId), getWorkUpdates(issueId)])
      setData({ status: 'ready', context: contextRes.data, updates: updatesRes.data.work_updates || [], error: '' })
    } catch (err) {
      setData((current) => ({ ...current, status: 'error', error: apiErrorMessage(err, 'Could not load this issue’s field-work details.') }))
    }
  }, [issueId])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const refresh = useCallback(async () => {
    await load()
    onChanged?.()
  }, [load, onChanged])

  if (data.status === 'loading') return <p className="page-state">Loading field-work details…</p>
  if (data.status === 'error') {
    return (
      <div>
        <p className="form-message error" role="alert">{data.error}</p>
        <button type="button" className="button" onClick={load}>Try again</button>
      </div>
    )
  }

  const { context, updates } = data
  const { issue, complaints, review_checklist: checklist, reviews } = context
  const summary = reviewStateSummary(reviews[0])
  const summaryTime = reviews[0]?.stale_at || reviews[0]?.reviewed_at || reviews[0]?.submitted_at

  return (
    <div className="issue-work-panel">
      <p>
        Issue status: <span className={`status-pill ${statusClass(issue.status)}`}>{statusIcon(issue.status)} {issue.status}</span>
      </p>
      {summary && (
        <div className={`resolution-banner banner-${summary.tone}`} role="status">
          <strong>{summary.title}</strong> <span className="resolution-muted">{formatDate(summaryTime)}</span>
          {summary.detail && <p>{summary.detail}</p>}
        </div>
      )}

      <ResolutionEvidence complaints={complaints} checklist={checklist} review={reviews[0] || null} />

      <section aria-label="Field-work log">
        <h3>Field-work log ({updates.length})</h3>
        {updates.length === 0 ? <p className="resolution-muted">No field work recorded yet.</p> : (
          <ul className="resolution-log">
            {updates.map((update) => (
              <li key={update.id}>
                <strong>{update.status}</strong> &bull; {formatDate(update.created_at)}
                <p>{update.note}</p>
                {update.image_url && <img src={update.image_url} alt="Field-work progress evidence" loading="lazy" />}
              </li>
            ))}
          </ul>
        )}
      </section>

      {reviews.length > 0 && (
        <details>
          <summary>Review history ({reviews.length})</summary>
          <ul className="resolution-log">
            {reviews.map((review) => (
              <li key={review.id}>
                <strong>{review.state}</strong> &bull; submitted {formatDate(review.submitted_at)}
                {review.stale_reason && <p>Withdrawn {formatDate(review.stale_at)}: {review.stale_reason}</p>}
                {review.rejection_reason && <p>Returned {formatDate(review.reviewed_at)}: {review.rejection_reason}</p>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {issue.status !== 'Resolved' && <WorkUpdateForm issueId={issue.id} complaints={complaints} onSaved={refresh} />}
      <ResolutionSubmitForm context={context} userId={user?.id} onSubmitted={refresh} onRefresh={load} />
    </div>
  )
}
