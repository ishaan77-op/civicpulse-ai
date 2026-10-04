export const CATEGORY_ICONS = {
  'Road Infrastructure': '🚧',
  'Garbage and Waste': '🗑️',
  'Water Supply': '🚰',
  'Street Lighting': '💡',
  Drainage: '🌊',
  'Public Safety': '🛡️',
  Other: '📍',
}

export const CATEGORIES = Object.keys(CATEGORY_ICONS)

export const VERIFICATION_OPTIONS = [
  { value: 'STILL_EXISTS', label: 'Yes, still exists', short: 'still present', icon: '✓' },
  { value: 'RESOLVED', label: 'Looks resolved', short: 'resolved', icon: '✕' },
  { value: 'NOT_SURE', label: 'Not sure', short: 'not sure', icon: '?' },
]

export const statusBadgeClass = (status) =>
  `status status-${String(status || 'Pending').toLowerCase().replaceAll(' ', '-')}`

export function relativeTime(value) {
  if (!value) return ''
  const date = new Date(value)
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (Number.isNaN(seconds)) return ''
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.round(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.round(months / 12)}y ago`
}

export const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`
