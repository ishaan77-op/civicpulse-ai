import { useCallback, useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getSpamReports, reopenSpamReport, reviewSpamReport } from '../services/complaintservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'

const STATUS_FILTERS = ['Pending', 'Confirmed', 'Rejected']

function SpamReviewList({ onDecision }) {
  const [statusFilter, setStatusFilter] = useState('Pending')
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [decidingId, setDecidingId] = useState(null)

  const fetchReports = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const { data } = await getSpamReports({ status: statusFilter })
      setReports(data.complaints || [])
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to load flagged reports.'))
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    const timer = window.setTimeout(fetchReports, 0)
    return () => window.clearTimeout(timer)
  }, [fetchReports])

  const decide = async (id, decision) => {
    try {
      setActionError('')
      setDecidingId(id)
      await reviewSpamReport(id, decision)
      setReports((current) => current.filter((report) => report.id !== id))
      onDecision?.(id, decision)
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Failed to record that decision.'))
    } finally {
      setDecidingId(null)
    }
  }

  const reopen = async (id) => {
    try {
      setActionError('')
      setDecidingId(id)
      await reopenSpamReport(id)
      setReports((current) => current.filter((report) => report.id !== id))
      onDecision?.(id, 'Reopened')
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Failed to reopen that report.'))
    } finally {
      setDecidingId(null)
    }
  }

  return (
    <section>
      <p className="dashboard-kicker">
        Reports the AI flagged as a likely mismatch between the photo/description and the claimed issue.
        A human decision here can always be corrected later by reopening it.
      </p>

      <div className="filter-group">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          {STATUS_FILTERS.map((status) => (
            <option key={status} value={status}>
              {status === 'Pending' ? 'Pending review' : status === 'Confirmed' ? 'Confirmed spam' : 'Not spam / legitimate'}
            </option>
          ))}
        </select>
      </div>

      {actionError && <p className="form-message error" role="alert">{actionError}</p>}

      {loading ? (
        <p className="page-state">Loading flagged reports...</p>
      ) : error ? (
        <p className="form-message error" role="alert">{error}</p>
      ) : reports.length === 0 ? (
        <div className="empty-state">
          <h2>No reports here</h2>
          <p>
            {statusFilter === 'Pending'
              ? 'Nothing is currently pending spam review.'
              : 'No reports currently have this decision.'}
          </p>
        </div>
      ) : (
        <div className="officer-complaint-list">
          {reports.map((report) => (
            <article className="officer-card" key={report.id}>
              <div className="officer-card-header">
                <div>
                  <span className="complaint-category">{report.category || 'General'}</span>
                  {report.spam_review?.ai_spam_confidence && (
                    <span className="priority-tag">
                      {report.spam_review.ai_spam_confidence} confidence
                    </span>
                  )}
                  <h2>{report.title}</h2>
                  <p className="officer-meta">
                    📍 {report.location} &bull; Reported {formatDateTime(report.created_at)}
                  </p>
                  {report.spam_review?.spam_reviewed_at && (
                    <p className="officer-meta">
                      Reviewed {formatDateTime(report.spam_review.spam_reviewed_at)}
                    </p>
                  )}
                  {report.spam_review?.spam_reopened_at && (
                    <p className="officer-meta">
                      Reopened {formatDateTime(report.spam_review.spam_reopened_at)}
                    </p>
                  )}
                </div>
              </div>

              <p className="officer-card-desc">{report.description}</p>

              {report.image_url && (
                <div className="officer-card-thumb">
                  <img src={report.image_url} alt={report.title} />
                </div>
              )}

              {report.spam_review?.ai_spam_reason && (
                <div className="officer-ai-strip">
                  <div><strong>AI flag reason:</strong> {report.spam_review.ai_spam_reason}</div>
                </div>
              )}

              <div className="status-action-box">
                {statusFilter === 'Pending' ? (
                  <>
                    <button
                      type="button"
                      className="button button-primary"
                      disabled={decidingId === report.id}
                      onClick={() => decide(report.id, 'Confirmed')}
                    >
                      Confirm Spam
                    </button>
                    <button
                      type="button"
                      className="button"
                      disabled={decidingId === report.id}
                      onClick={() => decide(report.id, 'Rejected')}
                    >
                      Not Spam
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="button"
                    disabled={decidingId === report.id}
                    onClick={() => reopen(report.id)}
                  >
                    Reopen for Review
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

export default SpamReviewList
