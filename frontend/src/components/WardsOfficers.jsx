import { useCallback, useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getOfficerDetail, getOverview, getWard } from '../services/performanceservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'
import { PAGE_SIZE, cleanParams, permissionMessage } from '../utils/performance.js'
import Pager from './Pager.jsx'

const REVIEW_STATES = ['Pending', 'Approved', 'Rejected', 'Stale', 'Superseded']

function WardDetail({ wardId }) {
  const [state, setState] = useState({ status: 'loading', data: null, error: '' })
  const load = useCallback(async () => {
    try {
      const { data } = await getWard(wardId)
      setState({ status: 'ready', data, error: '' })
    } catch (err) {
      setState({ status: 'error', data: null, error: apiErrorMessage(err, 'Could not load this ward.') })
    }
  }, [wardId])
  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  if (state.status === 'loading') return <p className="page-state">Loading ward…</p>
  if (state.status === 'error') return <div><p className="form-message error" role="alert">{state.error}</p><button type="button" className="button" onClick={load}>Try again</button></div>
  const { ward, assignments, active_officer_activity: activity, note } = state.data
  return (
    <div>
      {!ward.is_active && <p className="resolution-banner banner-stale">This ward is inactive{ward.deactivated_at ? ` (since ${formatDateTime(ward.deactivated_at)})` : ''}. Its history is kept.</p>}
      <h4>Assignment history</h4>
      {assignments.length === 0 ? <p className="resolution-muted">No Officer has ever been assigned.</p> : (
        <ul className="resolution-log">
          {assignments.map((row) => (
            <li key={row.id}>
              <strong>{row.officer.name}</strong> <span className="resolution-chip">{row.is_active ? 'Active' : 'Ended'}</span>
              {row.officer.role !== 'Officer' && <span className="resolution-chip chip-blocked">Now {row.officer.role}</span>}
              {row.officer.is_suspended && <span className="resolution-chip chip-blocked">Suspended</span>}
              <p className="resolution-muted">Assigned {formatDateTime(row.assigned_at)}{row.ended_at ? ` • ended ${formatDateTime(row.ended_at)}` : ''}</p>
              {row.is_active && activity[String(row.officer.id)] && (
                <p className="resolution-muted">
                  Officer's municipality-wide totals: {activity[String(row.officer.id)].work_updates} work updates, {activity[String(row.officer.id)].reviews_submitted} review submissions
                  ({activity[String(row.officer.id)].reviews_approved} approved, {activity[String(row.officer.id)].reviews_rejected} sent back)
                </p>
              )}
            </li>
          ))}
        </ul>
      )}
      <p className="resolution-muted">{note}</p>
    </div>
  )
}

function OfficerDetail({ officerId, onBack }) {
  const [filters, setFilters] = useState({ state: '', offset: 0 })
  const [state, setState] = useState({ status: 'loading', data: null, error: '' })
  const load = useCallback(async () => {
    try {
      const { data } = await getOfficerDetail(officerId, cleanParams({ state: filters.state, limit: PAGE_SIZE, offset: filters.offset }))
      setState({ status: 'ready', data, error: '' })
    } catch (err) {
      setState({ status: 'error', data: null, error: permissionMessage(err.response?.status, apiErrorMessage(err, 'Could not load this Officer.')) })
    }
  }, [officerId, filters])
  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  return (
    <div className="officer-detail">
      <button type="button" className="button" onClick={onBack}>← Back to directory</button>
      {state.status === 'loading' && <p className="page-state">Loading Officer…</p>}
      {state.status === 'error' && <div><p className="form-message error" role="alert">{state.error}</p><button type="button" className="button" onClick={load}>Try again</button></div>}
      {state.status === 'ready' && (() => {
        const { officer, wards, work, ratings, follow_ups: followUps, submissions } = state.data
        return (
          <>
            <h3>{officer.name} {officer.is_suspended && <span className="resolution-chip chip-blocked">Suspended</span>}</h3>
            <p className="resolution-muted">{officer.email}</p>

            <h4>Ward assignments</h4>
            {wards.length === 0 ? <p className="resolution-muted">Never assigned to a ward.</p> : (
              <ul className="resolution-log">
                {wards.map((row) => (
                  <li key={`${row.ward_id}-${row.assigned_at}`}>
                    <strong>{row.name}</strong>{row.code ? ` (${row.code})` : ''} <span className="resolution-chip">{row.is_active ? 'Active' : 'Ended'}</span>
                    {!row.ward_is_active && <span className="resolution-chip chip-blocked">Ward inactive</span>}
                    <p className="resolution-muted">Assigned {formatDateTime(row.assigned_at)}{row.ended_at ? ` • ended ${formatDateTime(row.ended_at)}` : ''}</p>
                  </li>
                ))}
              </ul>
            )}

            <h4>Work (activity, not caseload)</h4>
            <section className="officer-stats-grid" aria-label="Work summary">
              <div className="stat-card"><span className="stat-label">Review submissions</span><strong className="stat-value">{work.review_submissions}</strong><span className="resolution-muted">on {work.issues_with_review_submissions} issue{work.issues_with_review_submissions === 1 ? '' : 's'}</span></div>
              <div className="stat-card"><span className="stat-label">Field-work updates</span><strong className="stat-value">{work.work_updates}</strong><span className="resolution-muted">on {work.issues_with_work_updates} issue{work.issues_with_work_updates === 1 ? '' : 's'}</span></div>
              <div className="stat-card"><span className="stat-label">Approved / sent back</span><strong className="stat-value">{work.approved} / {work.rejected}</strong></div>
              <div className="stat-card"><span className="stat-label">Awaiting decision / withdrawn</span><strong className="stat-value">{work.pending_decision} / {work.stale_awaiting_resubmission}</strong></div>
            </section>
            <p className="resolution-muted">{work.note}</p>

            <h4>Ratings and corrections</h4>
            <p>
              {ratings.effective_total} rated job{ratings.effective_total === 1 ? '' : 's'} ({ratings.low_total} low).
              {' '}Stars: {Object.entries(ratings.by_stars).map(([star, count]) => `${star}★ ${count}`).join(' · ')}.
              {' '}Corrections on this Officer's work: {Object.entries(followUps.on_this_officers_work).map(([name, count]) => `${name} ${count}`).join(' · ')}.
              {' '}Assigned to this Officer: {Object.entries(followUps.assigned_to_this_officer).map(([name, count]) => `${name} ${count}`).join(' · ')}.
            </p>

            <h4>Work submissions</h4>
            <select aria-label="Filter submissions by review state" value={filters.state} onChange={(event) => setFilters({ state: event.target.value, offset: 0 })}>
              <option value="">All states</option>
              {REVIEW_STATES.map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
            {submissions.items.length === 0 ? <p className="resolution-muted">No submissions match.</p> : (
              <div className="table-responsive">
                <div className="resolution-table-wrap">
                <table className="admin-table">
                  <thead><tr><th>Submitted</th><th>Issue</th><th>Review</th><th>Rating</th><th>Correction</th></tr></thead>
                  <tbody>
                    {submissions.items.map((row) => (
                      <tr key={row.resolution_review_id}>
                        <td>{formatDateTime(row.submitted_at)}</td>
                        <td>{row.issue.category} • {row.issue.location_label || 'no location'}</td>
                        <td>{row.state}{row.supersedes_review_id ? ' (resubmission)' : ''}</td>
                        <td>{row.rating ? `${row.rating.stars}★` : '—'}</td>
                        <td>{row.follow_up ? row.follow_up.status : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              </div>
            )}
            <Pager total={submissions.total} limit={submissions.limit} offset={submissions.offset} onChange={(offset) => setFilters({ ...filters, offset })} />
          </>
        )
      })()}
    </div>
  )
}

// Ward-wise Officer directory (read-only) with ward and Officer detail views.
export default function WardsOfficers({ wards, officers }) {
  const [filters, setFilters] = useState({ ward_id: '', officer_id: '' })
  const [state, setState] = useState({ status: 'loading', data: null, error: '' })
  const [openWard, setOpenWard] = useState(null)
  const [officerId, setOfficerId] = useState(null)

  const load = useCallback(async () => {
    try {
      const { data } = await getOverview(cleanParams(filters))
      setState({ status: 'ready', data, error: '' })
    } catch (err) {
      setState((current) => ({ ...current, status: 'error', error: permissionMessage(err.response?.status, apiErrorMessage(err, 'Could not load the directory.')) }))
    }
  }, [filters])
  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  if (officerId) return <OfficerDetail officerId={officerId} onBack={() => setOfficerId(null)} />

  const { status, data, error } = state
  return (
    <section>
      <p className="resolution-kicker">Which Officers are assigned to which wards, and what each has done. Assignments are managed by Admins; this view is read-only.</p>
      <div className="officer-controls">
        <div className="filter-group resolution-filters">
          <select aria-label="Filter by ward" value={filters.ward_id} onChange={(event) => setFilters({ ...filters, ward_id: event.target.value })}>
            <option value="">All wards</option>
            {wards.map((ward) => <option key={ward.id} value={ward.id}>{ward.name}</option>)}
          </select>
          <select aria-label="Filter by officer" value={filters.officer_id} onChange={(event) => setFilters({ ...filters, officer_id: event.target.value })}>
            <option value="">All officers</option>
            {officers.map((officer) => <option key={officer.id} value={officer.id}>{officer.name}</option>)}
          </select>
        </div>
      </div>
      {status === 'loading' && <p className="page-state">Loading directory…</p>}
      {status === 'error' && <div><p className="form-message error" role="alert">{error}</p><button type="button" className="button" onClick={load}>Try again</button></div>}
      {status === 'ready' && (
        <>
          <h2>Wards ({data.wards.active_total} active)</h2>
          {data.wards.items.length === 0 ? (
            <div className="empty-state"><h2>No wards to show</h2><p>Wards are created by Admins. None match this filter.</p></div>
          ) : (
            <div className="officer-complaint-list">
              {data.wards.items.map((ward) => (
                <article className="officer-card" key={ward.id}>
                  <div className="officer-card-header">
                    <div>
                      <h3>{ward.name}{ward.code ? ` (${ward.code})` : ''}</h3>
                      {ward.officers.length === 0 ? <p className="resolution-muted">No Officer assigned.</p> : (
                        <p>{ward.officers.map((officer) => (
                          <button key={officer.id} type="button" className="text-link" onClick={() => setOfficerId(officer.id)}>
                            {officer.name}{officer.is_suspended ? ' (suspended)' : ''}
                          </button>
                        )).reduce((previous, current) => [previous, ', ', current])}</p>
                      )}
                    </div>
                    <button type="button" className="button" aria-expanded={openWard === ward.id} onClick={() => setOpenWard(openWard === ward.id ? null : ward.id)}>
                      {openWard === ward.id ? 'Hide history' : 'Assignment history'}
                    </button>
                  </div>
                  {openWard === ward.id && <WardDetail wardId={ward.id} />}
                </article>
              ))}
            </div>
          )}
          <p className="resolution-muted">Ward-level work: {data.wards.work_by_ward.reason}</p>

          <h2>Officers ({data.officers.total} total • {data.officers.assigned_to_a_ward} in a ward • {data.officers.unassigned} unassigned)</h2>
          {data.officers.items.length === 0 ? <p className="resolution-muted">No Officer matches this filter.</p> : (
            <div className="table-responsive">
              <div className="resolution-table-wrap">
              <table className="admin-table">
                <thead><tr><th>Officer</th><th>Wards</th><th>Field-work updates</th><th>Review submissions</th><th>Approved</th><th>Sent back</th><th>Ratings</th><th>Low</th><th>Open corrections</th></tr></thead>
                <tbody>
                  {data.officers.items.map((officer) => (
                    <tr key={officer.id}>
                      <td><button type="button" className="text-link" onClick={() => setOfficerId(officer.id)}>{officer.name}</button>{officer.is_suspended ? ' (suspended)' : ''}</td>
                      <td>{officer.assignment_status === 'Assigned' ? officer.ward_ids.length : 'None'}</td>
                      <td>{officer.work_updates}</td><td>{officer.reviews_submitted}</td><td>{officer.reviews_approved}</td><td>{officer.reviews_rejected}</td>
                      <td>{officer.ratings_received}</td><td>{officer.low_ratings_received}</td><td>{officer.open_corrections_assigned}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              </div>
            </div>
          )}
          <p className="resolution-muted">{data.officers.note}</p>
        </>
      )}
    </section>
  )
}
