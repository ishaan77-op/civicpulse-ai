import { useCallback, useEffect, useMemo, useState } from 'react'
import { getProfile, loginRequest, registerRequest } from '../services/authservice.js'
import { AuthContext } from './authcontextvalue.jsx'

const TOKEN_KEY = 'civicpulse_token'
const USER_KEY = 'civicpulse_user'
export { AuthContext } from './authcontextvalue.jsx'

const storedUser = () => {
  try { return JSON.parse(localStorage.getItem(USER_KEY)) } catch { return null }
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY))
  const [user, setUser] = useState(storedUser)
  const [isLoading, setIsLoading] = useState(() => Boolean(localStorage.getItem(TOKEN_KEY)))

  const clearAuth = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
    setIsLoading(false)
  }, [])

  const persistAuth = useCallback((authToken, authUser) => {
    localStorage.setItem(TOKEN_KEY, authToken)
    localStorage.setItem(USER_KEY, JSON.stringify(authUser))
    setToken(authToken)
    setUser(authUser)
  }, [])

  useEffect(() => {
    if (!token) return undefined
    let active = true
    getProfile()
      .then(({ data }) => { if (active) { const profile = data.user || data; persistAuth(token, profile) } })
      .catch(() => { if (active) clearAuth() })
      .finally(() => { if (active) setIsLoading(false) })
    return () => { active = false }
  }, [token, persistAuth, clearAuth])

  useEffect(() => {
    window.addEventListener('civicpulse:auth-expired', clearAuth)
    return () => window.removeEventListener('civicpulse:auth-expired', clearAuth)
  }, [clearAuth])

  const login = useCallback(async (credentials) => {
    const { data } = await loginRequest(credentials)
    persistAuth(data.token, data.user)
    return data.user
  }, [persistAuth])

  const register = useCallback(async (details) => {
    const { data } = await registerRequest(details)
    if (data.token && data.user) persistAuth(data.token, data.user)
    return data
  }, [persistAuth])

  const value = useMemo(() => ({ token, user, isLoading, isAuthenticated: Boolean(token && user), login, logout: clearAuth, register }), [token, user, isLoading, login, clearAuth, register])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
