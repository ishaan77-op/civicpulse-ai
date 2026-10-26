import { useCallback, useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getOverview } from '../services/performanceservice.js'
import { cleanParams, hoursLabel } from '../utils/performance.js'

function Stat({ label, value, hint, tone }) {
  return (
    <div className={`stat-card ${tone || ''}`}>
      <span className="stat-label">{label}</span>
      <strong className="stat-value">{value}</strong>
      {hint && <span className="resolution-muted">{hint}</span>}
    </div>
  )
}

// Read-only, municipality-wide supervision. Every figure comes from the API;
// anything the API reports as unavailable is shown as unavailable, not zero.
export default function ChiefAnalytics({ wards, officers }) {
  const [filters, setFilters] = useState({ ward_id: '', officer_id: '', from: '', to: '' })
  const [state, setState] = useState({ status: 'loading', data: null, error: '' })

  const load = useCallback(async () => {
    try {
      const { data } = await getOverview(cleanParams(filters))
      setState({ status: 'ready', data, error: '' })
    } catch (err) {
      setState((current) => ({ ...current, status: 'error', error: apiErrorMessage(err, 'Could not load the supervisory overview.') }))
    }
  }, [filters])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const change = (field) => (event) => setFilters((current) => ({ ...current, [field]: event.target.value }))

  const { status, data, error } = state
  return (
    <div className="chief-overview">
      <h2>Supervisory analytics</h2>
      <p className="resolution-kicker"><strong>Scope: municipality-wide.</strong> Supervision only; user and ward administration stay with Admins.</p>

      <div className="officer-controls">
        <div className="filter-group resolution-filters">
          <select aria-label="Filter by ward" value={filters.ward_id} onChange={change('ward_id')}>
            <option value="">All wards</option>
            {wards.map((ward) => <option key={ward.id} value={ward.id}>{ward.name}</option>)}
          </select>
          <select aria-label="Filter by officer" value={filters.officer_id} onChange={change('officer_id')}>
            <option value="">All officers</option>
            {officers.map((officer) => <option key={officer.id} value={officer.id}>{officer.name}</option>)}
          </select>
          <label className="resolution-inline">From <input type="date" value={filters.from} onChange={change('from')} /></label>
          <label className="resolution-inline">To <input type="date" value={filters.to} onChange={change('to')} /></label>
        </div>
      </div>

      {status === 'loading' && <p className="page-state">Loading overview…</p>}
      {status === 'error' && (
        <div>
          <p className="form-message error" role="alert">{error}</p>
          <button type="button" className="button" onClick={load}>Try again</button>
        </div>
      )}
      {status === 'ready' && (
        <>
          <p className="resolution-muted">
            Ward filter: {data.filters.applies_to.ward_id}. Officer filter: {data.filters.applies_to.officer_id}. Dates: {data.filters.applies_to.date_range}.
          </p>

          <h3>Resolution reviews</h3>
          <section className="officer-stats-grid" aria-label="Resolution reviews">
            <Stat label="Awaiting your decision" value={data.reviews.pending_decision} hint="Actionable now" tone="stat-progress" />
            <Stat label="Withdrawn (stale)" value={data.reviews.stale_awaiting_resubmission} hint="Waiting for the Officer; not rejected" tone="stat-pending" />
            <Stat label="Approved" value={data.reviews.approved} />
            <Stat label="Sent back (rejected)" value={data.reviews.rejected} hint={`${data.reviews.resubmissions} resubmission${data.reviews.resubmissions === 1 ? '' : 's'}`} />
          </section>

          <p className="resolution-muted">
            Work: {data.work.work_updates} field-work updates on {data.work.issues_with_work_updates} issue{data.work.issues_with_work_updates === 1 ? '' : 's'};
            {' '}{data.work.review_submissions} review submission{data.work.review_submissions === 1 ? '' : 's'} on {data.work.issues_with_review_submissions} issue{data.work.issues_with_review_submissions === 1 ? '' : 's'}.
            {' '}{data.work.note}
          </p>

          <h3>Issues <span className="resolution-muted">(not the same as complaints)</span></h3>
          <section className="officer-stats-grid" aria-label="Issues by status">
            {Object.entries(data.issues.by_status).map(([name, count]) => <Stat key={name} label={name} value={count} />)}
          </section>
          <p className="resolution-muted">
            {data.issues.total} issues in total, grouping {data.complaints.eligible_total} eligible complaints
            ({Object.entries(data.complaints.by_status).map(([name, count]) => `${count} ${name}`).join(', ')}).
            {' '}Excluded: {data.complaints.excluded_confirmed_spam} spam, {data.complaints.excluded_out_of_scope} out of scope.
            {data.complaints.eligible_without_issue_link > 0 && ` ${data.complaints.eligible_without_issue_link} older complaints have no issue link and are not part of any issue count.`}
          </p>

          <h3>Ratings and corrections</h3>
          <section className="officer-stats-grid" aria-label="Ratings and follow-ups">
            <Stat label="Rated jobs" value={data.ratings.effective_total} hint={`${data.ratings.revisions} revision${data.ratings.revisions === 1 ? '' : 's'}`} />
            <Stat label="Low ratings (1-2★)" value={data.ratings.low_total} />
            <Stat label="Approved, not yet rated" value={data.ratings.approved_not_yet_rated} />
            <Stat label="Corrections open" value={data.follow_ups.by_status['Awaiting Assignment'] + data.follow_ups.by_status.Assigned + data.follow_ups.by_status['Correction Submitted']} hint={`${data.follow_ups.by_status['Correction Submitted']} awaiting your verification`} />
          </section>
          <p className="resolution-muted">
            Star counts: {Object.entries(data.ratings.by_stars).map(([star, count]) => `${star}★ ${count}`).join(' · ')}. Follow-ups:
            {' '}{Object.entries(data.follow_ups.by_status).map(([name, count]) => `${name} ${count}`).join(' · ')}.
          </p>

          <h3>Resolution time</h3>
          {data.resolution_time.available ? (
            <p>
              Average {hoursLabel(data.resolution_time.average_hours)}, median {hoursLabel(data.resolution_time.median_hours)}
              {' '}across {data.resolution_time.sample_size} resolved issue{data.resolution_time.sample_size === 1 ? '' : 's'}.
              {data.resolution_time.excluded_resolved_without_approved_review > 0 &&
                ` ${data.resolution_time.excluded_resolved_without_approved_review} resolved issue(s) are excluded because they have no approved review on record.`}
            </p>
          ) : (
            <p className="resolution-muted">
              Unavailable: no resolved issue has an approved review on record yet.
              {data.resolution_time.excluded_resolved_without_approved_review > 0 && ` (${data.resolution_time.excluded_resolved_without_approved_review} resolved without one.)`}
            </p>
          )}
          <p className="resolution-muted">{data.resolution_time.basis}. No overdue or SLA status is shown: no policy has been approved.</p>

          <h3>Last {data.trends.weeks.length} weeks</h3>
          <div className="table-responsive">
            <div className="resolution-table-wrap">
            <table className="admin-table">
              <thead><tr><th>Week starting ({data.trends.bucket})</th><th>Reviews submitted</th><th>Reviews approved</th></tr></thead>
              <tbody>
                {data.trends.weeks.map((week) => (
                  <tr key={week.week_start}><td>{week.week_start}</td><td>{week.reviews_submitted}</td><td>{week.reviews_approved}</td></tr>
                ))}
              </tbody>
            </table>
            </div>
          </div>

        </>
      )}
    </div>
  )
}
