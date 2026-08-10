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