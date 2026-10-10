import api from './api.js'

export const createComplaint = (complaint) =>
  api.post('/complaints/', complaint)

export const getComplaints = () =>
  api.get('/complaints/')

export const getComplaint = (id) =>
  api.get(`/complaints/${id}`)

export const updateComplaint = (id, complaint) =>
  api.put(`/complaints/${id}`, complaint)

export const updateComplaintStatus = (id, status) =>
  api.put(`/complaints/${id}/status`, { status })

export const rejectComplaint = (id, reason, explanation) =>
  api.put(`/complaints/${id}/reject`, { reason, explanation })

export const reopenRejectedComplaint = (id) =>
  api.put(`/complaints/${id}/reopen-rejection`)

// Officer API calls
export const getOfficerComplaints = (params) =>
  api.get('/officers/complaints', { params })

export const getRejectedComplaints = () =>
  api.get('/officers/complaints', { params: { rejection_status: 'Rejected' } })

export const getOfficerStats = () =>
  api.get('/officers/stats')

export const getHeatmapData = (params) =>
  api.get('/officers/heatmap', { params })

export const getSpamReports = (params) =>
  api.get('/officers/spam', { params })

export const reviewSpamReport = (id, decision) =>
  api.put(`/officers/spam/${id}/review`, { decision })

export const reopenSpamReport = (id) =>
  api.put(`/officers/spam/${id}/reopen`)

export const getIssues = (params) =>
  api.get('/officers/issues', { params })

export const getIssueComplaints = (id) =>
  api.get(`/officers/issues/${id}/complaints`)

export const updateIssueStatus = (id, status) =>
  api.put(`/officers/issues/${id}/status`, { status })

// Officer work updates (Feature 1: Field-Work Evidence)
export const getWorkUpdates = (complaintId) =>
  api.get(`/officers/complaints/${complaintId}/work-updates`)

export const createWorkUpdate = (complaintId, formData) =>
  api.post(`/officers/complaints/${complaintId}/work-updates`, formData)

// Admin API calls
export const getAdminAnalytics = () =>
  api.get('/admin/analytics')

export const getAdminUsers = () =>
  api.get('/admin/users')

export const updateUserRole = (userId, role) =>
  api.put(`/admin/users/${userId}/role`, { role })

// Chief Officer: Feature 2 – Resolution Review
export const submitResolutionReview = (complaintId, formData) =>
  api.post(`/officers/complaints/${complaintId}/resolution-review`, formData)

export const getResolutionReview = (complaintId) =>
  api.get(`/officers/complaints/${complaintId}/resolution-review`)

export const getResolutionQueue = () =>
  api.get('/chief-officer/resolution-queue')

export const decideResolutionReview = (reviewId, decision, rejectionNote) =>
  api.put(`/chief-officer/resolution-reviews/${reviewId}/decide`, {
    decision,
    rejection_note: rejectionNote || undefined,
  })