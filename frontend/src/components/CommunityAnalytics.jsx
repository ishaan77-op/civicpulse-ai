import { useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getCommunityAnalytics } from '../services/communityservice.js'

export default function CommunityAnalytics() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    getCommunityAnalytics()
      .then(({ data: body }) => { if (active) setData(body) })
      .catch((err) => { if (active) setError(apiErrorMessage(err, 'Failed to load community analytics.')) })
    return () => { active = false }
  }, [])

  if (error) return <p className="form-message error" role="alert">{error}</p>
  if (!data) return <p className="page-state">Loading community intelligence...</p>

  const s = data.summary
  const categories = Object.entries(data.engagement_by_category || {})
  const maxEngagement = Math.max(1, ...categories.map(([, e]) => e.supports + e.verifications + e.comments))

  return (
    <>
      <section className="admin-kpi-grid">
        <div className="admin-kpi-card">
          <span className="kpi-title">Active Civic Issues</span>
          <strong className="kpi-value">{s.active_civic_issues}</strong>
          <small className="kpi-sub">{s.resolved_civic_issues} resolved &bull; {s.public_civic_issues} public in total</small>
        </div>
        <div className="admin-kpi-card">
          <span className="kpi-title">Community Participants</span>
          <strong className="kpi-value highlight">{s.community_participants}</strong>
          <small className="kpi-sub">Supported, verified or commented</small>
        </div>
        <div className="admin-kpi-card">
          <span className="kpi-title">Supports &amp; Verifications</span>
          <strong className="kpi-value">{s.total_supports} / {s.total_verifications}</strong>
          <small className="kpi-sub">{s.verifications_last_7_days} verifications in the last 7 days</small>
        </div>
        <div className="admin-kpi-card">
          <span className="kpi-title">Average Impact Score</span>
          <strong className="kpi-value">{s.average_impact_score}</strong>
          <small className="kpi-sub">Across {s.citizens_with_impact} citizens with scored activity</small>
        </div>
        <div className="admin-kpi-card">
          <span className="kpi-title">Community-Confirmed Unresolved</span>
          <strong className="kpi-value warning">{s.community_confirmed_unresolved}</strong>
          <small className="kpi-sub" title={data.definitions.community_confirmed_unresolved}>{data.definitions.community_confirmed_unresolved}</small>
        </div>
        <div className="admin-kpi-card">
          <span className="kpi-title">Disputed Resolutions</span>
          <strong className="kpi-value warning">{s.disputed_resolutions}</strong>
          <small className="kpi-sub">{data.definitions.disputed_resolutions}</small>
        </div>
        <div className="admin-kpi-card">
          <span className="kpi-title">Comments</span>
          <strong className="kpi-value">{s.total_comments}</strong>
          <small className="kpi-sub">{s.comments_awaiting_review} awaiting moderation</small>
        </div>
      </section>

      <section className="admin-breakdown-grid">
        <div className="breakdown-card">
          <h2>Community Engagement by Category</h2>
          <div className="breakdown-list">
            {categories.length === 0 ? (
              <p className="empty-breakdown">No public civic issues yet.</p>
            ) : (
              categories.map(([category, e]) => {
                const engagement = e.supports + e.verifications + e.comments
                return (
                  <div key={category} className="bar-row">
                    <div className="bar-label">
                      <span>{category} <small>({e.issues} issues)</small></span>
                      <strong>{e.supports} supports &bull; {e.verifications} verifications &bull; {e.comments} comments</strong>
                    </div>
                    <div className="bar-track">
                      <div className="bar-fill" style={{ width: `${Math.round((engagement / maxEngagement) * 100)}%` }} />
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </section>
      <p className="signal-note">Ward-level engagement is not shown: complaints do not yet record a ward, and deriving one from free-text addresses would be unreliable.</p>
    </>
  )
}
