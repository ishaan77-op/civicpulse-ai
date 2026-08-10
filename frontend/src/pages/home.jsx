import { Link } from 'react-router-dom'
import Navbar from '../components/navbar.jsx'
import Footer from '../components/footer.jsx'

export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <section className="hero-section">
          <div className="hero-glow hero-glow-left" /><div className="hero-glow hero-glow-right" />
          <div className="container hero">
            <div className="eyebrow"><span className="eyebrow-dot" />AI-powered civic intelligence</div>
            <h1>Your city.<br /><span>Your voice.</span> Your impact.</h1>
            <p className="hero-copy">Report civic issues, track their progress, and stay connected to the authorities working to resolve them.</p>
            <div className="hero-actions">
              <Link className="button button-primary" to="/login">Report an Issue <span aria-hidden="true">→</span></Link>
              <Link className="button button-secondary" to="/features">Explore CivicPulse <span aria-hidden="true">→</span></Link>
            </div>
            <p className="hero-note"><span className="check" aria-hidden="true">✓</span> Clear updates at every step <span className="dot-separator">•</span> Built for communities</p>
            <div className="hero-orbit" aria-hidden="true">
              <div className="orbit-ring orbit-ring-one" /><div className="orbit-ring orbit-ring-two" />
              <div className="orbit-core"><span className="core-pulse" /><span className="core-building">⌂</span></div>
              <div className="float-card float-card-one"><span className="card-icon card-icon-blue">↗</span><div><small>COMPLAINT RECEIVED</small><strong>Pothole reported</strong><span>AI classified · Roads</span></div><i className="status-dot" /></div>
              <div className="float-card float-card-two"><span className="card-icon card-icon-violet">✓</span><div><small>STATUS UPDATED</small><strong>Street light repair</strong><span>Assigned to department</span></div></div>
              <div className="float-card float-card-three"><span className="card-icon card-icon-sky">✦</span><div><small>AI INSIGHT</small><strong>Complaint category detected</strong></div></div>
            </div>
          </div>
        </section>

        <section id="about" className="section about-section"><div className="container about-content"><div><div className="section-label">About CivicPulse AI</div><h2>Technology that helps communities <span>be heard.</span></h2></div><div><p>CivicPulse AI bridges the gap between citizens and civic authorities through intelligent complaint management, transparent tracking, and data-driven insights. It is a simpler way to turn everyday observations into meaningful local action.</p><Link className="preview-link" to="/about">Discover our purpose <span aria-hidden="true">→</span></Link></div></div></section>

        <section className="final-cta"><div className="cta-orbit cta-orbit-one" /><div className="cta-orbit cta-orbit-two" /><div className="container"><div className="section-label cta-label">Shape a more responsive city</div><h2>Your city. Your voice.<br /><span>Your impact.</span></h2><p>Bring your civic concerns into view and help move your community forward.</p><Link className="button button-white" to="/login">Start Reporting <span aria-hidden="true">→</span></Link></div></section>
      </main>
      <Footer />
    </>
  )
}
