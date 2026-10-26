import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  buildDispositions,
  eligibleComplaintIds,
  reviewStateSummary,
  reviewToSupersede,
  statusOptions,
  submissionBlocker,
  validateRejectionReason,
  validateWorkUpdate,
} from './resolution.js'

test('officers can never pick Resolved or Pending Review from a dropdown', () => {
  for (const current of ['Pending', 'In Progress', 'Pending Review', 'Resolved']) {
    const selectable = statusOptions(current).filter((option) => !option.disabled).map((option) => option.value)
    assert.deepEqual(selectable, ['Pending', 'In Progress'])
  }
})

test('the current non-settable status is shown but disabled', () => {
  const options = statusOptions('Pending Review')
  assert.equal(options.at(-1).value, 'Pending Review')
  assert.equal(options.at(-1).disabled, true)
  assert.equal(statusOptions('Pending').length, 2)
})

test('work updates need a note and an allowed status', () => {
  assert.match(validateWorkUpdate({ note: '   ', status: 'In Progress' }), /Describe the work/)
  assert.match(validateWorkUpdate({ note: 'Filled the pothole', status: 'Resolved' }), /Pending or In Progress/)
  assert.equal(validateWorkUpdate({ note: 'Filled the pothole', status: 'In Progress' }), '')
})

test('rejection requires a meaningful reason, matching the backend minimum', () => {
  assert.match(validateRejectionReason(''), /required/)
  assert.match(validateRejectionReason('too short'), /at least 10/)
  assert.equal(validateRejectionReason('  Photo does not show the repaired area.  '), '')
})

test('dispositions are built only for eligible complaints and need a note each', () => {
  const checklist = [
    { complaint_id: 1, eligible: true },
    { complaint_id: 2, eligible: false, excluded_reason: 'Confirmed spam' },
    { complaint_id: 3, eligible: true },
  ]
  const ids = eligibleComplaintIds(checklist)
  assert.deepEqual(ids, [1, 3])
  assert.match(buildDispositions(ids, { 1: { disposition: 'Addressed', note: 'ok' } }).error, /Every eligible/)
  assert.match(buildDispositions(ids, { 1: { disposition: 'Bogus', note: 'x' }, 3: { disposition: 'Addressed', note: 'x' } }).error, /Every eligible/)
  const built = buildDispositions(ids, {
    1: { disposition: 'Addressed', note: ' Repaired ' },
    3: { disposition: 'Duplicate Covered', note: 'Same pothole' },
  })
  assert.equal(built.error, '')
  assert.deepEqual(built.dispositions, [
    { complaint_id: 1, disposition: 'Addressed', note: 'Repaired' },
    { complaint_id: 3, disposition: 'Duplicate Covered', note: 'Same pothole' },
  ])
})

test('an issue with no eligible complaints cannot be submitted', () => {
  assert.match(buildDispositions([], {}).error, /no eligible complaints/)
  const blocker = submissionBlocker({
    issue: { status: 'Pending' },
    checklist: [{ complaint_id: 1, eligible: false, excluded_reason: 'Out of scope' }],
    reviews: [],
  }, 5)
  assert.match(blocker, /excluded as spam or out of scope/)
})

test('submission is blocked while moderation is pending, after resolution, or by another officer', () => {
  const base = { issue: { status: 'In Progress' }, checklist: [{ complaint_id: 1, eligible: true }], reviews: [] }
  assert.equal(submissionBlocker(base, 5), '')
  assert.match(submissionBlocker({ ...base, checklist: [{ complaint_id: 1, eligible: false, blocked_reason: 'Awaiting spam moderation' }] }, 5), /moderation/)
  assert.match(submissionBlocker({ ...base, issue: { status: 'Resolved' } }, 5), /resolved/)
  assert.match(submissionBlocker({ ...base, reviews: [{ state: 'Pending', submitted_by: 9 }] }, 5), /Another officer/)
  assert.equal(submissionBlocker({ ...base, reviews: [{ state: 'Pending', submitted_by: 5 }] }, 5), '')
})

test('only the officer’s own latest open review is superseded', () => {
  assert.equal(reviewToSupersede([], 5), null)
  assert.equal(reviewToSupersede([{ id: 3, state: 'Stale', submitted_by: 5 }], 5).id, 3)
  assert.equal(reviewToSupersede([{ id: 3, state: 'Stale', submitted_by: 9 }], 5), null)
  assert.equal(reviewToSupersede([{ id: 3, state: 'Approved', submitted_by: 5 }], 5), null)
})

test('stale and rejected reviews expose their reasons', () => {
  assert.equal(reviewStateSummary({ state: 'Stale', stale_reason: 'A new complaint was linked' }).detail, 'A new complaint was linked')
  assert.equal(reviewStateSummary({ state: 'Rejected', rejection_reason: 'Photo unclear' }).detail, 'Photo unclear')
  assert.equal(reviewStateSummary({ state: 'Pending' }).tone, 'pending')
  assert.equal(reviewStateSummary(null), null)
})
