import { useContext, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { AuthContext } from '../context/authcontextvalue.jsx'
import { apiErrorMessage } from '../services/api.js'
import { homeRouteForRole } from '../utils/roleHome.js'
import Brand from '../components/brand.jsx'

export default function Register() {
  const { register, isAuthenticated, user } = useContext(AuthContext)
  const [form, setForm] = useState({ name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const navigate = useNavigate()
  if (isAuthenticated) return <Navigate to={homeRouteForRole(user?.role)} replace />
  const submit = async (event) => { event.preventDefault(); setError(''); setNotice(''); setSubmitting(true); try { const data = await register(form); if (data.token && data.user) navigate(homeRouteForRole(data.user.role), { replace: true }); else setNotice(data.message || 'Account created. You can now sign in.') } catch (requestError) { setError(apiErrorMessage(requestError, 'Unable to create your account.')) } finally { setSubmitting(false) } }
  return <main className="auth-page"><Brand className="auth-brand" /><section className="auth-card glass-card"><p className="section-label">Nashik civic services</p><h1>Join SmartFix</h1><p className="auth-intro">Create an account to report local concerns and follow their resolution.</p><form onSubmit={submit}><label>Full name<input type="text" autoComplete="name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required /></label><label>Email<input type="email" autoComplete="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} required /></label><label>Password<span style={{ position: 'relative', display: 'block' }}><input type={showPassword ? 'text' : 'password'} autoComplete="new-password" minLength="6" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} required style={{ width: '100%', paddingRight: '56px', boxSizing: 'border-box' }} /><button type="button" onClick={() => setShowPassword((current) => !current)} aria-label={showPassword ? 'Hide password' : 'Show password'} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'none', cursor: 'pointer', fontSize: '13px', color: '#555' }}>{showPassword ? 'Hide' : 'Show'}</button></span></label>{error && <p className="form-message error" role="alert">{error}</p>}{notice && <p className="form-message success" role="status">{notice}</p>}<button className="button button-primary" disabled={submitting}>{submitting ? 'Creating account…' : 'Create Account'} <span aria-hidden="true">→</span></button></form><p className="auth-switch">Already have an account? <Link to="/login">Sign in</Link></p></section></main>
}
