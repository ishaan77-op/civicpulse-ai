import { pageInfo } from '../utils/performance.js'

// Previous/next controls for a server-paged list.
export default function Pager({ total, limit, offset, onChange, disabled }) {
  if (!total) return null
  const info = pageInfo(total, limit, offset)
  return (
    <nav className="pager" aria-label="Pagination">
      <button type="button" className="button" disabled={disabled || !info.hasPrev} onClick={() => onChange(info.prevOffset)}>← Previous</button>
      <span aria-live="polite">{info.from}–{info.to} of {info.total}</span>
      <button type="button" className="button" disabled={disabled || !info.hasNext} onClick={() => onChange(info.nextOffset)}>Next →</button>
    </nav>
  )
}
