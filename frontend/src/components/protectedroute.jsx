import { useContext } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AuthContext } from '../context/authcontextvalue.jsx'
import { homeRouteForRole } from '../utils/roleHome.js'

export default function ProtectedRoute({ allowedRoles }) {
  const { isAuthenticated, isLoading, user } = useContext(AuthContext)
  const location = useLocation()
  if (isLoading) return <main className="auth-loading" aria-live="polite">Restoring your session…</main>
  if (!isAuthenticated) return <Navigate to="/login" replace state={{ from: location }} />
  if (allowedRoles && !allowedRoles.includes(user?.role)) return <Navigate to={homeRouteForRole(user?.role)} replace state={{ from: location }} />
  return <Outlet />
}
