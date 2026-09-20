import { useCallback, useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getIssues, updateIssueStatus } from '../services/complaintservice.js'
import { formatDateTime as formatDate } from '../utils/formatDateTime.js'

function IssueClusterList() {
  const [issues, setIssues] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [updatingId, setUpdatingId] = useState(null)

  const fetchIssues = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const params = {}
      if (statusFilter) params.status = statusFilter
      const { data } = await getIssues(params)
      setIssues(data.issues || [])
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to load issue clusters.'))
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    const timer = window.setTimeout(fetchIssues, 0)
    return () => window.clearTimeout(timer)
  }, [fetchIssues])

  const handleStatusChange = async (id, newStatus) => {
    try {
      setActionError('')
      setUpdatingId(id)
      await updateIssueStatus(id, newStatus)
      await fetchIssues()
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Failed to update issue status.'))
    } finally {
      setUpdatingId(null)
    }
  }

  return (
    <section>
      <p className="dashboard-kicker">
        Reports the AI grouped together as likely the same underlying civic issue - work the issue, not each duplicate.
      </p>

      <div className="filter-group">
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          <option value="Pending">Pending</option>
          <option value="In Progress">In Progress</option>
          <option value="Resolved">Resolved</option>
        </select>
      </div>

      {actionError && <p className="form-message error" role="alert">{actionError}</p>}

      {loading ? (
        <p className="page-state">Loading issue clusters...</p>
      ) : error ? (
        <p className="form-message error" role="alert">{error}</p>
      ) : issues.length === 0 ? (
        <div className="empty-state">
          <h2>No issue clusters yet</h2>
          <p>Grouped civic issues will appear here as complaints come in.</p>
        </div>
      ) : (
        <div className="officer-complaint-list">
          {issues.map((issue) => (
            <article className="officer-card" key={issue.id}>
              <div className="officer-card-header">
                <div>
                  <span className="complaint-category">{issue.category || 'General'}</span>
                  <span className="priority-tag">{issue.report_count} report{issue.report_count === 1 ? '' : 's'}</span>
                  <h2>{issue.location_label || 'Location not provided'}</h2>
                  <p className="officer-meta">
                    Opened {formatDate(issue.created_at)} &bull; Updated {formatDate(issue.updated_at)}
                  </p>
                </div>

                <div className="status-action-box">
                  <label htmlFor={`issue-status-${issue.id}`} className="visually-hidden">
                    Status for issue {issue.id}
                  </label>
                  <select
                    id={`issue-status-${issue.id}`}
                    value={issue.status || 'Pending'}
                    onChange={(e) => handleStatusChange(issue.id, e.target.value)}
                    disabled={updatingId === issue.id}
                    className={`status-select status-select-${(issue.status || 'Pending').toLowerCase().replace(' ', '-')}`}
                  >
                    <option value="Pending">🟡 Pending</option>
                    <option value="In Progress">🔵 In Progress</option>
                    <option value="Resolved">🟢 Resolved</option>
                  </select>
                </div>
              </div>

              {issue.ai_summary && (
                <p className="officer-card-desc">{issue.ai_summary}</p>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

export default IssueClusterList
