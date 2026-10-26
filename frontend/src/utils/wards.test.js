import assert from 'node:assert/strict'
import { test } from 'node:test'
import { assignableOfficers, validateWardForm, WARD_LIMITS } from './wards.js'

test('a ward needs a name; code and source are optional', () => {
  assert.match(validateWardForm({ name: '   ' }), /required/)
  assert.equal(validateWardForm({ name: 'Ward 1' }), '')
  assert.equal(validateWardForm({ name: 'Ward 1', code: 'W-1', source: 'Circular' }), '')
})

test('length limits mirror the server', () => {
  assert.match(validateWardForm({ name: 'x'.repeat(WARD_LIMITS.name + 1) }), /at most 120/)
  assert.match(validateWardForm({ name: 'ok', code: 'c'.repeat(WARD_LIMITS.code + 1) }), /at most 32/)
  assert.match(validateWardForm({ name: 'ok', source: 's'.repeat(WARD_LIMITS.source + 1) }), /at most 255/)
})

test('only unsuspended Officers not already active in the ward are assignable', () => {
  const users = [
    { id: 1, role: 'Officer', is_suspended: false },
    { id: 2, role: 'Officer', is_suspended: true },
    { id: 3, role: 'Citizen', is_suspended: false },
    { id: 4, role: 'Chief Officer', is_suspended: false },
    { id: 5, role: 'Admin', is_suspended: false },
    { id: 6, role: 'Officer', is_suspended: false },
  ]
  const assignments = [
    { is_active: true, officer: { id: 1 } },
    { is_active: false, officer: { id: 6 } }, // ended: may be assigned again
  ]
  assert.deepEqual(assignableOfficers(users, assignments).map((user) => user.id), [6])
})
