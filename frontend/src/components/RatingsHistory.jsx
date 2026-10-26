import { useCallback, useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getRatings } from '../services/performanceservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'
import { PAGE_SIZE, cleanParams, stars as starText } from '../utils/performance.js'
import Pager from './Pager.jsx'

export default function RatingsHistory({ officers }) {
  const [filters, setFilters] = useState({ officer_id: '', stars: '', history: '', offset: 0 })
  const [state, setState] = useState({ status: 'loading', ratings: [], total: 0, limit: PAGE_SIZE, offset: 0, error: '' })

  const load = useCallback(async () => {
    try {
      const { data } = await getRatings(cleanParams({ ...filters, limit: PAGE_SIZE }))
      setState({ status: 'ready', ratings: data.ratings || [], total: data.total, limit: data.limit, offset: data.offset, error: '' })
    } catch (err) {
      setState((current) => ({ ...current, status: 'error', error: apiErrorMessage(err, 'Could not load ratings.') }))
    }
  }, [filters])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const change = (field) => (event) => setFilters({ ...filters, [field]: event.target.value, offset: 0 })
  return (
    <section>
      <p className="resolution-kicker">Ratings are confidential to the Chief Officer and the rated Officer. Revisions are kept; nothing is overwritten.</p>
      <div className="officer-controls">
        <div className="filter-group resolution-filters">
          <select aria-label="Filter by officer" value={filters.officer_id} onChange={change('officer_id')}>
            <option value="">All officers</option>
            {officers.map((officer) => <option key={officer.id} value={officer.id}>{officer.name}</option>)}
          </select>
          <select aria-label="Filter by stars" value={filters.stars} onChange={change('stars')}>
            <option value="">Any rating</option>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} star{n === 1 ? '' : 's'}</option>)}
          </select>
          <select aria-label="Revisions" value={filters.history} onChange={change('history')}>
            <option value="">Current ratings</option>
            <option value="true">Include superseded revisions</option>
          </select>
        </div>
      </div>
      {state.status === 'loading' && <p className="page-state">Loading ratings…</p>}
      {state.status === 'error' && (
        <div><p className="form-message error" role="alert">{state.error}</p><button type="button" className="button" onClick={load}>Try again</button></div>
      )}
      {state.status === 'ready' && state.ratings.length === 0 && (
        <div className="empty-state"><h2>No ratings yet</h2><p>Rate approved work from the “Rate work” tab.</p></div>
      )}
      {state.status === 'ready' && state.ratings.length > 0 && (
        <ul className="resolution-log">
          {state.ratings.map((rating) => (
            <li key={rating.id}>
              <strong>{starText(rating.stars)}</strong>{' '}
              <span className="resolution-chip">{rating.rated_officer?.name}</span>
              {!rating.is_effective && <span className="resolution-chip chip-blocked">Superseded</span>}
              {rating.needs_follow_up && <span className="resolution-chip chip-excluded">Follow-up required</span>}
              <p className="resolution-muted">
                {rating.issue.category} • {rating.issue.location_label || 'no location'} • rated {formatDateTime(rating.created_at)} by {rating.rated_by?.name}
                {rating.supersedes_rating_id ? ` • revises #${rating.supersedes_rating_id}` : ''}
              </p>
              {rating.explanation && <p>{rating.explanation}</p>}
            </li>
          ))}
        </ul>
      )}
      <Pager total={state.total} limit={state.limit} offset={state.offset} onChange={(offset) => setFilters({ ...filters, offset })} />
    </section>
  )
}
