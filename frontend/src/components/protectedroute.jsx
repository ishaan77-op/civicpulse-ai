import { useContext } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AuthContext } from '../context/authcontextvalue.jsx'

export default function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useContext(AuthContext)
  const location = useLocation()
  if (isLoading) return <main className="auth-loading" aria-live="polite">Restoring your session…</main>
  return isAuthenticated ? <Outlet /> : <Navigate to="/login" replace state={{ from: location }} />
}
