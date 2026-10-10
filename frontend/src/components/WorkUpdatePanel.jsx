/**
 * WorkUpdatePanel
 *
 * Rendered inside the Officer complaint-detail view. Lets an Officer:
 *   - View all existing work updates (log) for a complaint
 *   - Submit a new field-work evidence update (note, status, photo, GPS)
 *
 * Design principles
 *   - Reuses CameraCapture for the photo (existing camera architecture)
 *   - GPS is captured via navigator.geolocation (same approach as MapPicker)
 *   - Server timestamp is always authoritative; the form never sends one
 *   - No citizen-visible UI; this component is only mounted for Officers
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import CameraCapture from './CameraCapture.jsx'
import { apiErrorMessage } from '../services/api.js'
import { createWorkUpdate, getWorkUpdates } from '../services/complaintservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'

const ALLOWED_STATUSES = ['Pending', 'In Progress']

// ─── small sub-components ────────────────────────────────────────────────────

function WorkUpdateCard({ wu }) {
  return (
    <div className="work-update-card">
      <div className="work-update-header">
        <span className={`status status-${String(wu.status).toLowerCase().replace(' ', '-')}`}>
          {wu.status}
        </span>
        <span className="work-update-meta">
          {wu.officer_name ?? `Officer #${wu.officer_id}`}
          {' · '}
          {formatDateTime(wu.created_at)}
        </span>
      </div>

      <p className="work-update-note">{wu.note}</p>

      {wu.image_url && (
        <div className="work-update-photo">
          <img
            src={wu.image_url}
            alt="Field-work evidence"
            className="complaint-detail-img"
          />
        </div>
      )}

      {wu.latitude != null && wu.longitude != null && (
        <p className="work-update-gps">
          📍 Officer GPS: {Number(wu.latitude).toFixed(5)}, {Number(wu.longitude).toFixed(5)}
        </p>
      )}
    </div>
  )
}

// ─── main component ──────────────────────────────────────────────────────────

export default function WorkUpdatePanel({ complaintId, onUpdateSubmitted }) {
  const [updates, setUpdates] = useState([])
  const [loadingUpdates, setLoadingUpdates] = useState(true)
  const [loadError, setLoadError] = useState('')

  // form state
  const [showForm, setShowForm] = useState(false)
  const [status, setStatus] = useState('In Progress')
  const [note, setNote] = useState('')
  const [image, setImage] = useState(null)
  const [gpsState, setGpsState] = useState({ latitude: null, longitude: null, loading: false, error: '' })
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [submitSuccess, setSubmitSuccess] = useState('')

  // reset the camera key so CameraCapture fully remounts when the form reopens
  const [cameraKey, setCameraKey] = useState(0)

  const fetchUpdates = useCallback(async () => {
    try {
      setLoadingUpdates(true)
      setLoadError('')
      const { data } = await getWorkUpdates(complaintId)
      setUpdates(data.work_updates || [])
    } catch (err) {
      setLoadError(apiErrorMessage(err, 'Could not load work updates.'))
    } finally {
      setLoadingUpdates(false)
    }
  }, [complaintId])

  useEffect(() => {
    fetchUpdates()
  }, [fetchUpdates])

  // ── GPS capture ─────────────────────────────────────────────────────────

  const captureGps = () => {
    if (!navigator.geolocation) {
      setGpsState((s) => ({ ...s, error: 'Geolocation is not supported by this browser.' }))
      return
    }
    setGpsState((s) => ({ ...s, loading: true, error: '' }))
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGpsState({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          loading: false,
          error: '',
        })
      },
      () => {
        setGpsState((s) => ({
          ...s,
          loading: false,
          error: 'Could not obtain GPS location. Check permissions.',
        }))
      },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  const clearGps = () => setGpsState({ latitude: null, longitude: null, loading: false, error: '' })

  // ── form open / close ───────────────────────────────────────────────────

  const openForm = () => {
    setStatus('In Progress')
    setNote('')
    setImage(null)
    setGpsState({ latitude: null, longitude: null, loading: false, error: '' })
    setSubmitError('')
    setSubmitSuccess('')
    setCameraKey((k) => k + 1)
    setShowForm(true)
  }

  const closeForm = () => {
    if (submitting) return
    setShowForm(false)
  }

  // ── submission ──────────────────────────────────────────────────────────

  const submit = async (e) => {
    e.preventDefault()
    setSubmitError('')
    setSubmitSuccess('')

    if (!note.trim()) {
      setSubmitError('A work/progress note is required.')
      return
    }

    const formData = new FormData()
    formData.append('status', status)
    formData.append('note', note.trim())

    if (image) {
      formData.append('image', image)
    }
    if (gpsState.latitude != null && gpsState.longitude != null) {
      formData.append('latitude', String(gpsState.latitude))
      formData.append('longitude', String(gpsState.longitude))
    }

    try {
      setSubmitting(true)
      await createWorkUpdate(complaintId, formData)
      setSubmitSuccess('Work update submitted.')
      setShowForm(false)
      await fetchUpdates()
      // Let the parent re-load the complaint so its status badge refreshes.
      onUpdateSubmitted?.()
    } catch (err) {
      setSubmitError(apiErrorMessage(err, 'Could not submit the work update.'))
    } finally {
      setSubmitting(false)
    }
  }

  // ── render ───────────────────────────────────────────────────────────────

  return (
    <section className="work-update-panel">
      <div className="work-update-panel-header">
        <h2>Field-Work Updates</h2>
        {!showForm && (
          <button
            type="button"
            className="button button-primary"
            id="btn-add-work-update"
            onClick={openForm}
          >
            + Add Work Update
          </button>
        )}
      </div>

      {/* ── inline form ── */}
      {showForm && (
        <form
          className="app-form work-update-form"
          onSubmit={submit}
          aria-label="Submit field-work update"
        >
          <h3>New Field-Work Update</h3>

          <label>
            Status
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              id="work-update-status"
            >
              {ALLOWED_STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>

          <label>
            Work / progress note <span aria-hidden="true">*</span>
            <textarea
              id="work-update-note"
              rows={4}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Describe the work done, progress made, or observations…"
              required
            />
          </label>

          {/* ── GPS capture ── */}
          <div className="work-update-gps-block">
            <span className="ai-analysis-label">Officer GPS location (optional)</span>
            {gpsState.latitude != null ? (
              <div className="gps-captured">
                <span>
                  📍 {Number(gpsState.latitude).toFixed(5)},{' '}
                  {Number(gpsState.longitude).toFixed(5)}
                </span>
                <button type="button" className="button" onClick={clearGps}>
                  Clear GPS
                </button>
              </div>
            ) : (
              <button
                type="button"
                className="button"
                id="btn-capture-gps"
                onClick={captureGps}
                disabled={gpsState.loading}
              >
                {gpsState.loading ? 'Acquiring GPS…' : '📡 Capture my GPS location'}
              </button>
            )}
            {gpsState.error && (
              <p className="form-message error" role="alert">{gpsState.error}</p>
            )}
          </div>

          {/* ── photo capture ── */}
          <div className="work-update-camera-block">
            <span className="ai-analysis-label">Evidence photo (optional)</span>
            <CameraCapture
              key={cameraKey}
              onCapture={(file) => setImage(file)}
            />
          </div>

          {submitError && (
            <p className="form-message error" role="alert">{submitError}</p>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="button"
              onClick={closeForm}
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="button button-primary"
              id="btn-submit-work-update"
              disabled={submitting}
            >
              {submitting ? 'Submitting…' : 'Submit Update'}
            </button>
          </div>
        </form>
      )}

      {submitSuccess && !showForm && (
        <p className="form-message success" role="status">{submitSuccess}</p>
      )}

      {/* ── work update log ── */}
      {loadingUpdates ? (
        <p className="page-state">Loading work updates…</p>
      ) : loadError ? (
        <p className="form-message error" role="alert">{loadError}</p>
      ) : updates.length === 0 ? (
        <p className="work-update-empty">No field-work updates yet for this complaint.</p>
      ) : (
        <div className="work-update-list">
          {updates.map((wu) => (
            <WorkUpdateCard key={wu.id} wu={wu} />
          ))}
        </div>
      )}
    </section>
  )
}
