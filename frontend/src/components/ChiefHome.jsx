import { useCallback, useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getOverview } from '../services/performanceservice.js'
import { attentionItems, permissionMessage, unassignedOfficers } from '../utils/performance.js'

// The landing view: what needs the Chief Officer's attention first, then a
// compact municipality-wide picture. Detail lives in the other sections.
export default function ChiefHome({ onNavigate }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: '' })

  const load = useCallback(async () => {
    try {
      const { data } = await getOverview()
      setState({ status: 'ready', data, error: '' })
    } catch (err) {
      setState((current) => ({
        ...current, status: 'error',
        error: permissionMessage(err.response?.status, apiErrorMessage(err, 'Could not load the overview.')),
      }))
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  if (state.status === 'loading') return <p className="page-state">Loading overview…</p>
  if (state.status === 'error') {
    return <div><p className="form-message error" role="alert">{state.error}</p><button type="button" className="button" onClick={load}>Try again</button></div>
  }

  const { data } = state
  const attention = attentionItems(data)
  const idle = unassignedOfficers(data.officers.items)
  return (
    <div className="chief-home">
      <p className="resolution-kicker"><strong>Municipality-wide.</strong> Supervision of work quality. User, role and ward administration are done by Admins.</p>

      <h2>Needs your attention</h2>
      {attention.length === 0 ? (
        <div className="empty-state"><h2>Nothing is waiting for you</h2><p>New submissions, ratings to give and corrections to verify will appear here.</p></div>
      ) : (
        <ul className="attention-list">
          {attention.map((item) => (
            <li key={item.id}>
              <button type="button" className="attention-item" onClick={() => onNavigate(item.tab)}>
                <strong>{item.count}</strong> {item.label} <span aria-hidden="true">→</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <h2>At a glance</h2>
      <section className="officer-stats-grid" aria-label="At a glance">
        <div className="stat-card"><span className="stat-label">Active wards</span><strong className="stat-value">{data.wards.active_total}</strong></div>
        <div className="stat-card"><span className="stat-label">Officers</span><strong className="stat-value">{data.officers.total}</strong>
          <span className="resolution-muted">{data.officers.assigned_to_a_ward} in a ward • {data.officers.unassigned} unassigned{data.officers.suspended ? ` • ${data.officers.suspended} suspended` : ''}</span></div>
        <div className="stat-card"><span className="stat-label">Issues</span><strong className="stat-value">{data.issues.total}</strong>
          <span className="resolution-muted">{data.issues.by_status['Pending Review']} awaiting review • {data.issues.by_status.Resolved} resolved</span></div>
        <div className="stat-card"><span className="stat-label">Open corrections</span>
          <strong className="stat-value">{data.follow_ups.by_status['Awaiting Assignment'] + data.follow_ups.by_status.Assigned + data.follow_ups.by_status['Correction Submitted']}</strong>
          <span className="resolution-muted">{data.follow_ups.by_status.Closed} closed</span></div>
      </section>
      <p className="resolution-muted">
        Issues group complaints ({data.complaints.eligible_total} eligible complaints in {data.issues.total} issues); the two are never added together.
        Open the Analytics section for definitions, resolution time and trends.
      </p>
      {idle.length > 0 && (
        <p className="resolution-muted">Officers with no active ward: {idle.map((officer) => officer.name).join(', ')}. Assignments are managed by Admins.</p>
      )}
    </div>
  )
}
