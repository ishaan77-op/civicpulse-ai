import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  FOLLOW_UP_STATUSES, assignableOfficers, attentionItems, cleanParams, effectiveRating, followUpActions, followUpTone,
  evidenceErrorMessage, hoursLabel, isLowRating, metric, pageInfo, permissionMessage, stars, unassignedOfficers,
  validateCorrection, validateRating, validateVerification,
} from './performance.js'

test('1- and 2-star ratings require an explanation; 3 to 5 do not', () => {
  assert.match(validateRating({ stars: 1, explanation: '  ' }), /Explain/)
  assert.match(validateRating({ stars: 2 }), /Explain/)
  assert.equal(validateRating({ stars: 2, explanation: 'Edges left rough' }), '')
  for (const value of [3, 4, 5]) assert.equal(validateRating({ stars: value }), '')
})

test('ratings outside 1-5 or not whole numbers are rejected', () => {
  for (const value of [0, 6, 2.5, '3', null, undefined]) assert.match(validateRating({ stars: value, explanation: 'x' }), /1 to 5/)
})

test('a revision always needs a reason', () => {
  assert.match(validateRating({ stars: 5 }, { id: 1 }), /Explain why/)
  assert.equal(validateRating({ stars: 5, explanation: 'Re-inspected' }, { id: 1 }), '')
})

test('low rating detection and star display', () => {
  assert.equal(isLowRating(1), true)
  assert.equal(isLowRating(2), true)
  assert.equal(isLowRating(3), false)
  assert.equal(stars(4), '★★★★☆')
})

test('verification: returning needs a note, closing does not', () => {
  assert.equal(validateVerification('Close'), '')
  assert.match(validateVerification('Return', ' '), /still needed/)
  assert.equal(validateVerification('Return', 'Edge still rough'), '')
  assert.match(validateVerification('Approve'), /close or return/)
})

test('corrections need a note', () => {
  assert.match(validateCorrection(' '), /Describe/)
  assert.equal(validateCorrection('Re-laid the surface'), '')
})

test('only the Chief Officer can close; an Officer can only submit a correction on an assigned case', () => {
  assert.deepEqual(followUpActions('Awaiting Assignment', 'Chief Officer'), ['assign'])
  assert.deepEqual(followUpActions('Assigned', 'Chief Officer'), ['reassign'])
  assert.deepEqual(followUpActions('Correction Submitted', 'Chief Officer'), ['close', 'return'])
  assert.deepEqual(followUpActions('Closed', 'Chief Officer'), [])
  assert.deepEqual(followUpActions('Assigned', 'Officer'), ['submitCorrection'])
  for (const status of ['Awaiting Assignment', 'Correction Submitted', 'Closed', 'Withdrawn']) {
    assert.deepEqual(followUpActions(status, 'Officer'), [])
  }
  for (const role of ['Admin', 'Citizen', undefined]) {
    assert.deepEqual(followUpActions('Correction Submitted', role), [])
  }
  assert.ok(!followUpActions('Correction Submitted', 'Officer').includes('close'))
})

test('blank filters are dropped and unavailable data is never shown as zero', () => {
  assert.deepEqual(cleanParams({ ward_id: '', officer_id: 3, from: null, to: undefined, status: 'Assigned' }), { officer_id: 3, status: 'Assigned' })
  assert.equal(metric(null), 'Unavailable')
  assert.equal(metric(0), '0')
  assert.equal(hoursLabel(null), 'Unavailable')
  assert.equal(hoursLabel(0), '0 h')
  assert.equal(hoursLabel(72), '3.0 days')
})

test('suspended officers and the current assignee are not offered for assignment', () => {
  const officers = [{ id: 1 }, { id: 2, is_suspended: true }, { id: 3, is_suspended: false }]
  assert.deepEqual(assignableOfficers(officers, 1).map((o) => o.id), [3])
})

test('paging describes the visible window and the neighbours', () => {
  assert.deepEqual(pageInfo(0, 20, 0), { from: 0, to: 0, total: 0, hasPrev: false, hasNext: false, prevOffset: 0, nextOffset: 20 })
  const middle = pageInfo(45, 20, 20)
  assert.equal(middle.from, 21)
  assert.equal(middle.to, 40)
  assert.ok(middle.hasPrev && middle.hasNext)
  assert.equal(middle.prevOffset, 0)
  assert.equal(pageInfo(45, 20, 40).to, 45)
  assert.equal(pageInfo(45, 20, 40).hasNext, false)
})

test('attention items list only waiting work, with no overdue claims', () => {
  const overview = {
    reviews: { pending_decision: 2, stale_awaiting_resubmission: 0 },
    follow_ups: { by_status: { 'Awaiting Assignment': 1, Assigned: 4, 'Correction Submitted': 3, Closed: 9 } },
    ratings: { approved_not_yet_rated: 5 },
  }
  const items = attentionItems(overview)
  assert.deepEqual(items.map((item) => item.id), ['pending-reviews', 'verification', 'unassigned', 'unrated'])
  assert.deepEqual(items.map((item) => item.count), [2, 3, 1, 5])
  assert.ok(!JSON.stringify(items).match(/overdue|late|breach/i))
  // wording agrees with the count
  assert.deepEqual(items.map((item) => item.label), [
    'resolution reviews awaiting your decision', 'corrections awaiting your verification',
    'low-rating follow-up to assign', 'approved jobs not yet rated',
  ])
  assert.equal(attentionItems({ reviews: { pending_decision: 1, stale_awaiting_resubmission: 1 } }).map((item) => item.label).join('|'),
    'resolution review awaiting your decision|withdrawn review waiting on an Officer to resubmit')
  assert.deepEqual(attentionItems({ reviews: {}, follow_ups: { by_status: {} }, ratings: {} }), [])
  assert.deepEqual(attentionItems(null), [])
  assert.deepEqual(attentionItems({ reviews: { pending_decision: null } }), []) // unavailable is not a task
})

test('follow-up statuses match the four-state workflow', () => {
  assert.deepEqual(FOLLOW_UP_STATUSES, ['Awaiting Assignment', 'Assigned', 'Correction Submitted', 'Closed'])
  assert.equal(followUpTone('Closed'), 'approved')
})

test('directory helpers rely on server-provided assignment status only', () => {
  const officers = [{ id: 1, assignment_status: 'Assigned' }, { id: 2, assignment_status: 'Unassigned' }, { id: 3 }]
  assert.deepEqual(unassignedOfficers(officers).map((o) => o.id), [2])
})

test('a 403 is explained as a permission problem, other errors keep their own message', () => {
  assert.match(permissionMessage(403, 'x'), /permission/)
  assert.equal(permissionMessage(500, 'Server problem'), 'Server problem')
})

test('the effective rating is the one the server marks effective', () => {
  const history = [{ id: 1, stars: 4, is_effective: false }, { id: 2, stars: 5, is_effective: true }]
  assert.equal(effectiveRating(history).id, 2)
  assert.equal(effectiveRating([]), null)
})

test('staff photo errors are explained without implying the file exists or not', () => {
  assert.match(evidenceErrorMessage(403), /no longer have access/)
  assert.match(evidenceErrorMessage(401), /no longer have access/)
  assert.match(evidenceErrorMessage(404), /no longer available/)
  assert.match(evidenceErrorMessage(500), /could not be loaded/)
  assert.match(evidenceErrorMessage(undefined), /could not be loaded/)
})
