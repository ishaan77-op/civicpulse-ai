import { useState } from 'react'
import { Link } from 'react-router-dom'
import { apiErrorMessage } from '../services/api.js'
import { removeSupport, supportIssue } from '../services/communityservice.js'
import { CATEGORY_ICONS, plural, relativeTime, statusBadgeClass } from '../utils/community.js'

export default function CommunityIssueCard({ issue, canEngage, onChange }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const { official, community, viewer } = issue
  const verification = community.verification || {}
  const isResolved = official.status === 'Resolved'
  const detailPath = `/community/issues/${issue.id}`

  const toggleSupport = async () => {
    try {
      setBusy(true)
      setError('')
      const { data } = viewer.supported ? await removeSupport(issue.id) : await supportIssue(issue.id)
      // Counts always come back from the server - never incremented locally.
      onChange({
        ...issue,
        community: { ...issue.community, supporters: data.community.supporters },
        viewer: { ...issue.viewer, supported: data.community.viewer.supported },
      })
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not update your support.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="civic-card">
      <Link to={detailPath} className="civic-card-link">
        <header className="civic-card-head">
          <span className="civic-category">
            <span aria-hidden="true">{CATEGORY_ICONS[issue.category] || '📍'}</span> {issue.category}
          </span>
          <span className="civic-time">{relativeTime(issue.updated_at)}</span>
        </header>

        <h2 className="civic-card-title">{issue.title}</h2>
        <p className="civic-location">
          📍 {issue.location_label || 'Nashik'}
          {typeof issue.distance_m === 'number' && (
            <span> · {issue.distance_m < 1000 ? `${issue.distance_m} m` : `${(issue.distance_m / 1000).toFixed(1)} km`} away</span>
          )}
        </p>

        {issue.image_url && (
          <div className="civic-card-media">
            <img src={issue.image_url} alt={`Citizen evidence: ${issue.category}`} loading="lazy" />
          </div>
        )}

        {issue.summary && <p className="civic-summary">{issue.summary}</p>}

        <div className="civic-official-row" aria-label="Official municipal information">
          <span className="civic-row-label">Official</span>
          <span className={statusBadgeClass(official.status)}>{official.status}</span>
          {official.priority && (
            <span className={`priority-tag priority-${official.priority.toLowerCase()}`}>{official.priority}</span>
          )}
          <span className="civic-reports">{plural(issue.report_count, 'report')}</span>
        </div>

        <ul className="civic-signal-row" aria-label="Community signal">
          <li><strong>{community.supporters}</strong> {community.supporters === 1 ? 'citizen supports' : 'citizens support'}</li>
          <li><strong>{verification.still_exists || 0}</strong> say still present</li>
          {verification.resolved > 0 && <li><strong>{verification.resolved}</strong> say resolved</li>}
          <li><strong>{community.comments}</strong> {community.comments === 1 ? 'comment' : 'comments'}</li>
        </ul>

        {issue.trending && (
          <p className="civic-trend-note">
            Trending: {Object.entries(issue.trending.recent_activity).filter(([, n]) => n > 0).map(([k, n]) => `${n} new ${k}`).join(' · ')} in the last {issue.trending.window_days} days
          </p>
        )}
      </Link>

      <footer className="civic-actions">
        {canEngage && (
          <button
            type="button"
            className={`civic-action ${viewer.supported ? 'is-active' : ''}`}
            onClick={toggleSupport}
            disabled={busy || (isResolved && !viewer.supported)}
            aria-pressed={viewer.supported}
            title={isResolved && !viewer.supported ? 'Officially resolved - verify it instead if it is still present' : undefined}
          >
            ▲ {viewer.supported ? 'Supporting' : 'Support'}
          </button>
        )}
        <Link className="civic-action" to={`${detailPath}#comments`}>💬 Comment</Link>
        <Link className={`civic-action ${viewer.verification ? 'is-active' : ''}`} to={`${detailPath}#verify`}>
          ✓ {viewer.verification ? 'Verified' : 'Verify'}
        </Link>
      </footer>
      {error && <p className="form-message error civic-card-error" role="alert">{error}</p>}
    </article>
  )
}
