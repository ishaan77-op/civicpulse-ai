import { useCallback, useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getRejectedComplaints, reopenRejectedComplaint } from '../services/complaintservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'

function RejectedComplaintsList({ onDecision }) {
  const [reports, setReports] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [reopeningId, setReopeningId] = useState(null)

  const fetchReports = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const { data } = await getRejectedComplaints()
      setReports(data.complaints || [])
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to load rejected complaints.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(fetchReports, 0)
    return () => window.clearTimeout(timer)
  }, [fetchReports])

  const reopen = async (id) => {
    try {
      setActionError('')
      setReopeningId(id)
      await reopenRejectedComplaint(id)
      setReports((current) => current.filter((report) => report.id !== id))
      onDecision?.(id, 'Reopened')
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Failed to reopen that complaint.'))
    } finally {
      setReopeningId(null)
    }
  }

  return (
    <section>
      <p className="dashboard-kicker">
        Complaints an Officer/Admin rejected as outside NMC/government jurisdiction. These may be
        genuine reports - they are simply not municipal responsibility. A rejection here never
        affects the citizen's spam standing and can always be reopened for another look.
      </p>

      {actionError && <p className="form-message error" role="alert">{actionError}</p>}

      {loading ? (
        <p className="page-state">Loading rejected complaints...</p>
      ) : error ? (
        <p className="form-message error" role="alert">{error}</p>
      ) : reports.length === 0 ? (
        <div className="empty-state">
          <h2>No rejected complaints</h2>
          <p>Nothing has been rejected as out-of-scope yet.</p>
        </div>
      ) : (
        <div className="officer-complaint-list">
          {reports.map((report) => (
            <article className="officer-card" key={report.id}>
              <div className="officer-card-header">
                <div>
                  <span className="complaint-category">{report.category || 'General'}</span>
                  <h2>{report.title}</h2>
                  <p className="officer-meta">
                    📍 {report.location} &bull; Reported {formatDateTime(report.created_at)}
                  </p>
                  {report.rejection?.reviewed_at && (
                    <p className="officer-meta">
                      Rejected {formatDateTime(report.rejection.reviewed_at)}
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

              {report.rejection && (
                <div className="officer-ai-strip">
                  <div><strong>Reason:</strong> {report.rejection.reason}</div>
                  {report.rejection.explanation && (
                    <div><strong>Explanation:</strong> {report.rejection.explanation}</div>
                  )}
                </div>
              )}

              <div className="status-action-box">
                <button
                  type="button"
                  className="button"
                  disabled={reopeningId === report.id}
                  onClick={() => reopen(report.id)}
                >
                  Reopen for Review
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

export default RejectedComplaintsList
