import { useContext, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { AuthContext } from '../context/authcontextvalue.jsx'
import { apiErrorMessage } from '../services/api.js'
import { homeRouteForRole } from '../utils/roleHome.js'
import Brand from '../components/brand.jsx'

export default function Login() {
  const { login, isAuthenticated, user } = useContext(AuthContext)
  const [form, setForm] = useState({ email: '', password: '' })
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  if (isAuthenticated) return <Navigate to={homeRouteForRole(user?.role)} replace />
  const submit = async (event) => { event.preventDefault(); setError(''); setSubmitting(true); try { const loggedInUser = await login(form); navigate(location.state?.from?.pathname || homeRouteForRole(loggedInUser?.role), { replace: true }) } catch (requestError) { setError(apiErrorMessage(requestError, 'Unable to sign in with those details.')) } finally { setSubmitting(false) } }
  return <main className="auth-page"><Brand className="auth-brand" /><section className="auth-card glass-card"><p className="section-label">NMC-SmartFix access</p><h1>Sign in to SmartFix</h1><p className="auth-intro">Report and track the civic issues that matter to Nashik.</p><form onSubmit={submit}><label>Email<input type="email" autoComplete="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label><label>Password<span style={{ position: 'relative', display: 'block' }}><input type={showPassword ? 'text' : 'password'} autoComplete="current-password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required style={{ width: '100%', paddingRight: '56px', boxSizing: 'border-box' }} /><button type="button" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? 'Hide password' : 'Show password'} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'none', cursor: 'pointer', fontSize: '13px', color: '#555' }}>{showPassword ? 'Hide' : 'Show'}</button></span></label>{error && <p className="form-message error" role="alert">{error}</p>}<button className="button button-primary" disabled={submitting}>{submitting ? 'Signing in…' : 'Sign In'} <span aria-hidden="true">→</span></button></form><p className="auth-switch">New to SmartFix? <Link to="/register">Create an account</Link></p></section></main>
}
