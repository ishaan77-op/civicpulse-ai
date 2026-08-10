import { useEffect, useState } from 'react'
import AppShell from '../components/appshell.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getProfile } from '../services/authservice.js'

export default function Profile() {
  const [profile, setProfile] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => { let active = true; getProfile().then(({ data }) => { if (active) setProfile(data.user || data) }).catch((requestError) => { if (active) setError(apiErrorMessage(requestError, 'We could not load your profile.')) }); return () => { active = false } }, [])
  return <AppShell eyebrow="Your account" title="Profile">{error ? <p className="form-message error" role="alert">{error}</p> : !profile ? <p className="page-state" aria-live="polite">Loading your profile…</p> : <section className="profile-card"><div className="profile-avatar" aria-hidden="true">{profile.name?.charAt(0)?.toUpperCase() || 'C'}</div><div><p className="section-label">CivicPulse member</p><h2>{profile.name}</h2><dl><div><dt>Email</dt><dd>{profile.email}</dd></div><div><dt>Role</dt><dd>{profile.role || 'Citizen'}</dd></div></dl></div></section>}</AppShell>
}
