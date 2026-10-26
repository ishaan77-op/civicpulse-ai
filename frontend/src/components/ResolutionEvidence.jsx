import ProtectedImage from './ProtectedImage.jsx'
import { formatDateTime as formatDate } from '../utils/formatDateTime.js'

// Original citizen reports (with their own photos) next to the completion
// evidence of one review. The two are always labelled and rendered
// separately so a reviewer never mistakes one for the other.
// Staff-only: it shows internal completion notes and dispositions.
export default function ResolutionEvidence({ complaints = [], checklist = [], review = null }) {
  const checklistById = new Map(checklist.map((item) => [item.complaint_id, item]))
  const titleById = new Map(complaints.map((complaint) => [complaint.id, complaint.title]))

  return (
    <div className="resolution-evidence">
      <section aria-label="Original reports">
        <h3>Original reports ({complaints.length})</h3>
        <div className="resolution-reports">
          {complaints.map((complaint) => {
            const entry = checklistById.get(complaint.id)
            return (
              <article className="resolution-report" key={complaint.id}>
                {complaint.image_url ? (
                  <figure>
                    <img src={complaint.image_url} alt={`Original report photo: ${complaint.title}`} loading="lazy" />
                    <figcaption>Original report photo</figcaption>
                  </figure>
                ) : (
                  <p className="resolution-muted">No original photo</p>
                )}
                <div>
                  <strong>{complaint.title}</strong>
                  <p className="resolution-muted">{complaint.location} &bull; {formatDate(complaint.created_at)}</p>
                  <p>{complaint.description}</p>
                  {entry?.excluded_reason && <span className="resolution-chip chip-excluded">Excluded: {entry.excluded_reason}</span>}
                  {entry?.blocked_reason && <span className="resolution-chip chip-blocked">{entry.blocked_reason}</span>}
                  {entry?.eligible && <span className="resolution-chip chip-eligible">Counted in this resolution</span>}
                </div>
              </article>
            )
          })}
        </div>
      </section>

      {review && (
        <section aria-label="Completion evidence">
          <h3>Completion evidence (submitted {formatDate(review.submitted_at)})</h3>
          <figure className="resolution-final">
            <ProtectedImage path={review.image_path} alt="Completion evidence photo" />
            <figcaption>Completion evidence photo</figcaption>
          </figure>
          <p><strong>Officer’s completion note:</strong> {review.completion_note}</p>
          {review.latitude != null && review.longitude != null && (
            <p className="resolution-muted">Evidence location: {review.latitude.toFixed(5)}, {review.longitude.toFixed(5)}</p>
          )}
          <ul className="resolution-dispositions">
            {(review.dispositions || []).map((row) => (
              <li key={row.complaint_id}>
                <strong>{titleById.get(row.complaint_id) || `Complaint #${row.complaint_id}`}</strong>
                <span className="resolution-chip">{row.disposition}</span>
                <span className="resolution-muted"> {row.note}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
