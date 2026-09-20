import { useContext, useState } from 'react'
import { Link } from 'react-router-dom'
import { AuthContext } from '../context/authcontextvalue.jsx'
import Brand from './brand.jsx'

const navigation = [
  { label: 'Home', to: '/' },
  { label: 'Features', to: '/features' },
  { label: 'How It Works', to: '/how-it-works' },
  { label: 'About', to: '/about' },
]

export default function Navbar() {
  const { user, isAuthenticated } = useContext(AuthContext) || {}
  const [isOpen, setIsOpen] = useState(false)
  const closeMenu = () => setIsOpen(false)

  return (
    <header className="site-header">
      <nav className="navbar container" aria-label="Main navigation">
        <Brand />
        <button className="menu-toggle" type="button" aria-label="Toggle navigation menu" aria-expanded={isOpen} aria-controls="primary-navigation" onClick={() => setIsOpen(!isOpen)}>
          <span /><span /><span />
        </button>
        <div id="primary-navigation" className={`nav-panel ${isOpen ? 'is-open' : ''}`}>
          <div className="nav-links">
            {navigation.map((item) => <Link key={item.label} to={item.to} onClick={closeMenu}>{item.label}</Link>)}
          </div>
          <div className="nav-actions">
            {isAuthenticated ? (
              <>
                <Link className="button button-small button-primary" to="/dashboard" onClick={closeMenu}>
                  Dashboard ({user?.name || 'Account'}) <span aria-hidden="true">→</span>
                </Link>
                {(user?.role === 'Officer' || user?.role === 'Admin') && (
                  <Link className="text-link" to="/officer" onClick={closeMenu}>Officer</Link>
                )}
                {user?.role === 'Admin' && (
                  <Link className="text-link" to="/admin" onClick={closeMenu}>Admin</Link>
                )}
              </>
            ) : (
              <>
                <Link className="text-link" to="/login" onClick={closeMenu}>Sign In</Link>
                <Link className="button button-small button-primary" to="/register" onClick={closeMenu}>Register <span aria-hidden="true">→</span></Link>
              </>
            )}
          </div>
        </div>
      </nav>
    </header>
  )
}
