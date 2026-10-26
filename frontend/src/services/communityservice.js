import api from './api.js'

// Level 2 community API. Note what is never sent: user ids, counts, scores
// or roles - the backend derives all of those from the signed-in session.

export const getCommunityFeed = (params) =>
  api.get('/community/feed', { params })

export const getCommunityIssue = (id) =>
  api.get(`/community/issues/${id}`)

export const supportIssue = (id) =>
  api.post(`/community/issues/${id}/support`)

export const removeSupport = (id) =>
  api.delete(`/community/issues/${id}/support`)

export const verifyIssue = (id, verificationType) =>
  api.post(`/community/issues/${id}/verify`, { verification_type: verificationType })

export const withdrawVerification = (id) =>
  api.delete(`/community/issues/${id}/verify`)

export const getIssueComments = (id, params) =>
  api.get(`/community/issues/${id}/comments`, { params })

export const postIssueComment = (id, content) =>
  api.post(`/community/issues/${id}/comments`, { content })

export const editComment = (commentId, content) =>
  api.put(`/community/comments/${commentId}`, { content })

export const deleteComment = (commentId) =>
  api.delete(`/community/comments/${commentId}`)

export const reportComment = (commentId, reason) =>
  api.post(`/community/comments/${commentId}/report`, { reason })

export const getMyImpact = () =>
  api.get('/community/me/impact')

export const getMyActivity = (params) =>
  api.get('/community/me/activity', { params })

// Officer / Admin
export const getModerationComments = (params) =>
  api.get('/community/moderation/comments', { params })

export const moderateComment = (commentId, decision, reason) =>
  api.put(`/community/moderation/comments/${commentId}`, { decision, reason })

export const getIssueIntelligence = (id) =>
  api.get(`/community/issues/${id}/intelligence`)

// Admin
export const getCommunityAnalytics = () =>
  api.get('/community/analytics')
