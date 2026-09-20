import { Link } from 'react-router-dom'
import Navbar from '../components/navbar.jsx'
import Footer from '../components/footer.jsx'

export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <section className="hero-section">
          <div className="container hero">
            <div className="eyebrow"><span className="eyebrow-dot" />Nashik Municipal Corporation</div>
            <h1>Smart Nashik.<br /><span>Better</span> tomorrow.</h1>
            <p className="hero-copy">NMC-SmartFix turns civic complaints into clear, trackable action with AI-powered routing for every neighbourhood.</p>
            <div className="hero-actions">
              <Link className="button button-primary" to="/login">Report an Issue <span aria-hidden="true">→</span></Link>
              <Link className="button button-secondary" to="/features">How SmartFix works <span aria-hidden="true">→</span></Link>
            </div>
            <p className="hero-note"><span className="check" aria-hidden="true">✓</span> Clear updates at every step <span className="dot-separator">•</span> Built for communities</p>
            <div className="hero-orbit" aria-hidden="true">
              <div className="orbit-ring orbit-ring-one" /><div className="orbit-ring orbit-ring-two" />
              <div className="orbit-core"><span className="core-pulse" /><span className="core-building">⌂</span></div>
              <div className="float-card float-card-one"><span className="card-icon card-icon-blue">↗</span><div><small>COMPLAINT RECEIVED</small><strong>Large pothole</strong><span>AI routed · Public Works</span></div><i className="status-dot" /></div>
              <div className="float-card float-card-two"><span className="card-icon card-icon-violet">✓</span><div><small>STATUS UPDATED</small><strong>Street light repair</strong><span>Marked resolved</span></div></div>
              <div className="float-card float-card-three"><span className="card-icon card-icon-sky">✦</span><div><small>AI INSIGHT</small><strong>Priority: High</strong></div></div>
            </div>
          </div>
        </section>

        <section id="about" className="section about-section"><div className="container about-content"><div><div className="section-label">About NMC-SmartFix</div><h2>One city, one clear path to <span>resolution.</span></h2></div><div><p>NMC-SmartFix helps Nashik residents report issues, see progress, and connect concerns to the teams able to act. It brings transparent civic service into one simple experience.</p><Link className="preview-link" to="/about">Discover our purpose <span aria-hidden="true">→</span></Link></div></div></section>

        <section className="final-cta"><div className="cta-orbit cta-orbit-one" /><div className="cta-orbit cta-orbit-two" /><div className="container"><div className="section-label cta-label">Shape a more responsive city</div><h2>Your city. Your voice.<br /><span>Your impact.</span></h2><p>Bring your civic concerns into view and help move your community forward.</p><Link className="button button-white" to="/login">Start Reporting <span aria-hidden="true">→</span></Link></div></section>
      </main>
      <Footer />
    </>
  )
}
