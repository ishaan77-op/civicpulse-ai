import { useCallback, useEffect, useRef, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { assignFollowUp, getFollowUp, getFollowUps, verifyFollowUp } from '../services/performanceservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'
import {
  FOLLOW_UP_STATUSES, PAGE_SIZE, assignableOfficers, cleanParams, followUpActions, followUpTone, stars as starText, validateVerification,
} from '../utils/performance.js'
import FollowUpEvents from './FollowUpEvents.jsx'
import Pager from './Pager.jsx'

function CaseControls({ followUp, officers, onChanged }) {
  const actions = followUpActions(followUp.status, 'Chief Officer')
  const [officerId, setOfficerId] = useState('')
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)

  const run = async (call, done) => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError('')
    try {
      await call()
      setNote('')
      setOfficerId('')
      await onChanged(done)
    } catch (err) {
      setError(apiErrorMessage(err, 'That change could not be saved.'))
      if ([404, 409].includes(err.response?.status)) await onChanged()
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const candidates = assignableOfficers(officers, followUp.assigned_officer?.id)
  const assign = (event) => {
    event.preventDefault()
    if (!officerId) { setError('Choose an Officer.'); return }
    const target = candidates.find((officer) => String(officer.id) === officerId)
    run(() => assignFollowUp(followUp.id, Number(officerId), note.trim()),
      `${actions.includes('reassign') ? 'Reassigned' : 'Assigned'} to ${target ? target.name : 'the Officer'}.`)
  }
  const verify = (decision) => {
    const problem = validateVerification(decision, note)
    if (problem) { setError(problem); return }
    run(() => verifyFollowUp(followUp.id, decision, note.trim()),
      decision === 'Close' ? 'Correction verified and the case is closed. The issue status is unchanged.' : 'Sent back to the Officer for more work.')
  }

  if (actions.length === 0) return <p className="resolution-muted">No further action: this case is {followUp.status.toLowerCase()}.</p>
  return (
    <div className="resolution-form">
      {(actions.includes('assign') || actions.includes('reassign')) && (
        <form className="app-form ward-assign-form" onSubmit={assign}>
          <label>{actions.includes('reassign') ? 'Reassign to' : 'Assign correction to'}
            <select value={officerId} disabled={busy} onChange={(event) => setOfficerId(event.target.value)}>
              <option value="">{candidates.length ? 'Choose an Officer' : 'No assignable Officers'}</option>
              {candidates.map((officer) => <option key={officer.id} value={officer.id}>{officer.name} ({officer.email})</option>)}
            </select>
          </label>
          <label>Instructions (optional)<input type="text" value={note} disabled={busy} onChange={(event) => setNote(event.target.value)} /></label>
          <button type="submit" className="button button-primary" disabled={busy || !candidates.length}>{busy ? 'Saving…' : actions.includes('reassign') ? 'Reassign' : 'Assign'}</button>
        </form>
      )}
      {actions.includes('close') && (
        <div className="resolution-confirm">
          <p>The Officer has submitted a correction. Verify it, then close the case or send it back. Closing does not change the issue's status.</p>
          <label>Verification note (required if returning)<textarea rows="2" value={note} disabled={busy} onChange={(event) => setNote(event.target.value)} /></label>
          <div className="resolution-actions">
            <button type="button" className="button button-primary" disabled={busy} onClick={() => verify('Close')}>Verify and close</button>
            <button type="button" className="button button-outline-danger" disabled={busy} onClick={() => verify('Return')}>Return for more work</button>
          </div>
        </div>
      )}
      {error && <p className="form-message error" role="alert">{error}</p>}
    </div>
  )
}

export default function FollowUpQueue({ officers }) {
  const [filters, setFilters] = useState({ status: '', assigned_officer_id: '', rated_officer_id: '', stars: '', offset: 0 })
  const [state, setState] = useState({ status: 'loading', items: [], total: 0, limit: PAGE_SIZE, offset: 0, error: '' })
  const [openId, setOpenId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const { data } = await getFollowUps(cleanParams({ ...filters, limit: PAGE_SIZE }))
      setState({ status: 'ready', items: data.follow_ups || [], total: data.total, limit: data.limit, offset: data.offset, error: '' })
    } catch (err) {
      setState((current) => ({ ...current, status: 'error', error: apiErrorMessage(err, 'Could not load follow-ups.') }))
    }
  }, [filters])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const loadDetail = useCallback(async (id) => {
    try {
      const { data } = await getFollowUp(id)
      setDetail({ id, followUp: data.follow_up, error: '' })
    } catch (err) {
      setDetail({ id, followUp: null, error: apiErrorMessage(err, 'Could not load this case.') })
    }
  }, [])

  const toggle = (id) => {
    setNotice('')
    if (openId === id) { setOpenId(null); setDetail(null); return }
    setOpenId(id)
    setDetail(null)
    loadDetail(id)
  }
  const changed = async (message) => {
    if (message) setNotice(message)
    await load()
    if (openId) await loadDetail(openId)
  }
  const filtered = Boolean(filters.status || filters.assigned_officer_id || filters.rated_officer_id || filters.stars)

  return (
    <section>
      <p className="resolution-kicker">
        Corrective follow-ups opened by 1-2 star ratings. They are separate from the issue's resolution: closing one never reopens or resolves an issue.
      </p>
      <div className="officer-controls">
        <div className="filter-group resolution-filters">
          <select aria-label="Filter by status" value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value, offset: 0 })}>
            <option value="">All statuses</option>
            {FOLLOW_UP_STATUSES.map((status) => <option key={status} value={status}>{status}</option>)}
          </select>
          <select aria-label="Filter by assigned officer" value={filters.assigned_officer_id} onChange={(e) => setFilters({ ...filters, assigned_officer_id: e.target.value, offset: 0 })}>
            <option value="">Any assignee</option>
            {officers.map((officer) => <option key={officer.id} value={officer.id}>{officer.name}</option>)}
          </select>
          <select aria-label="Filter by Officer whose work was rated" value={filters.rated_officer_id} onChange={(e) => setFilters({ ...filters, rated_officer_id: e.target.value, offset: 0 })}>
            <option value="">Any rated Officer</option>
            {officers.map((officer) => <option key={officer.id} value={officer.id}>{officer.name}</option>)}
          </select>
          <select aria-label="Filter by rating" value={filters.stars} onChange={(e) => setFilters({ ...filters, stars: e.target.value, offset: 0 })}>
            <option value="">1 or 2 stars</option>
            <option value="1">1 star</option>
            <option value="2">2 stars</option>
          </select>
        </div>
      </div>
      {notice && <p className="resolution-success" role="status">{notice}</p>}
      {state.status === 'loading' && <p className="page-state">Loading follow-ups…</p>}
      {state.status === 'error' && (
        <div><p className="form-message error" role="alert">{state.error}</p><button type="button" className="button" onClick={load}>Try again</button></div>
      )}
      {state.status === 'ready' && state.items.length === 0 && (
        <div className="empty-state"><h2>No follow-ups</h2><p>{filtered ? 'None match these filters.' : 'A 1- or 2-star rating opens one here.'}</p></div>
      )}
      {state.status === 'ready' && state.items.length > 0 && (
        <div className="officer-complaint-list">
          {state.items.map((item) => (
            <article className="officer-card" key={item.id}>
              <div className="officer-card-header">
                <div>
                  <span className={`resolution-banner banner-${followUpTone(item.status)} follow-up-status`}>{item.status}</span>
                  <h2>{item.issue.category} • {item.issue.location_label || 'no location'}</h2>
                  <p className="officer-meta">
                    Work by {item.rated_officer?.name} rated <strong>{starText(item.rating.stars)}</strong> •
                    {' '}{item.assigned_officer ? `assigned to ${item.assigned_officer.name}` : 'not assigned'} • updated {formatDateTime(item.updated_at)}
                  </p>
                  <p><strong>Why:</strong> {item.rating.explanation}</p>
                </div>
                <button type="button" className="button" aria-expanded={openId === item.id} onClick={() => toggle(item.id)}>
                  {openId === item.id ? 'Close details' : 'Open case'}
                </button>
              </div>
              {openId === item.id && (
                !detail ? <p className="page-state">Loading case…</p>
                  : detail.error ? <p className="form-message error" role="alert">{detail.error}</p>
                    : (
                      <>
                        <FollowUpEvents events={detail.followUp.events} />
                        <CaseControls followUp={detail.followUp} officers={officers} onChanged={changed} />
                      </>
                    )
              )}
            </article>
          ))}
        </div>
      )}
      <Pager total={state.total} limit={state.limit} offset={state.offset} onChange={(offset) => setFilters({ ...filters, offset })} />
    </section>
  )
}
