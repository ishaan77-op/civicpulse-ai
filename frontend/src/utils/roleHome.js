export function homeRouteForRole(role) {
  if (role === 'Officer') return '/officer'
  if (role === 'Admin') return '/admin'
  if (role === 'Chief Officer') return '/chief-officer'
  return '/dashboard'
}
