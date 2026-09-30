import api from './api.js'

export const getNotifications = (params) =>
  api.get('/notifications/', { params })

export const markNotificationRead = (id) =>
  api.put(`/notifications/${id}/read`)
