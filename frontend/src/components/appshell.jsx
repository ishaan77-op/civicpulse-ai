import { useContext, useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { AuthContext } from '../context/authcontextvalue.jsx'

const links = [{ to: '/dashboard', label: 'Dashboard' }, { to: '/report', label: 'Report an issue' }, { to: '/complaints', label: 'My complaints' }, { to: '/profile', label: 'Profile' }]

export default function AppShell({ title, eyebrow, children }) {
  const { user, logout } = useContext(AuthContext)
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const signOut = () => { logout(); navigate('/', { replace: true }) }
  return <div className="app-shell"><header className="app-header"><div className="container app-nav"><Link className="brand" to="/dashboard"><span className="brand-mark" aria-hidden="true"><span /></span><span>CivicPulse <em>AI</em></span></Link><button className="menu-toggle app-menu-toggle" type="button" aria-label="Toggle app navigation" aria-expanded={open} onClick={() => setOpen(!open)}><span /><span /><span /></button><div className={`app-links ${open ? 'is-open' : ''}`}>{links.map((link) => <NavLink key={link.to} to={link.to} onClick={() => setOpen(false)}>{link.label}</NavLink>)}<button type="button" onClick={signOut}>Log out</button></div></div></header><main className="app-main"><div className="container"><p className="section-label">{eyebrow}</p><div className="app-page-heading"><div><h1>{title}</h1>{user && <p>Welcome back, {user.name}.</p>}</div></div>{children}</div></main></div>
}
