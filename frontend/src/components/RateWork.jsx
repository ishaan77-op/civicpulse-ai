import { useCallback, useEffect, useRef, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getApprovedWork, getReviewRatings, rateReview } from '../services/performanceservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'
import { PAGE_SIZE, cleanParams, isLowRating, stars as starText, validateRating } from '../utils/performance.js'
import ImageLightbox from './ImageLightbox.jsx'
import ProtectedImage from './ProtectedImage.jsx'
import Pager from './Pager.jsx'

function RatingHistory({ reviewId }) {
  const [state, setState] = useState({ status: 'loading', ratings: [], error: '' })
  useEffect(() => {
    let active = true
    getReviewRatings(reviewId)
      .then(({ data }) => { if (active) setState({ status: 'ready', ratings: data.ratings || [], error: '' }) })
      .catch((err) => { if (active) setState({ status: 'error', ratings: [], error: apiErrorMessage(err, 'Could not load the rating history.') }) })
    return () => { active = false }
  }, [reviewId])
  if (state.status === 'loading') return <p className="page-state">Loading rating history…</p>
  if (state.status === 'error') return <p className="form-message error" role="alert">{state.error}</p>
  return (
    <ol className="resolution-log" aria-label="Rating history, oldest first">
      {state.ratings.map((rating) => (
        <li key={rating.id}>
          <strong>{starText(rating.stars)}</strong> {rating.is_effective ? <span className="resolution-chip chip-eligible">Current</span> : <span className="resolution-chip chip-blocked">Superseded</span>}
          <p className="resolution-muted">{formatDateTime(rating.created_at)} by {rating.rated_by?.name}{rating.supersedes_rating_id ? ` • revises #${rating.supersedes_rating_id}` : ''}</p>
          {rating.explanation && <p>{rating.explanation}</p>}
        </li>
      ))}
    </ol>
  )
}

function RatingForm({ work, onSaved }) {
  const existing = work.rating
  const [value, setValue] = useState(existing?.stars || 0)
  const [explanation, setExplanation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)

  const submit = async (event) => {
    event.preventDefault()
    if (inFlight.current) return
    const problem = validateRating({ stars: value, explanation }, existing)
    if (problem) { setError(problem); return }
    inFlight.current = true
    setBusy(true)
    setError('')
    try {
      const { data } = await rateReview(work.resolution_review_id, {
        stars: value,
        ...(explanation.trim() ? { explanation: explanation.trim() } : {}),
        ...(existing ? { revises_rating_id: existing.id } : {}),
      })
      await onSaved(data)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save the rating.'))
      // A 409 means someone else rated or revised first: show the latest.
      if (err.response?.status === 409) await onSaved(null)
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  return (
    <form className="app-form resolution-form" onSubmit={submit}>
      <fieldset className="resolution-fieldset" disabled={busy}>
        <legend>{existing ? `Revise rating (currently ${existing.stars}★)` : 'Rate this completed job'}</legend>
        <div className="star-picker" role="radiogroup" aria-label="Star rating">
          {[1, 2, 3, 4, 5].map((n) => (
            <button key={n} type="button" role="radio" aria-checked={value === n}
              aria-label={`${n} star${n === 1 ? '' : 's'}`} className={`star-btn ${value >= n ? 'on' : ''}`} onClick={() => setValue(n)}>
              ★
            </button>
          ))}
        </div>
        <label>
          {isLowRating(value) ? 'Explanation (required for 1-2 stars)' : existing ? 'Why is the rating changing? (required)' : 'Explanation (optional)'}
          <textarea rows="3" value={explanation} onChange={(event) => setExplanation(event.target.value)} />
        </label>
      </fieldset>
      {isLowRating(value) && (
        <p className="resolution-muted">A 1-2 star rating opens a corrective follow-up that you then assign. It does not change the issue or penalise anyone.</p>
      )}
      {error && <p className="form-message error" role="alert">{error}</p>}
      <button type="submit" className="button button-primary" disabled={busy || value === 0}>{busy ? 'Saving…' : existing ? 'Save revision' : 'Save rating'}</button>
    </form>
  )
}

export default function RateWork({ officers }) {
  const [filters, setFilters] = useState({ rated: 'false', officer_id: '', offset: 0 })
  const [state, setState] = useState({ status: 'loading', items: [], total: 0, limit: PAGE_SIZE, offset: 0, error: '' })
  const [openId, setOpenId] = useState(null)
  const [historyId, setHistoryId] = useState(null)
  const [zoomed, setZoomed] = useState(null)
  const [notice, setNotice] = useState('')

  const load = useCallback(async () => {
    try {
      const { data } = await getApprovedWork(cleanParams({
        rated: filters.rated === 'all' ? '' : filters.rated, officer_id: filters.officer_id, limit: PAGE_SIZE, offset: filters.offset,
      }))
      setState({ status: 'ready', items: data.approved_work || [], total: data.total, limit: data.limit, offset: data.offset, error: '' })
    } catch (err) {
      setState((current) => ({ ...current, status: 'error', error: apiErrorMessage(err, 'Could not load approved work.') }))
    }
  }, [filters])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const saved = async (result) => {
    if (result) {
      setNotice(result.follow_up && result.follow_up.status === 'Awaiting Assignment'
        ? 'Rating saved. A corrective follow-up is waiting for you to assign it.' : 'Rating saved.')
      setOpenId(null)
    }
    await load()
  }

  return (
    <section>
      <p className="resolution-kicker">
        Rating a completed job is a separate decision from approving its resolution. It never changes the issue's status.
      </p>
      <div className="officer-controls">
        <div className="filter-group resolution-filters">
          <select aria-label="Rating state" value={filters.rated} onChange={(e) => setFilters({ ...filters, rated: e.target.value, offset: 0 })}>
            <option value="false">Not yet rated</option>
            <option value="true">Already rated</option>
            <option value="all">All approved work</option>
          </select>
          <select aria-label="Filter by officer" value={filters.officer_id} onChange={(e) => setFilters({ ...filters, officer_id: e.target.value, offset: 0 })}>
            <option value="">All officers</option>
            {officers.map((officer) => <option key={officer.id} value={officer.id}>{officer.name}</option>)}
          </select>
        </div>
      </div>
      {notice && <p className="resolution-success" role="status">{notice}</p>}
      {state.status === 'loading' && <p className="page-state">Loading approved work…</p>}
      {state.status === 'error' && (
        <div><p className="form-message error" role="alert">{state.error}</p><button type="button" className="button" onClick={load}>Try again</button></div>
      )}
      {state.status === 'ready' && state.items.length === 0 && (
        <div className="empty-state"><h2>No approved work matches</h2><p>Approved resolutions appear here to be rated.</p></div>
      )}
      {state.status === 'ready' && state.items.length > 0 && (
        <div className="officer-complaint-list">
          {state.items.map((work) => (
            <article className="officer-card" key={work.resolution_review_id}>
              <div className="officer-card-header">
                <div>
                  <span className="complaint-category">{work.issue.category}</span>
                  <h2>{work.issue.location_label || 'Location not provided'}</h2>
                  <p className="officer-meta">
                    Work by {work.officer?.name || 'unknown Officer'} • approved {formatDateTime(work.approved_at)} • issue {work.issue.status}
                  </p>
                  {work.rating
                    ? <p><strong>{starText(work.rating.stars)}</strong> {work.follow_up && <span className="resolution-chip chip-blocked">Follow-up: {work.follow_up.status}</span>}</p>
                    : <p className="resolution-muted">Not rated yet</p>}
                  <div className="rate-evidence">
                    <button type="button" className="ba-zoom" onClick={() => setZoomed({ path: work.evidence.image_path, alt: 'Completion evidence submitted by the Officer' })}
                      aria-label="View the Officer's completion photo larger">
                      <ProtectedImage path={work.evidence.image_path} alt="Completion evidence submitted by the Officer" />
                    </button>
                    <p><strong>Officer's completion note:</strong> {work.evidence.completion_note}</p>
                    <p className="resolution-muted">{work.evidence.dispositions} linked report{work.evidence.dispositions === 1 ? '' : 's'} addressed in this submission.</p>
                  </div>
                </div>
                <div className="status-action-box">
                  <button type="button" className="button" aria-expanded={openId === work.resolution_review_id}
                    onClick={() => setOpenId(openId === work.resolution_review_id ? null : work.resolution_review_id)}>
                    {work.rating ? 'Revise rating' : 'Rate'}
                  </button>
                  {work.rating && (
                    <button type="button" className="button" aria-expanded={historyId === work.resolution_review_id}
                      onClick={() => setHistoryId(historyId === work.resolution_review_id ? null : work.resolution_review_id)}>
                      {historyId === work.resolution_review_id ? 'Hide history' : 'Rating history'}
                    </button>
                  )}
                </div>
              </div>
              {historyId === work.resolution_review_id && <RatingHistory reviewId={work.resolution_review_id} />}
              {openId === work.resolution_review_id && <RatingForm work={work} onSaved={saved} />}
            </article>
          ))}
        </div>
      )}
      <Pager total={state.total} limit={state.limit} offset={state.offset} onChange={(offset) => setFilters({ ...filters, offset })} />
      {zoomed && <ImageLightbox path={zoomed.path} alt={zoomed.alt} caption={zoomed.alt} onClose={() => setZoomed(null)} />}
    </section>
  )
}
