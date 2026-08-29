import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/appshell.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getAdminAnalytics, getAdminUsers, updateUserRole } from '../services/complaintservice.js'

export default function AdminDashboard() {
  const [analytics, setAnalytics] = useState(null)
  const [users, setUsers] = useState([])
  const [activeTab, setActiveTab] = useState('analytics') // 'analytics' | 'users'
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [roleUpdatingId, setRoleUpdatingId] = useState(null)

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const [analyticsRes, usersRes] = await Promise.all([
        getAdminAnalytics(),
        getAdminUsers()
      ])
      setAnalytics(analyticsRes.data)
      setUsers(usersRes.data.users || [])
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to load admin intelligence metrics.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(fetchData, 0)
    return () => window.clearTimeout(timer)
  }, [fetchData])

  const handleRoleChange = async (userId, newRole) => {
    try {
      setActionError('')
      setRoleUpdatingId(userId)
      await updateUserRole(userId, newRole)
      await fetchData()
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Failed to update user role.'))
    } finally {
      setRoleUpdatingId(null)
    }
  }

  const summary = analytics?.summary || {}
  const breakdown = analytics?.breakdown || {}

  return (
    <AppShell eyebrow="Platform Intelligence & Control" title="Admin Dashboard">
      <div className="admin-tabs">
        <button
          className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
        >
          📊 Analytics & Insights
        </button>
        <button
          className={`tab-btn ${activeTab === 'users' ? 'active' : ''}`}
          onClick={() => setActiveTab('users')}
        >
          👥 User Role Management ({users.length})
        </button>
      </div>

      {actionError && <p className="form-message error" role="alert">{actionError}</p>}

      {loading ? (
        <p className="page-state">Gathering platform intelligence metrics...</p>
      ) : error ? (
        <p className="form-message error" role="alert">{error}</p>
      ) : activeTab === 'analytics' ? (
        <>
          {/* Executive KPI Summary */}
          <section className="admin-kpi-grid">
            <div className="admin-kpi-card">
              <span className="kpi-title">Total Complaints</span>
              <strong className="kpi-value">{summary.total_complaints || 0}</strong>
              <small className="kpi-sub">Across all categories</small>
            </div>

            <div className="admin-kpi-card">
              <span className="kpi-title">Resolution Rate</span>
              <strong className="kpi-value highlight">{summary.resolution_rate || 0}%</strong>
              <small className="kpi-sub">{summary.resolved || 0} issues resolved</small>
            </div>

            <div className="admin-kpi-card">
              <span className="kpi-title">Pending Action</span>
              <strong className="kpi-value warning">{summary.pending || 0}</strong>
              <small className="kpi-sub">{summary.in_progress || 0} currently in progress</small>
            </div>

            <div className="admin-kpi-card">
              <span className="kpi-title">Registered Users</span>
              <strong className="kpi-value">{summary.total_users || 0}</strong>
              <small className="kpi-sub">{summary.citizens || 0} citizens &bull; {summary.officers || 0} officers</small>
            </div>
          </section>

          {/* Breakdown Distributions */}
          <section className="admin-breakdown-grid">
            <div className="breakdown-card">
              <h2>Complaints by Category</h2>
              <div className="breakdown-list">
                {Object.entries(breakdown.categories || {}).length === 0 ? (
                  <p className="empty-breakdown">No data recorded yet.</p>
                ) : (
                  Object.entries(breakdown.categories || {}).map(([cat, count]) => (
                    <div key={cat} className="bar-row">
                      <div className="bar-label">
                        <span>{cat}</span>
                        <strong>{count}</strong>
                      </div>
                      <div className="bar-track">
                        <div
                          className="bar-fill"
                          style={{ width: `${Math.min(100, (count / (summary.total_complaints || 1)) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="breakdown-card">
              <h2>Department Workload</h2>
              <div className="breakdown-list">
                {Object.entries(breakdown.departments || {}).length === 0 ? (
                  <p className="empty-breakdown">No data recorded yet.</p>
                ) : (
                  Object.entries(breakdown.departments || {}).map(([dept, count]) => (
                    <div key={dept} className="bar-row">
                      <div className="bar-label">
                        <span>{dept}</span>
                        <strong>{count}</strong>
                      </div>
                      <div className="bar-track">
                        <div
                          className="bar-fill fill-sky"
                          style={{ width: `${Math.min(100, (count / (summary.total_complaints || 1)) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="breakdown-card">
              <h2>Triage Priorities</h2>
              <div className="breakdown-list">
                {Object.entries(breakdown.priorities || {}).length === 0 ? (
                  <p className="empty-breakdown">No data recorded yet.</p>
                ) : (
                  Object.entries(breakdown.priorities || {}).map(([priority, count]) => (
                    <div key={priority} className="bar-row">
                      <div className="bar-label">
                        <span>{priority} Priority</span>
                        <strong>{count}</strong>
                      </div>
                      <div className="bar-track">
                        <div
                          className={`bar-fill fill-${priority.toLowerCase()}`}
                          style={{ width: `${Math.min(100, (count / (summary.total_complaints || 1)) * 100)}%` }}
                        />
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>
        </>
      ) : (
        /* User Management Section */
        <section className="admin-users-section">
          <h2>User Role & Access Directory</h2>
          <p>Grant Officer or Admin access to system accounts.</p>

          <div className="table-responsive">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Email</th>
                  <th>Current Role</th>
                  <th>Action / Assign Role</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <strong>{u.name}</strong>
                    </td>
                    <td>{u.email}</td>
                    <td>
                      <span className={`role-badge role-${u.role.toLowerCase()}`}>
                        {u.role}
                      </span>
                    </td>
                    <td>
                      <select
                        value={u.role}
                        onChange={(e) => handleRoleChange(u.id, e.target.value)}
                        disabled={roleUpdatingId === u.id}
                        className="role-select"
                      >
                        <option value="Citizen">Citizen</option>
                        <option value="Officer">Officer</option>
                        <option value="Admin">Admin</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </AppShell>
  )
}
