import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiErrorMessage } from '../services/api.js'
import { getMyActivity, getMyImpact } from '../services/communityservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'

// Everything shown here is computed by the backend from recorded events -
// this component only displays it.
export default function ImpactPanel() {
  const [impact, setImpact] = useState(null)
  const [activity, setActivity] = useState([])
  const [error, setError] = useState('')
  const [showRules, setShowRules] = useState(false)

  useEffect(() => {
    let active = true
    Promise.all([getMyImpact(), getMyActivity({ limit: 10 })])
      .then(([impactRes, activityRes]) => {
        if (!active) return
        setImpact(impactRes.data)
        setActivity(activityRes.data.events || [])
      })
      .catch((err) => { if (active) setError(apiErrorMessage(err, 'We could not load your community impact.')) })
    return () => { active = false }
  }, [])

  if (error) return <p className="form-message error" role="alert">{error}</p>
  if (!impact) return <p className="page-state" aria-live="polite">Loading your community impact…</p>

  const stats = [
    ['Issues reported', impact.stats.issues_reported],
    ['Issues supported', impact.stats.issues_supported],
    ['Verifications', impact.stats.verifications],
    ['Comments', impact.stats.comments],
    ['Resolved issues', impact.stats.resolved_issues],
  ]

  return (
    <section className="impact-panel">
      <div className="impact-hero">
        <div>
          <p className="section-label">Your public civic identity</p>
          <h2>{impact.handle}</h2>
          <p className="signal-note">This is the only name other citizens ever see. Your name and email are never shown in the community.</p>
        </div>
        <div className="impact-score" aria-label={`Community Impact Score ${impact.impact_score}`}>
          <span>Community Impact</span>
          <strong>⭐ {impact.impact_score}</strong>
        </div>
      </div>

      <dl className="impact-stats">
        {stats.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
        ))}
      </dl>

      <div className="impact-columns">
        <div>
          <h3 className="issue-subhead">Recent impact</h3>
          {activity.length === 0 ? (
            <p className="signal-note">No scored activity yet. <Link className="text-link" to="/community">Explore the community</Link> to get started.</p>
          ) : (
            <ul className="impact-activity">
              {activity.map((event) => (
                <li key={event.id}>
                  <span>{event.label}</span>
                  <time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time>
                  <strong className={event.points < 0 ? 'impact-negative' : 'impact-positive'}>{event.points > 0 ? `+${event.points}` : event.points}</strong>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h3 className="issue-subhead">How the score works</h3>
          <p className="signal-note">
            The score rewards meaningful civic contribution, not popularity. Points are only ever awarded by the server
            for verified actions, and penalties come only from a confirmed human review, never from AI alone.
          </p>
          <button type="button" className="signal-withdraw" onClick={() => setShowRules(!showRules)} aria-expanded={showRules}>
            {showRules ? 'Hide scoring rules' : 'Show scoring rules'}
          </button>
          {showRules && (
            <ul className="impact-rules">
              {impact.rules.weights.map((rule) => (
                <li key={rule.event_type}><span>{rule.label}</span><strong>{rule.points > 0 ? `+${rule.points}` : rule.points}</strong></li>
              ))}
              <li className="impact-rules-note">
                Support and verification points are earned once per issue; complaint and comment points once per issue;
                comments need at least {impact.rules.min_constructive_comment_length} characters; daily limits apply.
              </li>
            </ul>
          )}
        </div>
      </div>
    </section>
  )
}
