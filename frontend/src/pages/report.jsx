import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/appshell.jsx'
import { apiErrorMessage } from '../services/api.js'
import { createComplaint } from '../services/complaintservice.js'

const categories = ['Roads', 'Street lighting', 'Sanitation', 'Water', 'Public safety', 'Other']

export default function Report() {
  const [form, setForm] = useState({ title: '', description: '', category: '', location: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()
  const submit = async (event) => { event.preventDefault(); setError(''); setSubmitting(true); try { await createComplaint(form); navigate('/complaints', { replace: true }) } catch (requestError) { setError(apiErrorMessage(requestError, 'We could not submit this report.')) } finally { setSubmitting(false) } }
  return <AppShell eyebrow="New report" title="Report a civic issue"><section className="form-layout"><div><h2>Share what you have noticed.</h2><p>Clear details help the appropriate civic team understand the issue and what needs attention.</p></div><form className="app-form" onSubmit={submit}><label>Issue title<input value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required /></label><label>Category<select value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} required><option value="">Choose a category</option>{categories.map((category) => <option key={category}>{category}</option>)}</select></label><label>Location<input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} required /></label><label>Description<textarea rows="6" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} required /></label>{error && <p className="form-message error" role="alert">{error}</p>}<button className="button button-primary" disabled={submitting}>{submitting ? 'Submitting…' : 'Submit report'} <span aria-hidden="true">→</span></button></form></section></AppShell>
}
