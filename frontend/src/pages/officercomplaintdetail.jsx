/**
 * OfficerComplaintDetail
 *
 * A dedicated complaint-detail view for Officers/Admins. Shows all the
 * standard complaint metadata (same as the citizen view) PLUS the
 * WorkUpdatePanel so the officer can record field-work evidence.
 *
 * Reached via /officer/complaints/:id — a protected route added in App.jsx.
 * Does NOT replace or modify the existing citizen ComplaintDetails page.
 */

import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AppShell from '../components/appshell.jsx'
import WorkUpdatePanel from '../components/WorkUpdatePanel.jsx'
import ResolutionReviewPanel from '../components/ResolutionReviewPanel.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getComplaint } from '../services/complaintservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'

const formatAiValue = (v) => v || 'Not available'

export default function OfficerComplaintDetail() {
  const { id } = useParams()

  const [complaint, setComplaint] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadComplaint = useCallback(async () => {
    try {
      setError('')
      const { data } = await getComplaint(id)
      setComplaint(data.complaint || data)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not load this complaint.'))
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => {
    loadComplaint()
  }, [loadComplaint])

  if (loading) {
    return (
      <AppShell eyebrow="Officer · Complaint" title="Loading…">
        <p className="page-state" aria-live="polite">Loading complaint details…</p>
      </AppShell>
    )
  }

  if (error || !complaint) {
    return (
      <AppShell eyebrow="Officer · Complaint" title="Complaint">
        <p className="form-message error" role="alert">{error || 'Complaint not found.'}</p>
        <Link className="preview-link" to="/officer">← Back to Officer Dashboard</Link>
      </AppShell>
    )
  }

  const ai = complaint.ai_analysis

  return (
    <AppShell
      eyebrow="Officer · Complaint Detail"
      title={complaint.title || `Complaint #${complaint.id}`}
    >
      <div className="officer-complaint-detail">
        {/* ── breadcrumb ── */}
        <Link className="preview-link" to="/officer">
          ← Back to Officer Dashboard
        </Link>

        {/* ── complaint summary card ── */}
        <section className="officer-detail-summary">
          <div className="officer-detail-meta-row">
            <span className={`status status-${String(complaint.status || 'Pending').toLowerCase().replace(' ', '-')}`}>
              {complaint.status || 'Pending'}
            </span>
            {ai?.priority && (
              <span className={`priority-tag priority-${ai.priority.toLowerCase()}`}>
                {ai.priority} Priority
              </span>
            )}
            <span className="complaint-category">{complaint.category || 'General'}</span>
          </div>

          <p className="officer-meta">
            📍 {complaint.location}
            {complaint.latitude != null && complaint.longitude != null && (
              <> ({Number(complaint.latitude).toFixed(5)}, {Number(complaint.longitude).toFixed(5)})</>
            )}
            {' · '}Reported {formatDateTime(complaint.created_at)}
          </p>

          <p className="officer-card-desc">{complaint.description}</p>

          {complaint.image_url && (
            <div className="complaint-image-box">
              <span className="ai-analysis-label">Original Report Photo</span>
              <img
                src={complaint.image_url}
                alt={complaint.title}
                className="complaint-detail-img"
              />
            </div>
          )}

          {/* rejection notice */}
          {complaint.rejection && (
            <p className="form-message error" role="status">
              <strong>Rejected — Out of Scope</strong>
              <br />
              Reason: {complaint.rejection.reason}
              {complaint.rejection.explanation ? ` — ${complaint.rejection.explanation}` : ''}
              <br />
              Reviewed: {formatDateTime(complaint.rejection.reviewed_at)}
            </p>
          )}

          {/* civic issue grouping */}
          {complaint.civic_issue && (
            <p className="form-message">
              Grouped with civic issue reported by{' '}
              {complaint.civic_issue.report_count} citizen
              {complaint.civic_issue.report_count === 1 ? '' : 's'}.
              Issue status:{' '}
              <span
                className={`status status-${String(complaint.civic_issue.status).toLowerCase().replace(' ', '-')}`}
              >
                {complaint.civic_issue.status}
              </span>
            </p>
          )}
        </section>

        {/* ── AI analysis strip ── */}
        {ai && (
          <section className="ai-analysis">
            <h2>AI Analysis</h2>
            <div className="ai-analysis-grid">
              <div>
                <span className="ai-analysis-label">Category</span>
                <strong>{formatAiValue(complaint.category)}</strong>
              </div>
              <div>
                <span className="ai-analysis-label">Priority</span>
                <strong>{formatAiValue(ai.priority)}</strong>
              </div>
              <div>
                <span className="ai-analysis-label">Department</span>
                <strong>{formatAiValue(ai.department)}</strong>
              </div>
            </div>
            <div className="ai-analysis-section">
              <span className="ai-analysis-label">Visual observation</span>
              <p>{formatAiValue(ai.visual_observation)}</p>
            </div>
            <div className="ai-analysis-section">
              <span className="ai-analysis-label">Summary</span>
              <p>{formatAiValue(ai.summary)}</p>
            </div>
          </section>
        )}

        {/* ── field-work evidence panel ── */}
        <WorkUpdatePanel
          complaintId={complaint.id}
          onUpdateSubmitted={loadComplaint}
        />

        {/* ── final resolution review panel ── */}
        <ResolutionReviewPanel
          complaintId={complaint.id}
          complaintStatus={complaint.status}
          onReviewSubmitted={loadComplaint}
        />
      </div>
    </AppShell>
  )
}
