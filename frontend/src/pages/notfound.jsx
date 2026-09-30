import { Link } from 'react-router-dom'
import Navbar from '../components/navbar.jsx'
import Footer from '../components/footer.jsx'

export default function NotFound() {
  return (
    <>
      <Navbar />
      <main className="public-page">
        <section className="page-hero notfound-hero">
          <div className="container">
            <p className="eyebrow"><span className="eyebrow-dot" />404 &bull; Page Not Found</p>
            <h1>This page doesn't <span>exist.</span></h1>
            <p>The link you followed may be broken or the page may have been moved.</p>
            <div style={{ marginTop: '28px', display: 'flex', gap: '16px', justifyContent: 'center' }}>
              <Link className="button button-primary" to="/">Return Home <span aria-hidden="true">→</span></Link>
              <Link className="button button-secondary" to="/dashboard">Go to Dashboard <span aria-hidden="true">→</span></Link>
            </div>
          </div>
        </section>
      </main>
      <Footer />
    </>
  )
}
