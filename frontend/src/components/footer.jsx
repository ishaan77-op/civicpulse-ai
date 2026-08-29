import { Link } from 'react-router-dom'
import Brand from './brand.jsx'

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="container footer-content">
        <div className="footer-brand">
          <Brand />
          <p>Smart Nashik. Better Tomorrow.</p>
        </div>
        <div className="footer-links" aria-label="Footer navigation">
          <Link to="/features">Features</Link><Link to="/how-it-works">How it works</Link><Link to="/about">About</Link>
          <Link to="/login">Sign In</Link><Link to="/register">Register</Link>
        </div>
      </div>
      <div className="container footer-bottom"><span>© 2026 NMC-SmartFix</span><span>AI-powered civic complaint &amp; resolution platform.</span></div>
    </footer>
  )
}
