import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="container footer-content">
        <div className="footer-brand">
          <Link className="brand" to="/" aria-label="CivicPulse AI home"><span className="brand-mark" aria-hidden="true"><span /></span><span>CivicPulse <em>AI</em></span></Link>
          <p>Making civic engagement clearer, faster, and more connected.</p>
        </div>
        <div className="footer-links" aria-label="Footer navigation">
          <Link to="/features">Features</Link><Link to="/how-it-works">How it works</Link><Link to="/about">About</Link>
          <Link to="/login">Sign In</Link><Link to="/register">Register</Link>
        </div>
      </div>
      <div className="container footer-bottom"><span>© 2026 CivicPulse AI</span><span>Built for more responsive cities.</span></div>
    </footer>
  )
}
