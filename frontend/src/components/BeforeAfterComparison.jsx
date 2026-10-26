import { useCallback, useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { getResolutionEvidence } from '../services/complaintservice.js'
import { afterImageUrl, describeEvidence } from '../utils/citizenEvidence.js'
import { formatDateTime } from '../utils/formatDateTime.js'
import ImageLightbox from './ImageLightbox.jsx'

function Panel({ label, sublabel, imageUrl, alt, emptyText, onZoom }) {
  return (
    <figure className="ba-panel">
      <figcaption>
        <span className="ba-label">{label}</span> {sublabel}
      </figcaption>
      {imageUrl ? (
        <button type="button" className="ba-zoom" onClick={() => onZoom({ src: imageUrl, alt, caption: `${label} - ${sublabel}` })}
          aria-label={`View larger: ${alt}`}>
          <img src={imageUrl} alt={alt} loading="lazy" />
          <span aria-hidden="true" className="ba-zoom-hint">Tap to enlarge</span>
        </button>
      ) : (
        <p className="ba-empty">{emptyText}</p>
      )}
    </figure>
  )
}

// Citizen-facing BEFORE / AFTER view. Everything shown here comes from the
// citizen-safe endpoint; the original report photo and the approved
// completion photo are separate fields and are never swapped or merged.
export default function BeforeAfterComparison({ complaintId }) {
  const [data, setData] = useState({ status: 'loading', evidence: null, error: '' })
  const [zoomed, setZoomed] = useState(null)

  const load = useCallback(async () => {
    try {
      const { data: body } = await getResolutionEvidence(complaintId)
      setData({ status: 'ready', evidence: body.evidence, error: '' })
    } catch (err) {
      setData({ status: 'error', evidence: null, error: apiErrorMessage(err, 'We could not load the resolution progress for this complaint.') })
    }
  }, [complaintId])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const closeZoom = useCallback(() => setZoomed(null), [])

  if (data.status === 'loading') return <section className="ba-section"><p className="page-state" aria-live="polite">Loading resolution progress…</p></section>
  if (data.status === 'error') {
    return (
      <section className="ba-section">
        <p className="form-message error" role="alert">{data.error}</p>
        <button type="button" className="button" onClick={load}>Try again</button>
      </section>
    )
  }

  const { evidence } = data
  const summary = describeEvidence(evidence)
  if (!summary) return null // e.g. this report was not part of a resolution

  const approved = evidence.state === 'approved'
  const afterUrl = afterImageUrl(evidence)

  return (
    <section className="ba-section" aria-labelledby="ba-heading">
      <h2 id="ba-heading">Before &amp; after</h2>
      <div className={`resolution-banner banner-${summary.tone === 'none' ? 'stale' : summary.tone}`} role="status">
        <strong>{summary.title}</strong>
        <p>{summary.message}</p>
        {evidence.issue_status && <p className="resolution-muted">Current issue status: {evidence.issue_status}</p>}
      </div>

      <div className="ba-grid">
        <Panel
          label="BEFORE" sublabel="Original report"
          imageUrl={evidence.before?.image_url} alt="Original report photo"
          emptyText="No photo was attached to the original report."
          onZoom={setZoomed}
        />
        <Panel
          label="AFTER" sublabel={approved ? 'Completed work' : 'Awaiting approved completion'}
          imageUrl={afterUrl} alt="Completed work photo"
          emptyText={approved ? 'The completion photo is currently unavailable.' : 'No approved completion photo yet.'}
          onZoom={setZoomed}
        />
      </div>

      <dl className="ba-dates">
        {evidence.before?.reported_at && <><dt>Reported</dt><dd>{formatDateTime(evidence.before.reported_at)}</dd></>}
        {evidence.work_submitted_at && <><dt>Work submitted</dt><dd>{formatDateTime(evidence.work_submitted_at)}</dd></>}
        {evidence.returned_at && <><dt>Returned for correction</dt><dd>{formatDateTime(evidence.returned_at)}</dd></>}
        {evidence.approved_at && <><dt>Approved</dt><dd>{formatDateTime(evidence.approved_at)}</dd></>}
      </dl>

      {approved && evidence.after?.report && (
        <div className="ba-report">
          <h3>Completion report</h3>
          <p>{evidence.after.report}</p>
        </div>
      )}

      {zoomed && <ImageLightbox src={zoomed.src} alt={zoomed.alt} caption={zoomed.caption} onClose={closeZoom} />}
    </section>
  )
}
