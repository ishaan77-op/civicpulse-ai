import { useEffect, useState } from 'react'
import { getNotifications, markNotificationRead } from '../services/notificationservice.js'

function NotificationBanner() {
  const [queue, setQueue] = useState([])
  const [dismissing, setDismissing] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      try {
        const { data } = await getNotifications({ unread_only: true })
        setQueue(data.notifications || [])
      } catch {
        // Non-critical - a citizen simply won't see a notification this
        // load if the request fails; nothing else on the page depends on it.
      }
    }, 0)

    return () => window.clearTimeout(timer)
  }, [])

  if (queue.length === 0) {
    return null
  }

  const current = queue[0]

  const dismiss = async () => {
    setDismissing(true)
    try {
      await markNotificationRead(current.id)
    } catch {
      // Even if marking-as-read fails, still move on for this session so
      // the citizen isn't stuck; it will simply reappear next load.
    } finally {
      setQueue((rest) => rest.slice(1))
      setDismissing(false)
    }
  }

  return (
    <div
      role="alert"
      style={{
        marginBottom: '16px',
        padding: '14px 16px',
        borderRadius: '10px',
        background: '#fff3cd',
        color: '#664d03',
      }}
    >
      <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{current.message}</p>

      <button
        type="button"
        onClick={dismiss}
        disabled={dismissing}
        style={{
          marginTop: '10px',
          padding: '8px 14px',
          borderRadius: '7px',
          border: 'none',
          background: '#664d03',
          color: '#fff',
          cursor: dismissing ? 'wait' : 'pointer',
        }}
      >
        Got it
      </button>

      {queue.length > 1 && (
        <span style={{ marginLeft: '10px', fontSize: '12px' }}>
          +{queue.length - 1} more notification{queue.length - 1 === 1 ? '' : 's'}
        </span>
      )}
    </div>
  )
}

export default NotificationBanner
