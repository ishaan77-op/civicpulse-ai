// Single source of truth for displaying a backend timestamp. The backend
// always sends a timezone-qualified ISO-8601 UTC instant (e.g. "...+00:00"),
// so `new Date(value)` already resolves to the correct real-world instant -
// this only ever controls how that instant is *displayed*, always in IST.
// Do not add ad-hoc `new Intl.DateTimeFormat(...)` calls or manual UTC
// offset math elsewhere; use this instead so every page agrees.

const DISPLAY_TIME_ZONE = 'Asia/Kolkata'

const partsFormatter = new Intl.DateTimeFormat('en-US', {
  timeZone: DISPLAY_TIME_ZONE,
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: true,
})

export function formatDateTime(value) {
  if (!value) return 'Date unavailable'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Date unavailable'

  const parts = {}
  for (const part of partsFormatter.formatToParts(date)) {
    parts[part.type] = part.value
  }

  return `${parts.day} ${parts.month} ${parts.year}, ${parts.hour}:${parts.minute} ${parts.dayPeriod}`
}
