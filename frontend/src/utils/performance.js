// Pure rules for ratings, corrective follow-ups and the supervisory overview.
// The server is the authority; these give early, readable feedback and decide
// which controls to show. Nothing here is a security boundary.

export const LOW_RATING_MAX = 2
export const MAX_EXPLANATION = 2000
export const FOLLOW_UP_STATUSES = ['Awaiting Assignment', 'Assigned', 'Correction Submitted', 'Closed']
export const PAGE_SIZE = 20

export function isLowRating(stars) {
  return Number.isInteger(stars) && stars >= 1 && stars <= LOW_RATING_MAX
}

export function stars(value) {
  return '★'.repeat(value) + '☆'.repeat(5 - value)
}

// existing: the review's current effective rating, if any (a revision then needs a reason).
export function validateRating({ stars: value, explanation = '' }, existing = null) {
  if (!Number.isInteger(value) || value < 1 || value > 5) return 'Choose a rating from 1 to 5 stars.'
  const text = explanation.trim()
  if (text.length > MAX_EXPLANATION) return `Keep the explanation under ${MAX_EXPLANATION} characters.`
  if (isLowRating(value) && !text) return 'Explain a 1- or 2-star rating so the Officer knows what to correct.'
  if (existing && !text) return 'Explain why the rating is changing.'
  return ''
}

export function validateVerification(decision, note = '') {
  if (decision !== 'Close' && decision !== 'Return') return 'Choose whether to close or return the correction.'
  if (decision === 'Return' && !note.trim()) return 'Say what is still needed before returning the correction.'
  return ''
}

export function validateCorrection(note = '') {
  return note.trim() ? '' : 'Describe the corrective work you did.'
}

// What a viewer may do with a follow-up in its current status.
export function followUpActions(status, role) {
  if (role === 'Chief Officer') {
    if (status === 'Awaiting Assignment') return ['assign']
    if (status === 'Assigned') return ['reassign']
    if (status === 'Correction Submitted') return ['close', 'return']
    return []
  }
  if (role === 'Officer') return status === 'Assigned' ? ['submitCorrection'] : []
  return []
}

export function followUpTone(status) {
  switch (status) {
    case 'Awaiting Assignment': return 'stale'
    case 'Assigned': return 'pending'
    case 'Correction Submitted': return 'rejected'
    case 'Closed': return 'approved'
    default: return 'stale'
  }
}

// Drops blank filters so they are not sent as empty parameters.
export function cleanParams(params = {}) {
  return Object.fromEntries(Object.entries(params).filter(([, value]) => value !== '' && value !== null && value !== undefined))
}

// Unavailable data is shown as such, never as zero.
export function metric(value, fallback = 'Unavailable') {
  return value === null || value === undefined ? fallback : String(value)
}

export function hoursLabel(hours) {
  if (hours === null || hours === undefined) return 'Unavailable'
  if (hours < 48) return `${hours} h`
  return `${(hours / 24).toFixed(1)} days`
}

export function assignableOfficers(officers = [], currentOfficerId = null) {
  return officers.filter((officer) => !officer.is_suspended && officer.id !== currentOfficerId)
}


// Paging over a server-side list. total/limit/offset come from the API.
export function pageInfo(total, limit, offset) {
  const from = total === 0 ? 0 : offset + 1
  const to = Math.min(offset + limit, total)
  return {
    from,
    to,
    total,
    hasPrev: offset > 0,
    hasNext: offset + limit < total,
    prevOffset: Math.max(0, offset - limit),
    nextOffset: offset + limit,
  }
}

// What the Chief Officer should look at first, from overview figures only.
// Items with nothing waiting are omitted; no thresholds or "overdue" are implied.
export function attentionItems(overview) {
  if (!overview) return []
  const reviews = overview.reviews || {}
  const followUps = overview.follow_ups?.by_status || {}
  const ratings = overview.ratings || {}
  const items = [
    { id: 'pending-reviews', count: reviews.pending_decision, one: 'resolution review awaiting your decision', many: 'resolution reviews awaiting your decision', tab: 'reviews' },
    { id: 'verification', count: followUps['Correction Submitted'], one: 'correction awaiting your verification', many: 'corrections awaiting your verification', tab: 'followups' },
    { id: 'unassigned', count: followUps['Awaiting Assignment'], one: 'low-rating follow-up to assign', many: 'low-rating follow-ups to assign', tab: 'followups' },
    { id: 'unrated', count: ratings.approved_not_yet_rated, one: 'approved job not yet rated', many: 'approved jobs not yet rated', tab: 'quality' },
    { id: 'stale', count: reviews.stale_awaiting_resubmission, one: 'withdrawn review waiting on an Officer to resubmit', many: 'withdrawn reviews waiting on an Officer to resubmit', tab: 'reviews' },
  ]
  return items
    .filter((item) => Number.isInteger(item.count) && item.count > 0)
    .map(({ one, many, ...item }) => ({ ...item, label: item.count === 1 ? one : many }))
}

// Unassigned Officers, for the directory: only people the API says have no active ward.
export function unassignedOfficers(officers = []) {
  return officers.filter((officer) => officer.assignment_status === 'Unassigned')
}

// Staff-facing wording for a failed request that the server answered 403.
export function permissionMessage(status, fallback) {
  return status === 403 ? 'You do not have permission to view this. Sign in with a Chief Officer account.' : fallback
}

// The one effective rating in a history, if any (history is oldest first).
export function effectiveRating(history = []) {
  return history.find((rating) => rating.is_effective) || null
}

// Why a staff-only photo did not load, in words for the person looking at it.
export function evidenceErrorMessage(status) {
  if (status === 401 || status === 403) return 'You no longer have access to this photo.'
  if (status === 404) return 'This photo is no longer available.'
  return 'The photo could not be loaded.'
}
