// How a citizen is told about their complaint's resolution progress.
// The backend decides what evidence a citizen may see (completion photo and
// report only after Chief Officer approval); this only words what it returned.

export function describeEvidence(evidence) {
  const state = evidence?.state
  switch (state) {
    case 'approved':
      return {
        tone: 'approved',
        title: 'Resolved and verified',
        message: 'The Chief Officer approved the completed work for this issue.',
        showAfter: true,
      }
    case 'awaiting_review':
      return {
        tone: 'pending',
        title: 'Work submitted - awaiting verification',
        message: 'The field team has submitted work for the Chief Officer to verify. It is not marked complete yet, so no completion photo is shown.',
        showAfter: false,
      }
    case 'returned':
      return {
        tone: 'returned',
        title: 'Returned for correction',
        message: 'The submitted work was sent back to the field team for more work. The issue is not resolved yet.',
        showAfter: false,
      }
    case 'none':
      return {
        tone: 'none',
        title: 'No completion photo yet',
        message: 'When the work is finished and approved by the Chief Officer, the after photo and completion report will appear here.',
        showAfter: false,
      }
    default:
      return null // not_applicable or an unknown state: show nothing rather than guess
  }
}

// The completion photo is only ever offered for an approved state with a file.
export function afterImageUrl(evidence) {
  return evidence?.state === 'approved' ? evidence.after?.image_url || null : null
}
