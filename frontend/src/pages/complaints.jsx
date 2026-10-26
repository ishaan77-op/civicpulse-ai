import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../components/appshell.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getComplaints } from '../services/complaintservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'

const statusClass = (complaint) => complaint.rejection ? 'status status-rejected' : `status status-${String(complaint.status || 'Pending').toLowerCase().replaceAll(' ', '-')}`
const statusLabel = (complaint) => complaint.rejection ? 'Rejected — Out of Scope' : (complaint.status || 'Pending')

export default function Complaints() {
  const [complaints, setComplaints] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  useEffect(() => { let active = true; getComplaints().then(({ data }) => { if (active) setComplaints(Array.isArray(data) ? data : data.complaints || []) }).catch((requestError) => { if (active) setError(apiErrorMessage(requestError, 'We could not load your complaints.')) }).finally(() => { if (active) setLoading(false) }); return () => { active = false } }, [])
  return <AppShell eyebrow="Your reports" title="My complaints"><section className="complaints-header"><p>Review your submitted issues and open a report to see or update its details.</p><Link className="button button-primary" to="/report">Report an Issue <span aria-hidden="true">→</span></Link></section>{loading ? <p className="page-state" aria-live="polite">Loading your complaints…</p> : error ? <p className="form-message error" role="alert">{error}</p> : complaints.length === 0 ? <section className="empty-state"><span className="dashboard-icon">◷</span><h2>No reports yet</h2><p>When you report a civic issue, it will appear here so you can follow its progress.</p><Link className="button button-primary" to="/report">Report an Issue <span aria-hidden="true">→</span></Link></section> : <section className="complaint-list">{complaints.map((complaint) => <Link className="complaint-card" to={`/complaints/${complaint.id}`} key={complaint.id}><div><span className="complaint-category">{complaint.category || 'Uncategorized'}</span><h2>{complaint.title}</h2><p>{complaint.location || 'Location not provided'} <span>•</span> {formatDateTime(complaint.created_at || complaint.createdAt)}</p></div><div className="complaint-meta"><span className={statusClass(complaint)}>{statusLabel(complaint)}</span><b aria-hidden="true">→</b></div></Link>)}</section>}</AppShell>
}
