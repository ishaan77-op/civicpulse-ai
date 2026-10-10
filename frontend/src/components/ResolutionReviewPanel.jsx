/**
 * ResolutionReviewPanel
 *
 * Rendered inside the Officer complaint-detail view (OfficerComplaintDetail).
 * Allows an Officer to:
 *   1. See the current resolution review status for a complaint.
 *   2. Submit a final-resolution evidence request (note + photo + optional GPS).
 *   3. See a rejection reason if the Chief Officer rejected their request.
 *   4. Re-submit corrected evidence after a rejection.
 *
 * Security: this component is only mounted for Officers (and Admins).
 * The backend independently enforces the same permissions.
 *
 * Design principles:
 *   - Reuses CameraCapture for the photo (same architecture as WorkUpdatePanel).
 *   - GPS via navigator.geolocation (same approach as MapPicker).
 *   - Server timestamp is authoritative; the form never sends one.
 */

import { useCallback, useEffect, useState } from 'react'
import CameraCapture from './CameraCapture.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getResolutionReview, submitResolutionReview } from '../services/complaintservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'

// Status values that mean the complaint is no longer eligible for a new
// resolution submission.
const TERMINAL_STATUSES = ['Resolved']

export default function ResolutionReviewPanel({ complaintId, complaintStatus, onReviewSubmitted }) {
  const [review, setReview] = useState(null)
  const [loadingReview, setLoadingReview] = useState(true)
  const [loadError, setLoadError] = useState('')

  // form state
  const [showForm, setShowForm] = useState(false)
  const [note, setNote] = useState('')
  const [image, setImage] = useState(null)
  const [gpsState, setGpsState] = useState({ latitude: null, longitude: null, loading: false, error: '' })
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')
  const [submitSuccess, setSubmitSuccess] = useState('')
  const [cameraKey, setCameraKey] = useState(0)

  const fetchReview = useCallback(async () => {
    try {
      setLoadingReview(true)
      setLoadError('')
      const { data } = await getResolutionReview(complaintId)
      setReview(data.review || null)
    } catch (err) {
      setLoadError(apiErrorMessage(err, 'Could not load resolution review.'))
    } finally {
      setLoadingReview(false)
    }
  }, [complaintId])

  useEffect(() => {
    fetchReview()
  }, [fetchReview])

  // ── GPS ──────────────────────────────────────────────────────────────────

  const captureGps = () => {
    if (!navigator.geolocation) {
      setGpsState((s) => ({ ...s, error: 'Geolocation not supported.' }))
      return
    }
    setGpsState((s) => ({ ...s, loading: true, error: '' }))
    navigator.geolocation.getCurrentPosition(
      (pos) => setGpsState({ latitude: pos.coords.latitude, longitude: pos.coords.longitude, loading: false, error: '' }),
      () => setGpsState((s) => ({ ...s, loading: false, error: 'Could not obtain GPS. Check permissions.' })),
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  const clearGps = () => setGpsState({ latitude: null, longitude: null, loading: false, error: '' })

  // ── Form ─────────────────────────────────────────────────────────────────

  const openForm = () => {
    setNote('')
    setImage(null)
    setGpsState({ latitude: null, longitude: null, loading: false, error: '' })
    setSubmitError('')
    setSubmitSuccess('')
    setCameraKey((k) => k + 1)
    setShowForm(true)
  }

  const closeForm = () => { if (!submitting) setShowForm(false) }

  const submit = async (e) => {
    e.preventDefault()
    setSubmitError('')
    setSubmitSuccess('')

    if (!note.trim()) {
      setSubmitError('A completion note is required.')
      return
    }
    if (!image) {
      setSubmitError('A final evidence photo is required.')
      return
    }

    const formData = new FormData()
    formData.append('completion_note', note.trim())
    formData.append('image', image)
    if (gpsState.latitude != null) {
      formData.append('latitude', String(gpsState.latitude))
      formData.append('longitude', String(gpsState.longitude))
    }

    try {
      setSubmitting(true)
      await submitResolutionReview(complaintId, formData)
      setSubmitSuccess('Resolution request submitted. Awaiting Chief Officer review.')
      setShowForm(false)
      await fetchReview()
      onReviewSubmitted?.()
    } catch (err) {
      setSubmitError(apiErrorMessage(err, 'Could not submit the resolution request.'))
    } finally {
      setSubmitting(false)
    }
  }

  // ── Derived state ────────────────────────────────────────────────────────

  const isPending = review && review.decision === null
  const isApproved = review && review.decision === 'Approved'
  const isRejected = review && review.decision === 'Rejected'
  const isResolved = TERMINAL_STATUSES.includes(complaintStatus)

  // Can the officer submit (or resubmit)? Yes unless:
  //   - already resolved (terminal)
  //   - a pending review is waiting for Chief Officer decision
  const canSubmit = !isResolved && !isPending

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <section className="resolution-review-panel">
      <div className="work-update-panel-header">
        <h2>Final Resolution Review</h2>
        {canSubmit && !showForm && (
          <button
            type="button"
            className="button button-primary"
            id="btn-submit-resolution-review"
            onClick={openForm}
          >
            {isRejected ? '🔄 Resubmit Resolution Evidence' : '✅ Submit for Resolution Review'}
          </button>
        )}
      </div>

      {/* ── Rejection notice ── */}
      {isRejected && (
        <div className="resolution-rejection-notice" role="alert">
          <strong>❌ Review Rejected</strong>
          <p>
            Rejected by {review.reviewer_name || `Chief Officer #${review.reviewed_by}`}
            {' · '}{formatDateTime(review.reviewed_at)}
          </p>
          <p className="resolution-rejection-reason">Reason: {review.rejection_note}</p>
          <p>Please correct the evidence and re-submit.</p>
        </div>
      )}

      {/* ── Pending notice ── */}
      {isPending && (
        <div className="resolution-pending-notice" role="status">
          <strong>⏳ Pending Chief Officer Review</strong>
          <p>
            Submitted by {review.officer_name || `Officer #${review.submitted_by}`}
            {' · '}{formatDateTime(review.submitted_at)}
          </p>
          <p className="resolution-pending-note">{review.completion_note}</p>
          {review.image_url && (
            <div className="resolution-evidence-photo">
              <span className="ai-analysis-label">Final Evidence Photo</span>
              <img src={review.image_url} alt="Final evidence" className="complaint-detail-img" />
            </div>
          )}
          {review.latitude != null && (
            <p className="work-update-gps">
              📍 GPS: {Number(review.latitude).toFixed(5)}, {Number(review.longitude).toFixed(5)}
            </p>
          )}
        </div>
      )}

      {/* ── Approved notice ── */}
      {isApproved && (
        <div className="resolution-approved-notice" role="status">
          <strong>✅ Resolution Approved</strong>
          <p>
            Approved by {review.reviewer_name || `Chief Officer #${review.reviewed_by}`}
            {' · '}{formatDateTime(review.reviewed_at)}
          </p>
        </div>
      )}

      {/* ── Submission form ── */}
      {showForm && canSubmit && (
        <form
          className="app-form work-update-form"
          onSubmit={submit}
          aria-label="Submit final resolution evidence"
        >
          <h3>Final Resolution Evidence</h3>
          <p className="resolution-form-help">
            Provide a completion note and evidence photo for Chief Officer review.
            The complaint will not be marked Resolved until the Chief Officer approves.
          </p>

          <label>
            Completion note <span aria-hidden="true">*</span>
            <textarea
              id="resolution-completion-note"
              rows={4}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Describe the completed work and any final observations…"
              required
            />
          </label>

          {/* GPS capture */}
          <div className="work-update-gps-block">
            <span className="ai-analysis-label">Officer GPS (optional)</span>
            {gpsState.latitude != null ? (
              <div className="gps-captured">
                <span>📍 {Number(gpsState.latitude).toFixed(5)}, {Number(gpsState.longitude).toFixed(5)}</span>
                <button type="button" className="button" onClick={clearGps}>Clear GPS</button>
              </div>
            ) : (
              <button
                type="button"
                className="button"
                id="btn-resolution-capture-gps"
                onClick={captureGps}
                disabled={gpsState.loading}
              >
                {gpsState.loading ? 'Acquiring GPS…' : '📡 Capture GPS location'}
              </button>
            )}
            {gpsState.error && <p className="form-message error" role="alert">{gpsState.error}</p>}
          </div>

          {/* Final evidence photo — mandatory */}
          <div className="work-update-camera-block">
            <span className="ai-analysis-label">Final evidence photo <span aria-hidden="true">*</span></span>
            <CameraCapture key={cameraKey} onCapture={(file) => setImage(file)} />
          </div>

          {submitError && <p className="form-message error" role="alert">{submitError}</p>}

          <div className="modal-actions">
            <button type="button" className="button" onClick={closeForm} disabled={submitting}>
              Cancel
            </button>
            <button
              type="submit"
              className="button button-primary"
              id="btn-submit-resolution-evidence"
              disabled={submitting}
            >
              {submitting ? 'Submitting…' : 'Submit for Review'}
            </button>
          </div>
        </form>
      )}

      {submitSuccess && !showForm && (
        <p className="form-message success" role="status">{submitSuccess}</p>
      )}

      {/* ── Load state ── */}
      {loadingReview && <p className="page-state">Loading review status…</p>}
      {loadError && <p className="form-message error" role="alert">{loadError}</p>}

      {!loadingReview && !review && !showForm && canSubmit && (
        <p className="work-update-empty">No resolution review submitted yet for this complaint.</p>
      )}
    </section>
  )
}
