import { formatDateTime } from '../utils/formatDateTime.js'
import ProtectedImage from './ProtectedImage.jsx'

// The audit trail of a follow-up. Shows staff names only to the Chief Officer
// (the API sends actor names to them and just a role to Officers).
export default function FollowUpEvents({ events = [] }) {
  return (
    <ol className="resolution-log follow-up-events">
      {events.map((event) => (
        <li key={event.id}>
          <strong>{event.event_type.replace(/([a-z])([A-Z])/g, '$1 $2')}</strong>{' '}
          <span className="resolution-muted">
            {formatDateTime(event.created_at)} • {event.actor?.name || event.actor_role}
            {event.officer && event.officer.name !== event.actor?.name ? ` → ${event.officer.name}` : ''}
          </span>
          {event.note && <p>{event.note}</p>}
          {event.image_path && <ProtectedImage key={event.image_path} path={event.image_path} alt="Correction evidence" />}
        </li>
      ))}
    </ol>
  )
}
