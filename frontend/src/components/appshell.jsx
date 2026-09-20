import { useContext, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { AuthContext } from '../context/authcontextvalue.jsx'
import { homeRouteForRole } from '../utils/roleHome.js'
import NotificationBanner from './NotificationBanner.jsx'
import Brand from './brand.jsx'

// Role-aware navigation - an Officer/Admin must never see citizen-only
// actions like "Report an issue" or "My complaints" in their own nav.
function linksForRole(role) {
  if (role === 'Officer') {
    return [
      { to: '/officer', label: 'Officer Hub' },
    ]
  }

  if (role === 'Admin') {
    return [
      { to: '/admin', label: 'Admin Intelligence' },
      { to: '/officer', label: 'Officer Hub' },
    ]
  }

  return [
    { to: '/dashboard', label: 'Dashboard' },
    { to: '/report', label: 'Report an issue' },
    { to: '/complaints', label: 'My complaints' },
  ]
}

export default function AppShell({ title, eyebrow, children }) {
  const { user, logout } = useContext(AuthContext)
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const signOut = () => { logout(); navigate('/', { replace: true }) }

  const links = [...linksForRole(user?.role), { to: '/profile', label: 'Profile' }]

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="container app-nav">
          <Brand to={homeRouteForRole(user?.role)} />
          <button className="menu-toggle app-menu-toggle" type="button" aria-label="Toggle app navigation" aria-expanded={open} onClick={() => setOpen(!open)}>
            <span /><span /><span />
          </button>
          <div className={`app-links ${open ? 'is-open' : ''}`}>
            {links.map((link) => (
              <NavLink key={link.to} to={link.to} onClick={() => setOpen(false)}>
                {link.label}
              </NavLink>
            ))}
            <button type="button" onClick={signOut}>Log out</button>
          </div>
        </div>
      </header>
      <main className="app-main">
        <div className="container">
          <p className="section-label">{eyebrow}</p>
          <div className="app-page-heading">
            <div>
              <h1>{title}</h1>
              {user && <p>Welcome back, {user.name} ({user.role || 'Citizen'}).</p>}
            </div>
          </div>
          {user?.role === 'Citizen' && <NotificationBanner />}
          {children}
        </div>
      </main>
    </div>
  )
}
