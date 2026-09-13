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

// Officer API calls
export const getOfficerComplaints = (params) =>
  api.get('/officers/complaints', { params })

export const getOfficerStats = () =>
  api.get('/officers/stats')

// Admin API calls
export const getAdminAnalytics = () =>
  api.get('/admin/analytics')

export const getAdminUsers = () =>
  api.get('/admin/users')

export const updateUserRole = (userId, role) =>
  api.put(`/admin/users/${userId}/role`, { role })