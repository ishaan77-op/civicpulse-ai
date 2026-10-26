import assert from 'node:assert/strict'
import { test } from 'node:test'
import { afterImagePath, describeEvidence } from './citizenEvidence.js'

test('only an approved state offers the completion photo', () => {
  assert.equal(describeEvidence({ state: 'approved' }).showAfter, true)
  for (const state of ['awaiting_review', 'returned', 'none']) {
    assert.equal(describeEvidence({ state }).showAfter, false)
  }
})

test('pending and returned work is never described as completed', () => {
  for (const state of ['awaiting_review', 'returned', 'none']) {
    const { title, message } = describeEvidence({ state })
    assert.doesNotMatch(title, /resolved|verified|completed|approved/i)
    assert.match(message, /\bnot\b|\bno\b|When the work is finished/i)
  }
  assert.match(describeEvidence({ state: 'returned' }).message, /not resolved/)
  assert.match(describeEvidence({ state: 'awaiting_review' }).message, /not marked complete/)
  assert.match(describeEvidence({ state: 'approved' }).title, /Resolved and verified/)
})

test('unknown and not-applicable states render nothing', () => {
  assert.equal(describeEvidence({ state: 'not_applicable' }), null)
  assert.equal(describeEvidence({ state: 'surprise' }), null)
  assert.equal(describeEvidence(null), null)
})

test('the after image is ignored unless approved', () => {
  const after = { image_path: '/complaints/7/resolution-evidence/after-image', report: 'done' }
  assert.equal(afterImagePath({ state: 'approved', after }), '/complaints/7/resolution-evidence/after-image')
  assert.equal(afterImagePath({ state: 'awaiting_review', after }), null)
  assert.equal(afterImagePath({ state: 'returned', after }), null)
  assert.equal(afterImagePath({ state: 'approved', after: { image_path: null, report: 'done' } }), null)
  // A public URL on the payload is never used for the completion photo.
  assert.equal(afterImagePath({ state: 'approved', after: { image_url: '/uploads/final.jpg', report: 'done' } }), null)
  assert.equal(afterImagePath(undefined), null)
})
