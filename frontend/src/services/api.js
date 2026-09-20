import axios from 'axios'
import { API_BASE_URL } from '../config/api.js'

const api = axios.create({
  baseURL: API_BASE_URL,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('civicpulse_token')

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.dispatchEvent(new Event('civicpulse:auth-expired'))
    }

    return Promise.reject(error)
  },
)

export default api

export function apiErrorMessage(
  error,
  fallback = 'Something went wrong. Please try again.',
) {
  if (!error.response && error.request) {
    return "Can't reach the server. Make sure the backend is running and try again."
  }

  return (
    error.response?.data?.message ||
    error.response?.data?.error ||
    fallback
  )
}