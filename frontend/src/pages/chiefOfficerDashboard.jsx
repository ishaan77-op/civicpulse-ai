/**
 * ChiefOfficerDashboard
 *
 * Dedicated dashboard for users with role "Chief Officer".
 * Reached via /chief-officer (a protected route in App.jsx).
 *
 * Features:
 *   - Resolution review queue: complaints awaiting final approval.
 *   - Approve / Reject actions per review.
 *   - Rejection requires a rejection reason.
 *
 * Does NOT modify the existing OfficerDashboard or AdminDashboard.
 */

import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/appshell.jsx'
import { apiErrorMessage } from '../services/api.js'
import {
  decideResolutionReview,
  getResolutionQueue,
} from '../services/complaintservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'

export default function ChiefOfficerDashboard() {
  const [queue, setQueue] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')

  // Per-review: { [reviewId]: { deciding: bool, showRejectForm: bool, rejectionNote: '' } }
  const [reviewState, setReviewState] = useState({})

  const fetchQueue = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const { data } = await getResolutionQueue()
      setQueue(data.queue || [])
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not load the resolution queue.'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchQueue()
  }, [fetchQueue])

  // Helpers for per-review state
  const getRS = (reviewId) =>
    reviewState[reviewId] || { deciding: false, showRejectForm: false, rejectionNote: '' }

  const setRS = (reviewId, patch) =>
    setReviewState((prev) => ({
      ...prev,
      [reviewId]: { ...getRS(reviewId), ...patch },
    }))

  const handleApprove = async (reviewId) => {
    try {
      setActionError('')
      setRS(reviewId, { deciding: true })
      await decideResolutionReview(reviewId, 'Approved', null)
      await fetchQueue()
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Could not approve the resolution.'))
    } finally {
      setRS(reviewId, { deciding: false })
    }
  }

  const handleReject = async (reviewId) => {
    const rs = getRS(reviewId)
    if (!rs.rejectionNote.trim()) return
    try {
      setActionError('')
      setRS(reviewId, { deciding: true })
      await decideResolutionReview(reviewId, 'Rejected', rs.rejectionNote.trim())
      await fetchQueue()
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Could not reject the resolution.'))
    } finally {
      setRS(reviewId, { deciding: false, showRejectForm: false, rejectionNote: '' })
    }
  }

  return (
    <AppShell eyebrow="Chief Officer · Review Queue" title="Resolution Review Queue">
      <p className="dashboard-kicker">
        Complaints pending final resolution approval. Review the evidence and make a decision.
      </p>

      {actionError && (
        <p className="form-message error" role="alert">{actionError}</p>
      )}

      {loading ? (
        <p className="page-state">Loading review queue…</p>
      ) : error ? (
        <p className="form-message error" role="alert">{error}</p>
      ) : queue.length === 0 ? (
        <p className="work-update-empty">
          ✅ No complaints pending resolution review. All caught up!
        </p>
      ) : (
        <div className="resolution-queue-list">
          {queue.map(({ review, complaint }) => {
            const rs = getRS(review.id)
            return (
              <article
                key={review.id}
                className="resolution-queue-card"
                id={`resolution-review-${review.id}`}
              >
                {/* Complaint summary */}
                <div className="resolution-card-header">
                  <span
                    className={`status status-${String(complaint.status || 'pending-review').toLowerCase().replace(/\s+/g, '-')}`}
                  >
                    {complaint.status}
                  </span>
                  <strong className="resolution-card-title">
                    #{complaint.id} — {complaint.title}
                  </strong>
                  <span className="complaint-category">{complaint.category}</span>
                </div>

                <p className="resolution-card-meta">
                  📍 {complaint.location}
                  {' · '}Reported {formatDateTime(complaint.created_at)}
                </p>

                <p className="officer-card-desc">{complaint.description}</p>

                {/* Resolution evidence */}
                <div className="resolution-evidence-section">
                  <span className="ai-analysis-label">Completion Note</span>
                  <p className="resolution-completion-note">{review.completion_note}</p>

                  {review.image_url && (
                    <div className="resolution-evidence-photo">
                      <span className="ai-analysis-label">Final Evidence Photo</span>
                      <img
                        src={review.image_url}
                        alt="Final resolution evidence"
                        className="complaint-detail-img"
                      />
                    </div>
                  )}

                  {review.latitude != null && (
                    <p className="work-update-gps">
                      📍 Officer GPS: {Number(review.latitude).toFixed(5)}, {Number(review.longitude).toFixed(5)}
                    </p>
                  )}

                  <p className="resolution-card-meta">
                    Submitted by <strong>{review.officer_name || `Officer #${review.submitted_by}`}</strong>
                    {' · '}{formatDateTime(review.submitted_at)}
                  </p>
                </div>

                {/* Decision actions */}
                {!rs.showRejectForm && (
                  <div className="officer-card-actions">
                    <button
                      type="button"
                      className="button button-primary"
                      id={`btn-approve-${review.id}`}
                      disabled={rs.deciding}
                      onClick={() => handleApprove(review.id)}
                    >
                      {rs.deciding ? 'Processing…' : '✅ Approve Resolution'}
                    </button>
                    <button
                      type="button"
                      className="button button-outline"
                      id={`btn-reject-open-${review.id}`}
                      disabled={rs.deciding}
                      onClick={() => setRS(review.id, { showRejectForm: true })}
                    >
                      ❌ Reject
                    </button>
                  </div>
                )}

                {/* Inline rejection form */}
                {rs.showRejectForm && (
                  <div className="resolution-reject-form">
                    <label htmlFor={`reject-note-${review.id}`}>
                      Rejection reason <span aria-hidden="true">*</span>
                    </label>
                    <textarea
                      id={`reject-note-${review.id}`}
                      rows={3}
                      value={rs.rejectionNote}
                      onChange={(e) => setRS(review.id, { rejectionNote: e.target.value })}
                      placeholder="Describe why the evidence is insufficient…"
                    />
                    <div className="modal-actions">
                      <button
                        type="button"
                        className="button"
                        disabled={rs.deciding}
                        onClick={() => setRS(review.id, { showRejectForm: false, rejectionNote: '' })}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        className="button button-danger"
                        id={`btn-reject-submit-${review.id}`}
                        disabled={rs.deciding || !rs.rejectionNote.trim()}
                        onClick={() => handleReject(review.id)}
                      >
                        {rs.deciding ? 'Rejecting…' : 'Confirm Rejection'}
                      </button>
                    </div>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}
    </AppShell>
  )
}
