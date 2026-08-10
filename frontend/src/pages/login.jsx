import { useContext, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { AuthContext } from '../context/authcontextvalue.jsx'
import { apiErrorMessage } from '../services/api.js'

export default function Login() {
  const { login, isAuthenticated } = useContext(AuthContext)
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  if (isAuthenticated) return <Navigate to="/dashboard" replace />
  const submit = async (event) => { event.preventDefault(); setError(''); setSubmitting(true); try { await login(form); navigate(location.state?.from?.pathname || '/dashboard', { replace: true }) } catch (requestError) { setError(apiErrorMessage(requestError, 'Unable to sign in with those details.')) } finally { setSubmitting(false) } }
  return <main className="auth-page"><Link className="brand auth-brand" to="/"><span className="brand-mark" aria-hidden="true"><span /></span><span>CivicPulse <em>AI</em></span></Link><section className="auth-card"><p className="section-label">Welcome back</p><h1>Sign in to CivicPulse</h1><p className="auth-intro">Continue following and reporting the civic issues that matter to your community.</p><form onSubmit={submit}><label>Email<input type="email" autoComplete="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label><label>Password<input type="password" autoComplete="current-password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required /></label>{error && <p className="form-message error" role="alert">{error}</p>}<button className="button button-primary" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign In'} <span aria-hidden="true">→</span></button></form><p className="auth-switch">New to CivicPulse? <Link to="/register">Create an account</Link></p></section></main>
}
