import api from './api.js'

// Staff context for one civic issue: { issue, complaints, review_checklist, reviews }.
export const getIssueResolutionContext = (issueId) =>
  api.get(`/issues/${issueId}/resolution-reviews`)

// { work_updates: [...] }
export const getWorkUpdates = (issueId) =>
  api.get(`/issues/${issueId}/work-updates`)

// multipart: note, status, complaint_id?, latitude?, longitude?, image?
// The Idempotency-Key header makes a retried request safe (200 replay, not a duplicate).
export const createWorkUpdate = (issueId, formData, idempotencyKey) =>
  api.post(`/issues/${issueId}/work-updates`, formData, {
    headers: { 'Idempotency-Key': idempotencyKey },
  })

// multipart: completion_note, image, dispositions (JSON string), supersedes_review_id?
export const submitResolutionReview = (issueId, formData) =>
  api.post(`/issues/${issueId}/resolution-reviews`, formData)

// { queue: [...pending], stale: [...stale] }; each entry is
// { issue, complaints, review_checklist, review }.
export const getResolutionQueue = () =>
  api.get('/chief-officer/resolution-queue')

// decision: 'Approved' | 'Rejected'; rejection_reason is required (10+ chars) for Rejected.
export const decideResolutionReview = (reviewId, decision, rejectionReason) =>
  api.put(`/chief-officer/resolution-reviews/${reviewId}/decision`, {
    decision,
    ...(decision === 'Rejected' ? { rejection_reason: rejectionReason } : {}),
  })
