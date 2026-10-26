// Early, readable feedback for the Admin ward screens. The server enforces the
// same limits and remains the authority.

export const WARD_LIMITS = { name: 120, code: 32, source: 255, reason: 500 }

export function validateWardForm({ name = '', code = '', source = '' }) {
  if (!name.trim()) return 'Ward name is required.'
  if (name.trim().length > WARD_LIMITS.name) return `Ward name must be at most ${WARD_LIMITS.name} characters.`
  if (code.trim().length > WARD_LIMITS.code) return `Ward code must be at most ${WARD_LIMITS.code} characters.`
  if (source.trim().length > WARD_LIMITS.source) return `Source must be at most ${WARD_LIMITS.source} characters.`
  return ''
}

// Users the Admin may assign to this ward: current Officers who are not
// suspended and not already actively assigned to it. (Role and suspension are
// re-checked by the server.)
export function assignableOfficers(users = [], assignments = []) {
  const active = new Set(assignments.filter((row) => row.is_active).map((row) => row.officer.id))
  return users.filter((user) => user.role === 'Officer' && !user.is_suspended && !active.has(user.id))
}

export function describeAssignmentState(assignment) {
  if (assignment.is_active) return 'Active'
  return 'Ended'
}
