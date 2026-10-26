import { Link } from 'react-router-dom'
import Navbar from '../components/navbar.jsx'
import Footer from '../components/footer.jsx'

const steps = [
  ['01', 'Report', 'Start with what you see.', 'A citizen submits a civic issue with the details that matter. Providing a clear description creates a useful starting point for everyone who will need to understand the concern.'],
  ['02', 'AI Analysis', 'Bring clarity to the issue.', 'CivicPulse understands the complaint and identifies its category. This helps organize the report around its civic context and makes the next step easier to determine.'],
  ['03', 'Authority Assignment', 'Connect it to the right place.', 'The issue is routed to the department best placed to act. A more focused handoff helps responsible teams quickly see the context behind a complaint.'],
  ['04', 'Resolution', 'Keep progress in view.', 'Citizens can follow progress through to a clear outcome. Transparent updates make it easier to understand what has happened and what comes next.'],
]

export default function HowItWorks() {
  return <><Navbar /><main className="public-page"><section className="page-hero page-hero-works"><div className="container"><p className="eyebrow"><span className="eyebrow-dot" />Simple by design</p><h1>From one observation to <span>shared progress.</span></h1><p>CivicPulse brings citizens and civic authorities into one clearer workflow, with meaningful context at each step.</p></div></section><section className="page-section workflow-section"><div className="container workflow-list">{steps.map(([number, title, tagline, text]) => <article className="workflow-card" key={number}><div className="workflow-marker"><span>{number}</span><i /></div><div><p className="section-label">{tagline}</p><h2>{title}</h2><p>{text}</p></div></article>)}</div></section><section className="page-cta"><div className="container"><div><p className="section-label">Ready when you are</p><h2>Help make local concerns easier to act on.</h2></div><Link className="button button-primary" to="/login">Start Reporting <span aria-hidden="true">→</span></Link></div></section></main><Footer /></>
}
