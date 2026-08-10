import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import AppShell from '../components/appshell.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getComplaint, updateComplaint } from '../services/complaintservice.js'

const categories = ['Roads', 'Street lighting', 'Sanitation', 'Water', 'Public safety', 'Other']

export default function ComplaintDetails() {
  const { id } = useParams()
  const [complaint, setComplaint] = useState(null)
  const [form, setForm] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => { let active = true; getComplaint(id).then(({ data }) => { const record = data.complaint || data; if (active) { setComplaint(record); setForm({ title: record.title || '', description: record.description || '', category: record.category || '', location: record.location || '' }) } }).catch((requestError) => { if (active) setError(apiErrorMessage(requestError, 'We could not load this complaint.')) }).finally(() => { if (active) setLoading(false) }); return () => { active = false } }, [id])
  const submit = async (event) => { event.preventDefault(); setError(''); setSuccess(''); setSaving(true); try { const { data } = await updateComplaint(id, form); const updated = data.complaint || data; setComplaint(updated); setForm({ title: updated.title || form.title, description: updated.description || form.description, category: updated.category || form.category, location: updated.location || form.location }); setSuccess('Your complaint has been updated.') } catch (requestError) { setError(apiErrorMessage(requestError, 'We could not save those changes.')) } finally { setSaving(false) } }
  return <AppShell eyebrow="Complaint details" title={complaint?.title || 'Complaint'}>{loading ? <p className="page-state" aria-live="polite">Loading complaint details…</p> : error ? <><p className="form-message error" role="alert">{error}</p><Link className="preview-link" to="/complaints">Back to my complaints</Link></> : <section className="detail-layout"><div className="detail-summary"><Link className="preview-link" to="/complaints">← Back to my complaints</Link><span className={`status status-${String(complaint.status || 'Pending').toLowerCase().replaceAll(' ', '-')}`}>{complaint.status || 'Pending'}</span><h2>Keep report details current.</h2><p>Update the information below if it helps make the issue clearer for the team responsible for resolving it.</p></div><form className="app-form" onSubmit={submit}><label>Issue title<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required /></label><label>Category<select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} required><option value="">Choose a category</option>{categories.map((category) => <option key={category}>{category}</option>)}</select></label><label>Location<input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} required /></label><label>Description<textarea rows="6" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} required /></label>{error && <p className="form-message error" role="alert">{error}</p>}{success && <p className="form-message success" role="status">{success}</p>}<button className="button button-primary" disabled={saving}>{saving ? 'Saving…' : 'Save changes'} <span aria-hidden="true">→</span></button></form></section>}</AppShell>
}
