import { useCallback, useEffect, useState } from 'react'
import AppShell from '../components/appshell.jsx'
import ChiefAnalytics from '../components/ChiefAnalytics.jsx'
import ChiefHome from '../components/ChiefHome.jsx'
import FollowUpQueue from '../components/FollowUpQueue.jsx'
import RateWork from '../components/RateWork.jsx'
import RatingsHistory from '../components/RatingsHistory.jsx'
import ResolutionQueue from '../components/ResolutionQueue.jsx'
import WardsOfficers from '../components/WardsOfficers.jsx'
import { apiErrorMessage } from '../services/api.js'
import { getOverview } from '../services/performanceservice.js'
import { permissionMessage } from '../utils/performance.js'

const TABS = [
  { id: 'home', label: 'Overview' },
  { id: 'directory', label: 'Wards & Officers' },
  { id: 'reviews', label: 'Resolution reviews' },
  { id: 'quality', label: 'Ratings & work quality' },
  { id: 'followups', label: 'Corrective follow-ups' },
  { id: 'analytics', label: 'Analytics' },
]

// Supervisory workspace: reviewing completed work, rating it, and following up
// on poor work, across the whole municipality. User, role and ward
// administration are not here (Admin only).
export default function ChiefOfficerDashboard() {
  const [tab, setTab] = useState('home')
  const [qualityView, setQualityView] = useState('rate')
  const [directory, setDirectory] = useState({ status: 'loading', wards: [], officers: [], error: '' })

  const loadDirectory = useCallback(async () => {
    try {
      const { data } = await getOverview()
      setDirectory({ status: 'ready', wards: data.wards.items, officers: data.officers.items, error: '' })
    } catch (err) {
      setDirectory({
        status: 'error', wards: [], officers: [],
        error: permissionMessage(err.response?.status, apiErrorMessage(err, 'Could not load the officer and ward directory.')),
      })
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(loadDirectory, 0)
    return () => window.clearTimeout(timer)
  }, [loadDirectory])

  return (
    <AppShell eyebrow="Municipal Supervision" title="Chief Officer">
      <div className="admin-tabs resolution-tabs" role="tablist" aria-label="Chief Officer sections">
        {TABS.map((item) => (
          <button key={item.id} type="button" role="tab" aria-selected={tab === item.id}
            className={`tab-btn ${tab === item.id ? 'active' : ''}`} onClick={() => setTab(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      {directory.status === 'error' && (
        <div>
          <p className="form-message error" role="alert">{directory.error}</p>
          <button type="button" className="button" onClick={loadDirectory}>Try again</button>
        </div>
      )}
      {directory.status !== 'error' && (
        tab === 'home' ? <ChiefHome onNavigate={setTab} />
          : tab === 'directory' ? <WardsOfficers wards={directory.wards} officers={directory.officers} />
            : tab === 'reviews' ? <ResolutionQueue />
              : tab === 'quality' ? (
                <>
                  <div className="admin-tabs resolution-tabs" role="tablist" aria-label="Ratings views">
                    <button type="button" role="tab" aria-selected={qualityView === 'rate'} className={`tab-btn ${qualityView === 'rate' ? 'active' : ''}`} onClick={() => setQualityView('rate')}>Rate approved work</button>
                    <button type="button" role="tab" aria-selected={qualityView === 'history'} className={`tab-btn ${qualityView === 'history' ? 'active' : ''}`} onClick={() => setQualityView('history')}>All ratings</button>
                  </div>
                  {qualityView === 'rate' ? <RateWork officers={directory.officers} /> : <RatingsHistory officers={directory.officers} />}
                </>
              )
                : tab === 'followups' ? <FollowUpQueue officers={directory.officers} />
                  : <ChiefAnalytics wards={directory.wards} officers={directory.officers} />
      )}
    </AppShell>
  )
}
