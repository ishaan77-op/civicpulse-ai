export function homeRouteForRole(role) {
  if (role === 'Officer') return '/officer'
  if (role === 'Chief Officer') return '/chief-officer'
  if (role === 'Admin') return '/admin'
  return '/dashboard'
}
