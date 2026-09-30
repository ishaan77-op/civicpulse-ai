import { useCallback, useContext, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import AppShell from '../components/appshell.jsx'
import CommunityIssueCard from '../components/CommunityIssueCard.jsx'
import { AuthContext } from '../context/authcontextvalue.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getCommunityFeed } from '../services/communityservice.js'
import { CATEGORIES } from '../utils/community.js'

const FEEDS = [
  { value: 'recent', label: 'Recent', hint: 'Newest reports and latest official updates first.' },
  { value: 'trending', label: 'Trending', hint: 'Open issues with the most new reports, support, verifications and comments this week.' },
  { value: 'nearby', label: 'Nearby', hint: 'Issues within 3 km of your current location.' },
  { value: 'priority', label: 'High Priority', hint: 'Issues triaged as High or Critical priority.' },
]

const PER_PAGE = 10

export default function Community() {
  const { user } = useContext(AuthContext)
  const canEngage = user?.role === 'Citizen'
  const [sort, setSort] = useState('recent')
  const [category, setCategory] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [search, setSearch] = useState('')
  const [coords, setCoords] = useState(null)
  const [locationError, setLocationError] = useState('')
  const [issues, setIssues] = useState([])
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')

  // Debounce the search box so typing doesn't fire a request per key.
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(searchInput.trim()), 350)
    return () => window.clearTimeout(timer)
  }, [searchInput])

  const fetchPage = useCallback(async (pageToLoad) => {
    if (sort === 'nearby' && !coords) return
    const params = { sort, page: pageToLoad, per_page: PER_PAGE }
    if (category) params.category = category
    if (search) params.q = search
    if (sort === 'nearby') { params.lat = coords.lat; params.lng = coords.lng }

    try {
      if (pageToLoad === 1) setLoading(true)
      else setLoadingMore(true)
      setError('')
      const { data } = await getCommunityFeed(params)
      setIssues((current) => (pageToLoad === 1 ? data.issues : [...current, ...data.issues]))
      setHasMore(data.has_more)
      setTotal(data.total)
      setPage(pageToLoad)
    } catch (err) {
      setError(apiErrorMessage(err, 'We could not load the community feed.'))
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }, [sort, category, search, coords])

  useEffect(() => {
    const timer = window.setTimeout(() => fetchPage(1), 0)
    return () => window.clearTimeout(timer)
  }, [fetchPage])

  const chooseFeed = (value) => {
    setSort(value)
    if (value !== 'nearby' || coords) return
    setLocationError('')
    if (!navigator.geolocation) {
      setLocationError('Your browser does not support location access.')
      setLoading(false)
      return
    }
    setLoading(true)
    navigator.geolocation.getCurrentPosition(
      (position) => setCoords({ lat: position.coords.latitude, lng: position.coords.longitude }),
      () => {
        setLocationError('Allow location access to see issues near you. Your location is only used for this search and is never stored.')
        setLoading(false)
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
    )
  }

  const replaceIssue = (updated) => setIssues((current) => current.map((item) => (item.id === updated.id ? updated : item)))
  const activeFeed = FEEDS.find((feed) => feed.value === sort)

  return (
    <AppShell eyebrow="Community" title="Nashik civic community">
      <section className="community-intro">
        <p>
          See what fellow citizens are reporting, support the issues that matter to you, and confirm what you see on the ground.
          Everyone appears anonymously. <strong>Official status is always set by NMC</strong>; community signals help officers prioritise.
        </p>
        {canEngage && <Link className="button button-primary button-small" to="/report">Report an issue <span aria-hidden="true">→</span></Link>}
      </section>

      <section className="community-toolbar">
        <div className="search-box">
          <input
            type="search"
            placeholder="🔎 Search civic issues by area, type or description…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            aria-label="Search civic issues"
          />
        </div>
        <div className="filter-group">
          <select value={category} onChange={(e) => setCategory(e.target.value)} aria-label="Filter by category">
            <option value="">All categories</option>
            {CATEGORIES.map((cat) => <option key={cat} value={cat}>{cat}</option>)}
          </select>
        </div>
      </section>

      <div className="community-tabs" role="tablist" aria-label="Feed">
        {FEEDS.map((feed) => (
          <button
            key={feed.value}
            type="button"
            role="tab"
            aria-selected={sort === feed.value}
            className={`community-tab ${sort === feed.value ? 'active' : ''}`}
            onClick={() => chooseFeed(feed.value)}
          >
            {feed.label}
          </button>
        ))}
      </div>
      <p className="community-feed-hint">{activeFeed.hint}{!loading && !error && ` · ${total} issue${total === 1 ? '' : 's'}`}</p>

      {locationError && sort === 'nearby' ? (
        <p className="form-message error" role="alert">{locationError}</p>
      ) : loading ? (
        <p className="page-state" aria-live="polite">Loading civic issues…</p>
      ) : error ? (
        <p className="form-message error" role="alert">{error}</p>
      ) : issues.length === 0 ? (
        <section className="empty-state">
          <span className="dashboard-icon">⌁</span>
          <h2>No civic issues here yet</h2>
          <p>{sort === 'trending' ? 'Nothing has picked up community activity this week.' : 'Try another feed, category or search.'}</p>
        </section>
      ) : (
        <section className="civic-feed">
          {issues.map((issue) => (
            <CommunityIssueCard key={issue.id} issue={issue} canEngage={canEngage} onChange={replaceIssue} />
          ))}
          {hasMore && (
            <button type="button" className="button button-secondary community-more" onClick={() => fetchPage(page + 1)} disabled={loadingMore}>
              {loadingMore ? 'Loading…' : 'Load more issues'}
            </button>
          )}
        </section>
      )}
    </AppShell>
  )
}
