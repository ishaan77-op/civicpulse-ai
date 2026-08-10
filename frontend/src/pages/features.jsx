import { Link } from 'react-router-dom'
import Navbar from '../components/navbar.jsx'
import Footer from '../components/footer.jsx'

const features = [
  { icon: '✦', title: 'AI Complaint Classification', summary: 'Make every report easier to understand from the start.', text: 'CivicPulse AI helps identify the type of issue being reported and surfaces the context needed to prioritize it. This creates a more consistent path from a citizen’s observation to meaningful civic action.' },
  { icon: '◷', title: 'Real-Time Tracking', summary: 'Keep progress visible, not buried in a process.', text: 'Citizens can stay informed from the moment an issue is submitted through each update toward resolution. Clear status information makes the experience more transparent for everyone involved.' },
  { icon: '↗', title: 'Smart Department Routing', summary: 'Connect issues with the teams equipped to act.', text: 'By organizing complaints with clearer context, CivicPulse supports routing them to the appropriate authority. The result is a more direct handoff and less uncertainty about where a report belongs.' },
  { icon: '⌁', title: 'Civic Analytics', summary: 'Turn recurring signals into clearer insight.', text: 'Complaint data can reveal the themes that matter across a community. CivicPulse brings those signals into focus so civic teams can better understand needs and respond with intention.' },
]

export default function Features() {
  return <><Navbar /><main className="public-page"><section className="page-hero"><div className="hero-glow hero-glow-left" /><div className="hero-glow hero-glow-right" /><div className="container"><p className="eyebrow"><span className="eyebrow-dot" />Built for clearer civic action</p><h1>Tools that help every civic issue <span>move forward.</span></h1><p>Thoughtful technology for reporting, understanding, and following the issues that shape everyday life in a community.</p></div></section><section className="page-section"><div className="container detail-grid">{features.map((feature, index) => <article className="detail-card" key={feature.title}><span className="feature-icon" aria-hidden="true">{feature.icon}</span><span className="detail-count">0{index + 1}</span><h2>{feature.title}</h2><h3>{feature.summary}</h3><p>{feature.text}</p></article>)}</div></section><section className="page-cta"><div className="container"><div><p className="section-label">A connected civic experience</p><h2>See what a clearer path forward can look like.</h2></div><Link className="button button-primary" to="/login">Report an Issue <span aria-hidden="true">→</span></Link></div></section></main><Footer /></>
}
