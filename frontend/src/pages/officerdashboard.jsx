import { useEffect, useState } from 'react'
import AppShell from '../components/appshell.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getOfficerComplaints, getOfficerStats, updateComplaintStatus } from '../services/complaintservice.js'

const formatDate = (value) => value ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : 'Date unavailable'

export default function OfficerDashboard() {
  const [complaints, setComplaints] = useState([])
  const [stats, setStats] = useState({ total_complaints: 0, pending: 0, in_progress: 0, resolved: 0 })
  const [statusFilter, setStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [updatingId, setUpdatingId] = useState(null)

  const fetchData = async () => {
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
  }

  useEffect(() => {
    fetchData()
  }, [statusFilter, categoryFilter])

  const handleStatusChange = async (id, newStatus) => {
    try {
      setUpdatingId(id)
      await updateComplaintStatus(id, newStatus)
      await fetchData()
    } catch (err) {
      alert(apiErrorMessage(err, 'Failed to update complaint status.'))
    } finally {
      setUpdatingId(null)
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
    </AppShell>
  )
}
