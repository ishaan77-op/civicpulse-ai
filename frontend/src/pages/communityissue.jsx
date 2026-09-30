import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { CircleMarker, MapContainer, TileLayer } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import AppShell from '../components/appshell.jsx'
import CommunityComments from '../components/CommunityComments.jsx'
import { apiErrorMessage } from '../services/api.js'
import {
  getCommunityIssue,
  removeSupport,
  supportIssue,
  verifyIssue,
  withdrawVerification,
} from '../services/communityservice.js'
import { CATEGORY_ICONS, VERIFICATION_OPTIONS, plural, statusBadgeClass } from '../utils/community.js'
import { formatDateTime } from '../utils/formatDateTime.js'

const TIMELINE_ICONS = { reported: '📝', ai: '🤖', report_added: '➕', official: '🏛️', community: '👥' }

export default function CommunityIssue() {
  const { id } = useParams()
  const location = useLocation()
  const [issue, setIssue] = useState(null)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      setError('')
      const { data } = await getCommunityIssue(id)
      setIssue(data.issue)
    } catch (err) {
      setError(apiErrorMessage(err, 'We could not load this civic issue.'))
    }
  }, [id])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  // Honour #comments / #verify links from the feed once content exists.
  useEffect(() => {
    if (!issue || !location.hash) return
    document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [issue, location.hash])

  const applyCommunity = (community) => setIssue((current) => ({
    ...current,
    community: { ...current.community, supporters: community.supporters, verification: community.verification },
    viewer: { ...current.viewer, ...community.viewer },
  }))

  const runAction = async (action, successMessage) => {
    try {
      setBusy(true)
      setActionError('')
      setActionMessage('')
      const { data } = await action()
      applyCommunity(data.community)
      setActionMessage(successMessage || data.message)
    } catch (err) {
      setActionError(apiErrorMessage(err, 'That did not go through. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  if (error) {
    return (
      <AppShell eyebrow="Community" title="Civic issue">
        <p className="form-message error" role="alert">{error}</p>
        <p><Link className="text-link" to="/community">← Back to the community feed</Link></p>
      </AppShell>
    )
  }

  if (!issue) {
    return <AppShell eyebrow="Community" title="Civic issue"><p className="page-state" aria-live="polite">Loading civic issue…</p></AppShell>
  }

  const { official, community, viewer } = issue
  const verification = community.verification || {}
  const totalVerifications = (verification.still_exists || 0) + (verification.resolved || 0) + (verification.not_sure || 0)
  const canEngage = viewer.can_engage
  const isResolved = official.status === 'Resolved'

  return (
    <AppShell eyebrow="Community · Civic issue" title={issue.title}>
      <p className="community-back"><Link className="text-link" to="/community">← Community feed</Link></p>

      <div className="issue-layout">
        <div className="issue-main">
          <section className="issue-panel">
            <span className="civic-category"><span aria-hidden="true">{CATEGORY_ICONS[issue.category] || '📍'}</span> {issue.category}</span>
            <p className="civic-location">📍 {issue.location_label || 'Nashik'}</p>
            {issue.summary && (
              <>
                <h2 className="issue-subhead">AI summary</h2>
                <p className="issue-summary">{issue.summary}</p>
              </>
            )}
            <p className="issue-meta">
              First reported {formatDateTime(issue.first_reported_at)} · Last updated {formatDateTime(issue.updated_at)} · {plural(issue.report_count, 'citizen report')}
            </p>
          </section>

          {issue.evidence?.length > 0 && (
            <section className="issue-panel">
              <h2 className="issue-subhead">Citizen evidence</h2>
              <div className="issue-evidence">
                {issue.evidence.map((item) => (
                  <figure key={item.image_url}>
                    <img src={item.image_url} alt={item.observation || 'Citizen photo of the issue'} loading="lazy" />
                    <figcaption>{item.observation || 'Photo'} <span>· {formatDateTime(item.reported_at)}</span></figcaption>
                  </figure>
                ))}
              </div>
            </section>
          )}

          <section className="issue-panel">
            <h2 className="issue-subhead">Location</h2>
            <div className="issue-map">
              <MapContainer center={[issue.latitude, issue.longitude]} zoom={16} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
                <TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
                <CircleMarker center={[issue.latitude, issue.longitude]} radius={12} pathOptions={{ color: '#e47b27', fillColor: '#e47b27', fillOpacity: 0.45 }} />
              </MapContainer>
            </div>
          </section>

          <CommunityComments issueId={issue.id} onCountChange={(comments) => setIssue((current) => ({ ...current, community: { ...current.community, comments } }))} />

          <section className="issue-panel">
            <h2 className="issue-subhead">Timeline</h2>
            <ol className="issue-timeline">
              {issue.timeline.map((event, index) => (
                <li key={`${event.kind}-${event.at}-${index}`} className={`timeline-${event.kind}`}>
                  <span className="timeline-icon" aria-hidden="true">{TIMELINE_ICONS[event.kind] || '•'}</span>
                  <div>
                    <strong>{event.label}</strong>
                    {event.detail && <p>{event.detail}</p>}
                    <time dateTime={event.at}>{formatDateTime(event.at)}</time>
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <aside className="issue-side">
          <section className="signal-panel signal-official" aria-labelledby="official-heading">
            <p className="signal-kicker">🏛️ Official · NMC</p>
            <h2 id="official-heading" className="visually-hidden">Official municipal information</h2>
            <dl>
              <div><dt>Status</dt><dd><span className={statusBadgeClass(official.status)}>{official.status}</span></dd></div>
              <div><dt>Priority</dt><dd>{official.priority ? <span className={`priority-tag priority-${official.priority.toLowerCase()}`}>{official.priority}</span> : 'Not triaged'}</dd></div>
              <div><dt>Department</dt><dd>{official.department || 'Unassigned'}</dd></div>
            </dl>
            <p className="signal-note">Only authorised NMC officers can change the official status.</p>
          </section>

          <section className="signal-panel signal-community" aria-labelledby="community-heading" id="verify">
            <p className="signal-kicker">👥 Community signal</p>
            <h2 id="community-heading" className="visually-hidden">Community signal</h2>

            {issue.disputed && (
              <p className="signal-dispute">Since this was marked resolved, more citizens report it is still present. NMC officers can see this.</p>
            )}

            <div className="signal-support">
              <strong>{community.supporters}</strong>
              <span>{community.supporters === 1 ? 'citizen supports this' : 'citizens support this'}</span>
            </div>
            {canEngage && (
              <button
                type="button"
                className={`button ${viewer.supported ? 'button-secondary' : 'button-primary'} signal-button`}
                disabled={busy || (isResolved && !viewer.supported)}
                onClick={() => runAction(() => (viewer.supported ? removeSupport(issue.id) : supportIssue(issue.id)), viewer.supported ? 'Support removed.' : 'Thanks for your support.')}
              >
                ▲ {viewer.supported ? 'Supporting · remove' : 'Support this issue'}
              </button>
            )}

            <h3 className="signal-question">Is this issue still present?</h3>
            <ul className="signal-bars">
              {VERIFICATION_OPTIONS.map((option) => {
                const count = verification[option.value.toLowerCase()] || 0
                const width = totalVerifications ? Math.round((count / totalVerifications) * 100) : 0
                return (
                  <li key={option.value}>
                    <div className="signal-bar-label"><span>{option.icon} {count} {option.short}</span></div>
                    <div className="bar-track"><div className={`bar-fill signal-fill-${option.value.toLowerCase()}`} style={{ width: `${width}%` }} /></div>
                  </li>
                )
              })}
            </ul>

            {canEngage ? (
              <div className="signal-verify" role="group" aria-label="Your observation">
                {VERIFICATION_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={`civic-action ${viewer.verification === option.value ? 'is-active' : ''}`}
                    aria-pressed={viewer.verification === option.value}
                    disabled={busy}
                    onClick={() => runAction(() => verifyIssue(issue.id, option.value), 'Observation recorded. Official status is unchanged.')}
                  >
                    {option.icon} {option.label}
                  </button>
                ))}
                {viewer.verification && (
                  <button type="button" className="signal-withdraw" disabled={busy} onClick={() => runAction(() => withdrawVerification(issue.id), 'Observation withdrawn.')}>
                    Withdraw my observation
                  </button>
                )}
              </div>
            ) : (
              <p className="signal-note">Support and verification come from citizens only, so NMC staff can’t skew the signal.</p>
            )}

            {actionMessage && <p className="form-message success" role="status">{actionMessage}</p>}
            {actionError && <p className="form-message error" role="alert">{actionError}</p>}
            <p className="signal-note">Community signals are advisory. They never change the official status.</p>
          </section>
        </aside>
      </div>
    </AppShell>
  )
}
