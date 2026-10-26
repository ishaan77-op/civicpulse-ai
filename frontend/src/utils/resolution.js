// Pure helpers for the issue-wide field-work and resolution-review workflow.
// Kept free of React/DOM so they can be unit-tested with `node --test`.
// The backend stays the authority on every rule below; these only give the
// user early, readable feedback.

// "Resolved" is reachable only through Chief Officer approval, and
// "Pending Review" only by submitting a resolution review.
export const OFFICER_SETTABLE_STATUSES = ['Pending', 'In Progress']
export const DISPOSITIONS = ['Addressed', 'Duplicate Covered']
export const MIN_REJECTION_REASON_LENGTH = 10
export const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp'

const STATUS_ICONS = { Pending: '🟡', 'In Progress': '🔵', 'Pending Review': '🟣', Resolved: '🟢' }

export function statusIcon(status) {
  return STATUS_ICONS[status] || '⚪'
}

export function statusClass(status) {
  return `status-select-${String(status || 'Pending').toLowerCase().replace(/\s+/g, '-')}`
}

// Options for an officer's status dropdown: the two statuses they may set,
// plus the current status shown (disabled) when it is one they cannot set.
export function statusOptions(current) {
  const options = OFFICER_SETTABLE_STATUSES.map((value) => ({ value, label: `${statusIcon(value)} ${value}`, disabled: false }))
  if (current && !OFFICER_SETTABLE_STATUSES.includes(current)) {
    options.push({ value: current, label: `${statusIcon(current)} ${current}`, disabled: true })
  }
  return options
}

export function newIdempotencyKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

export function validateWorkUpdate({ note, status }) {
  if (!String(note || '').trim()) return 'Describe the work done before saving the update.'
  if (!OFFICER_SETTABLE_STATUSES.includes(status)) return 'Choose Pending or In Progress.'
  return ''
}

export function validateRejectionReason(reason) {
  const trimmed = String(reason || '').trim()
  if (!trimmed) return 'A rejection reason is required.'
  if (trimmed.length < MIN_REJECTION_REASON_LENGTH) {
    return `Explain the rejection in at least ${MIN_REJECTION_REASON_LENGTH} characters so the officer knows what to fix.`
  }
  return ''
}

// Complaint ids the officer must give a disposition for.
export function eligibleComplaintIds(checklist = []) {
  return checklist.filter((item) => item.eligible).map((item) => item.complaint_id)
}

export function blockedChecklistItems(checklist = []) {
  return checklist.filter((item) => item.blocked_reason)
}

// entries: { [complaintId]: { disposition, note } }. Returns { dispositions, error }.
export function buildDispositions(eligibleIds, entries = {}) {
  const dispositions = []
  for (const id of eligibleIds) {
    const entry = entries[id] || {}
    if (!DISPOSITIONS.includes(entry.disposition) || !String(entry.note || '').trim()) {
      return { dispositions: [], error: 'Every eligible complaint needs a disposition and a short note.' }
    }
    dispositions.push({ complaint_id: id, disposition: entry.disposition, note: entry.note.trim() })
  }
  if (dispositions.length === 0) {
    return { dispositions, error: 'This issue has no eligible complaints to resolve.' }
  }
  return { dispositions, error: '' }
}

// The review a new submission should replace, if any: only the submitting
// officer's own latest Pending, Stale, or Rejected review (backend rule).
export function reviewToSupersede(reviews = [], userId) {
  const latest = reviews[0]
  if (!latest || latest.submitted_by !== userId) return null
  return ['Pending', 'Stale', 'Rejected'].includes(latest.state) ? latest : null
}

// Why the officer cannot submit a review right now ('' when they can).
export function submissionBlocker({ issue, checklist = [], reviews = [] }, userId) {
  if (!issue) return 'Issue details are not loaded.'
  if (issue.status === 'Resolved') return 'This issue was resolved by Chief Officer approval.'
  const pending = reviews.find((review) => review.state === 'Pending')
  if (pending && pending.submitted_by !== userId) return 'Another officer’s review is already awaiting Chief Officer decision.'
  if (blockedChecklistItems(checklist).length > 0) return 'Some linked complaints still await spam moderation. Finish moderation first.'
  if (eligibleComplaintIds(checklist).length === 0) return 'Every linked complaint was excluded as spam or out of scope, so there is nothing to resolve.'
  return ''
}

export function reviewStateSummary(review) {
  if (!review) return null
  switch (review.state) {
    case 'Pending': return { tone: 'pending', title: 'Awaiting Chief Officer decision', detail: '' }
    case 'Stale': return { tone: 'stale', title: 'Review withdrawn: new information arrived', detail: review.stale_reason || '' }
    case 'Rejected': return { tone: 'rejected', title: 'Chief Officer sent this back for more work', detail: review.rejection_reason || '' }
    case 'Approved': return { tone: 'approved', title: 'Approved by the Chief Officer', detail: '' }
    case 'Superseded': return { tone: 'stale', title: 'Replaced by a newer submission', detail: '' }
    default: return { tone: 'stale', title: review.state, detail: '' }
  }
}

export function toFormData(fields) {
  const data = new FormData()
  for (const [key, value] of Object.entries(fields)) {
    if (value !== undefined && value !== null && value !== '') data.append(key, value)
  }
  return data
}
