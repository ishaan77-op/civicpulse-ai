import { useContext, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AuthContext } from '../context/authcontextvalue.jsx'
import { apiErrorMessage } from '../services/api.js'

export default function Register() {
  const { register, isAuthenticated } = useContext(AuthContext)
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()
  if (isAuthenticated) return <Navigate to="/dashboard" replace />
  const submit = async (event) => { event.preventDefault(); setError(''); setNotice(''); setSubmitting(true); try { const data = await register(form); if (data.token && data.user) navigate('/dashboard', { replace: true }); else setNotice(data.message || 'Account created. You can now sign in.') } catch (requestError) { setError(apiErrorMessage(requestError, 'Unable to create your account.')) } finally { setSubmitting(false) } }
  return <main className="auth-page"><Link className="brand auth-brand" to="/"><span className="brand-mark" aria-hidden="true"><span /></span><span>CivicPulse <em>AI</em></span></Link><section className="auth-card"><p className="section-label">Get started</p><h1>Join CivicPulse</h1><p className="auth-intro">Create an account to report local concerns and follow their progress.</p><form onSubmit={submit}><label>Full name<input type="text" autoComplete="name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></label><label>Email<input type="email" autoComplete="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label><label>Password<input type="password" autoComplete="new-password" minLength="6" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required /></label>{error && <p className="form-message error" role="alert">{error}</p>}{notice && <p className="form-message success" role="status">{notice}</p>}<button className="button button-primary" disabled={submitting}>{submitting ? 'Creating account…' : 'Create Account'} <span aria-hidden="true">→</span></button></form><p className="auth-switch">Already have an account? <Link to="/login">Sign in</Link></p></section></main>
}
