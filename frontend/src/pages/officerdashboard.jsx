import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/appshell.jsx'
import HeatmapView from '../components/HeatmapView.jsx'
import SpamReviewList from '../components/SpamReviewList.jsx'
import IssueClusterList from '../components/IssueClusterList.jsx'
import RejectedComplaintsList from '../components/RejectedComplaintsList.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getHeatmapData, getOfficerComplaints, getOfficerStats, rejectComplaint, updateComplaintStatus } from '../services/complaintservice.js'
import { formatDateTime as formatDate } from '../utils/formatDateTime.js'

const REJECTION_REASONS = [
  'Private Property',
  'Private Society / Apartment',
  'Outside NMC Jurisdiction',
  'Not a Municipal Responsibility',
  'Other',
]

export default function OfficerDashboard() {
  const [complaints, setComplaints] = useState([])
  const [stats, setStats] = useState({ total_complaints: 0, pending: 0, in_progress: 0, resolved: 0 })
  const [statusFilter, setStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [updatingId, setUpdatingId] = useState(null)
  const [view, setView] = useState('list') // 'list' | 'heatmap' | 'spam' | 'issues'
  const [heatmapPoints, setHeatmapPoints] = useState([])
  const [heatmapLoading, setHeatmapLoading] = useState(false)
  const [heatmapError, setHeatmapError] = useState('')
  const [rejectModalId, setRejectModalId] = useState(null)
  const [rejectReason, setRejectReason] = useState('')
  const [rejectExplanation, setRejectExplanation] = useState('')
  const [rejectSubmitting, setRejectSubmitting] = useState(false)
  const [rejectError, setRejectError] = useState('')

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const params = {}
      if (statusFilter) params.status = statusFilter
      if (categoryFilter) params.category = categoryFilter

      const [complaintsRes, statsRes] = await Promise.all([
        getOfficerComplaints(params),
        getOfficerStats()
      ])

      setComplaints(complaintsRes.data.complaints || [])
      setStats(statsRes.data || { total_complaints: 0, pending: 0, in_progress: 0, resolved: 0 })
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to load officer dashboard data.'))
    } finally {
      setLoading(false)
    }
  }, [statusFilter, categoryFilter])

  useEffect(() => {
    const timer = window.setTimeout(fetchData, 0)
    return () => window.clearTimeout(timer)
  }, [fetchData])

  const fetchHeatmap = useCallback(async () => {
    try {
      setHeatmapLoading(true)
      setHeatmapError('')
      const { data } = await getHeatmapData({ status: 'Pending' })
      const pending = data.points || []
      const { data: inProgressData } = await getHeatmapData({ status: 'In Progress' })
      setHeatmapPoints([...pending, ...(inProgressData.points || [])])
    } catch (err) {
      setHeatmapError(apiErrorMessage(err, 'Failed to load the heatmap.'))
    } finally {
      setHeatmapLoading(false)
    }
  }, [])

  useEffect(() => {
    if (view !== 'heatmap') return undefined
    const timer = window.setTimeout(fetchHeatmap, 0)
    return () => window.clearTimeout(timer)
  }, [view, fetchHeatmap])

  const handleStatusChange = async (id, newStatus) => {
    try {
      setActionError('')
      setUpdatingId(id)
      await updateComplaintStatus(id, newStatus)
      await fetchData()
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Failed to update complaint status.'))
    } finally {
      setUpdatingId(null)
    }
  }

  const openRejectModal = (id) => {
    setRejectModalId(id)
    setRejectReason('')
    setRejectExplanation('')
    setRejectError('')
  }

  const closeRejectModal = () => {
    if (rejectSubmitting) return
    setRejectModalId(null)
  }

  const submitRejection = async () => {
    if (!rejectReason) {
      setRejectError('Please select a reason.')
      return
    }
    if (rejectReason === 'Other' && !rejectExplanation.trim()) {
      setRejectError('Please provide a short explanation.')
      return
    }

    try {
      setRejectSubmitting(true)
      setRejectError('')
      await rejectComplaint(rejectModalId, rejectReason, rejectExplanation.trim())
      setRejectModalId(null)
      await fetchData()
    } catch (err) {
      setRejectError(apiErrorMessage(err, 'Failed to reject this complaint.'))
    } finally {
      setRejectSubmitting(false)
    }
  }

  const filteredComplaints = complaints.filter(c => {
    if (!searchQuery) return true
    const q = searchQuery.toLowerCase()
    return c.title?.toLowerCase().includes(q) ||
           c.description?.toLowerCase().includes(q) ||
           c.location?.toLowerCase().includes(q) ||
           c.category?.toLowerCase().includes(q)
  })

  return (
    <AppShell eyebrow="Municipal Operations" title="Officer Dashboard">
      {/* Overview Metric Cards */}
      <section className="officer-stats-grid">
        <div className="stat-card">
          <span className="stat-label">Total Assigned</span>
          <strong className="stat-value">{stats.total_complaints}</strong>
        </div>
        <div className="stat-card stat-pending">
          <span className="stat-label">Pending Triage</span>
          <strong className="stat-value">{stats.pending}</strong>
        </div>
        <div className="stat-card stat-progress">
          <span className="stat-label">In Progress</span>
          <strong className="stat-value">{stats.in_progress}</strong>
        </div>
        <div className="stat-card stat-resolved">
          <span className="stat-label">Resolved Issues</span>
          <strong className="stat-value">{stats.resolved}</strong>
        </div>
      </section>

      {/* View Toggle */}
      <div className="admin-tabs">
        <button
          className={`tab-btn ${view === 'list' ? 'active' : ''}`}
          onClick={() => setView('list')}
        >
          📋 List View
        </button>
        <button
          className={`tab-btn ${view === 'heatmap' ? 'active' : ''}`}
          onClick={() => setView('heatmap')}
        >
          🗺️ Damage Heatmap
        </button>
        <button
          className={`tab-btn ${view === 'spam' ? 'active' : ''}`}
          onClick={() => setView('spam')}
        >
          🚩 Spam Review
        </button>
        <button
          className={`tab-btn ${view === 'issues' ? 'active' : ''}`}
          onClick={() => setView('issues')}
        >
          🧩 Issue Clusters
        </button>
        <button
          className={`tab-btn ${view === 'rejected' ? 'active' : ''}`}
          onClick={() => setView('rejected')}
        >
          🚫 Out of Scope
        </button>
      </div>

      {view === 'heatmap' ? (
        <section>
          <p className="dashboard-kicker">
            Concentration of Pending &amp; In Progress issues, weighted by AI priority.
          </p>
          {heatmapLoading ? (
            <p className="page-state">Loading heatmap...</p>
          ) : heatmapError ? (
            <p className="form-message error" role="alert">{heatmapError}</p>
          ) : (
            <HeatmapView points={heatmapPoints} />
          )}
        </section>
      ) : view === 'spam' ? (
        <SpamReviewList onDecision={() => { fetchData(); fetchHeatmap() }} />
      ) : view === 'issues' ? (
        <IssueClusterList />
      ) : view === 'rejected' ? (
        <RejectedComplaintsList onDecision={() => { fetchData(); fetchHeatmap() }} />
      ) : (
      <>
      {/* Control / Filter Bar */}
      <section className="officer-controls">
        <div className="search-box">
          <input
            type="text"
            placeholder="Search complaints by title, keyword, or location..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">All Statuses</option>
            <option value="Pending">Pending</option>
            <option value="In Progress">In Progress</option>
            <option value="Resolved">Resolved</option>
          </select>

          <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
            <option value="">All Categories</option>
            <option value="Road Infrastructure">Road Infrastructure</option>
            <option value="Street Lighting">Street Lighting</option>
            <option value="Garbage and Waste">Garbage and Waste</option>
            <option value="Water Supply">Water Supply</option>
            <option value="Drainage">Drainage</option>
            <option value="Public Safety">Public Safety</option>
            <option value="Other">Other</option>
          </select>
        </div>
      </section>

      {actionError && <p className="form-message error" role="alert">{actionError}</p>}

      {loading ? (
        <p className="page-state">Loading complaints database...</p>
      ) : error ? (
        <p className="form-message error" role="alert">{error}</p>
      ) : filteredComplaints.length === 0 ? (
        <div className="empty-state">
          <h2>No complaints match your filters</h2>
          <p>Try resetting status or category filters to view all issues.</p>
        </div>
      ) : (
        <div className="officer-complaint-list">
          {filteredComplaints.map((item) => (
            <article className="officer-card" key={item.id}>
              <div className="officer-card-header">
                <div>
                  <span className="complaint-category">{item.category || 'General'}</span>
                  {item.ai_analysis?.priority && (
                    <span className={`priority-tag priority-${item.ai_analysis.priority.toLowerCase()}`}>
                      {item.ai_analysis.priority} Priority
                    </span>
                  )}
                  <h2>{item.title}</h2>
                  <p className="officer-meta">
                    📍 {item.location} &bull; Reported {formatDate(item.created_at)}
                  </p>
                </div>

                <div className="status-action-box">
                  <label htmlFor={`status-select-${item.id}`} className="visually-hidden">
                    Status for {item.title}
                  </label>
                  <select
                    id={`status-select-${item.id}`}
                    value={item.status || 'Pending'}
                    onChange={(e) => handleStatusChange(item.id, e.target.value)}
                    disabled={updatingId === item.id}
                    className={`status-select status-select-${(item.status || 'Pending').toLowerCase().replace(' ', '-')}`}
                  >
                    <option value="Pending">🟡 Pending</option>
                    <option value="In Progress">🔵 In Progress</option>
                    <option value="Resolved">🟢 Resolved</option>
                  </select>
                  <button
                    type="button"
                    className="button button-outline-danger"
                    onClick={() => openRejectModal(item.id)}
                  >
                    Reject / Out of Scope
                  </button>
                </div>
              </div>

              <p className="officer-card-desc">{item.description}</p>

              {item.image_url && (
                <div className="officer-card-thumb">
                  <img src={item.image_url} alt={item.title} />
                </div>
              )}

              {item.ai_analysis && (
                <div className="officer-ai-strip">
                  <div><strong>AI Dept:</strong> {item.ai_analysis.department || 'Unassigned'}</div>
                  <div><strong>Observation:</strong> {item.ai_analysis.visual_observation || 'N/A'}</div>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
      </>
      )}

      {rejectModalId && (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-box app-form">
            <h2>Reject / Out of Scope</h2>
            <p>
              Select why this complaint is outside NMC/government responsibility. This is not
              spam - it will not affect the citizen's spam standing.
            </p>

            {REJECTION_REASONS.map((reason) => (
              <label className="radio-row" key={reason}>
                <input
                  type="radio"
                  name="rejection-reason"
                  value={reason}
                  checked={rejectReason === reason}
                  onChange={() => setRejectReason(reason)}
                />
                {reason}
              </label>
            ))}

            <label>
              Additional explanation{rejectReason === 'Other' ? ' (required)' : ' (optional)'}
              <textarea
                rows="3"
                value={rejectExplanation}
                onChange={(e) => setRejectExplanation(e.target.value)}
              />
            </label>

            {rejectError && (
              <p className="form-message error" role="alert">{rejectError}</p>
            )}

            <div className="modal-actions">
              <button type="button" className="button" onClick={closeRejectModal} disabled={rejectSubmitting}>
                Cancel
              </button>
              <button
                type="button"
                className="button button-primary"
                onClick={submitRejection}
                disabled={rejectSubmitting}
              >
                {rejectSubmitting ? 'Submitting…' : 'Confirm Rejection'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  )
}
