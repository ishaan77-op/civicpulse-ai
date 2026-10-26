import api from './api.js'

// ---- Chief Officer (municipality-wide; the server refuses every other role)
// overview: { scope, wards, officers, issues, complaints, reviews, ratings, follow_ups, resolution_time, trends, definitions }
export const getOverview = (params) => api.get('/chief-officer/overview', { params })
// { approved_work: [{ resolution_review_id, issue, officer, approved_at, rating, follow_up }] }
export const getApprovedWork = (params) => api.get('/chief-officer/approved-work', { params })
// body: { stars, explanation?, revises_rating_id? } -> { rating, follow_up }
export const rateReview = (reviewId, body) => api.post(`/chief-officer/resolution-reviews/${reviewId}/rating`, body)
export const getReviewRatings = (reviewId) => api.get(`/chief-officer/resolution-reviews/${reviewId}/ratings`)
export const getRatings = (params) => api.get('/chief-officer/ratings', { params })
export const getFollowUps = (params) => api.get('/chief-officer/follow-ups', { params })
export const getFollowUp = (id) => api.get(`/chief-officer/follow-ups/${id}`)
export const assignFollowUp = (id, officerId, reason) =>
  api.put(`/chief-officer/follow-ups/${id}/assign`, { officer_id: officerId, ...(reason ? { reason } : {}) })
export const verifyFollowUp = (id, decision, note) =>
  api.put(`/chief-officer/follow-ups/${id}/verify`, { decision, ...(note ? { note } : {}) })

// Directory views (read-only): ward assignment record, and one Officer's work/ratings/submissions.
export const getWard = (id) => api.get(`/chief-officer/wards/${id}`)
export const getOfficerDetail = (id, params) => api.get(`/chief-officer/officers/${id}`, { params })

// Staff-only correction photo: the image bytes, sent only with the caller's token.
// `path` is the API-relative path the server put on the event (image_path).
export const getEvidenceImage = (path, signal) => api.get(path, { responseType: 'blob', signal })

// ---- Officer (own records only)
export const getMyRatings = (params) => api.get('/officers/me/ratings', { params })
export const getMyFollowUps = (params) => api.get('/officers/me/follow-ups', { params })
export const getMyFollowUp = (id) => api.get(`/officers/me/follow-ups/${id}`)
// multipart: note, image?
export const submitCorrection = (id, formData) => api.post(`/officers/me/follow-ups/${id}/submit-correction`, formData)
