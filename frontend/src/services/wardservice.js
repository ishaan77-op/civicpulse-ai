import api from './api.js'

// Admin-only ward registry. Responses:
//   list:        { wards: [ward] }
//   create/update/activate/deactivate: { message, ward }
//   assignments: { ward, assignments: [assignment] }   (newest first, active and ended)
//   assign/end:  { message, assignment }
export const listWards = (params) => api.get('/admin/wards', { params })
export const createWard = (ward) => api.post('/admin/wards', ward)
export const updateWard = (id, ward) => api.put(`/admin/wards/${id}`, ward)
export const deactivateWard = (id) => api.put(`/admin/wards/${id}/deactivate`)
export const activateWard = (id) => api.put(`/admin/wards/${id}/activate`)

export const listWardAssignments = (wardId) => api.get(`/admin/wards/${wardId}/assignments`)
export const assignOfficer = (wardId, officerId, reason) =>
  api.post(`/admin/wards/${wardId}/assignments`, { officer_id: officerId, ...(reason ? { reason } : {}) })
export const endAssignment = (wardId, assignmentId, reason) =>
  api.put(`/admin/wards/${wardId}/assignments/${assignmentId}/end`, reason ? { reason } : {})
