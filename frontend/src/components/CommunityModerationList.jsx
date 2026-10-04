import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiErrorMessage } from '../services/api.js'
import { getModerationComments, moderateComment } from '../services/communityservice.js'
import { formatDateTime as formatDate } from '../utils/formatDateTime.js'

// Same philosophy as spam review: automated checks and citizen reports only
// queue a comment - an Officer/Admin makes the (auditable) decision.
export default function CommunityModerationList() {
  const [status, setStatus] = useState('Flagged')
  const [comments, setComments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionError, setActionError] = useState('')
  const [reasons, setReasons] = useState({})
  const [busyId, setBusyId] = useState(null)

  const fetchQueue = useCallback(async () => {
    try {
      setLoading(true)
      setError('')
      const { data } = await getModerationComments({ status })
      setComments(data.comments || [])
    } catch (err) {
      setError(apiErrorMessage(err, 'Failed to load community moderation queue.'))
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    const timer = window.setTimeout(fetchQueue, 0)
    return () => window.clearTimeout(timer)
  }, [fetchQueue])

  const decide = async (commentId, decision) => {
    const reason = (reasons[commentId] || '').trim()
    if (decision === 'Remove' && !reason) {
      setActionError('Please give a reason before removing a comment - it is kept for the audit trail.')
      return
    }
    try {
      setBusyId(commentId)
      setActionError('')
      await moderateComment(commentId, decision, reason)
      await fetchQueue()
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Failed to record the moderation decision.'))
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section>
      <p className="dashboard-kicker">
        Community comments flagged by citizens or the automatic content check. Flagged comments stay visible until you decide.
      </p>

      <div className="filter-group">
        <select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Moderation status">
          <option value="Flagged">Awaiting review</option>
          <option value="Removed">Removed</option>
          <option value="Visible">Visible</option>
        </select>
      </div>

      {actionError && <p className="form-message error" role="alert">{actionError}</p>}

      {loading ? (
        <p className="page-state">Loading moderation queue...</p>
      ) : error ? (
        <p className="form-message error" role="alert">{error}</p>
      ) : comments.length === 0 ? (
        <div className="empty-state">
          <h2>Nothing to review</h2>
          <p>{status === 'Flagged' ? 'No community comments are waiting for a decision.' : 'No comments with this status.'}</p>
        </div>
      ) : (
        <div className="officer-complaint-list">
          {comments.map((comment) => (
            <article className="officer-card" key={comment.id}>
              <div className="officer-card-header">
                <div>
                  <span className="complaint-category">{comment.author.handle}</span>
                  {comment.moderation.flag_source && <span className="priority-tag priority-high">{comment.moderation.flag_source}</span>}
                  <p className="officer-meta">
                    Posted {formatDate(comment.created_at)} on{' '}
                    <Link className="text-link" to={`/community/issues/${comment.civic_issue_id}`}>civic issue #{comment.civic_issue_id}</Link>
                    {' '}&bull; user #{comment.author_user_id}
                  </p>
                </div>
              </div>
              <p className="officer-card-desc comment-body">{comment.content}</p>
              <div className="officer-ai-strip">
                {comment.moderation.flag_reason && <div><strong>Flag reason:</strong> {comment.moderation.flag_reason}</div>}
                {comment.moderation.flagged_at && <div><strong>Flagged:</strong> {formatDate(comment.moderation.flagged_at)}</div>}
                {comment.moderation.moderated_at && (
                  <div><strong>Decision:</strong> {formatDate(comment.moderation.moderated_at)} by staff #{comment.moderation.moderated_by}{comment.moderation.moderation_reason ? ` - ${comment.moderation.moderation_reason}` : ''}</div>
                )}
              </div>
              <div className="moderation-actions">
                {status !== 'Removed' && (
                  <input
                    type="text"
                    placeholder="Reason for removal (required)"
                    value={reasons[comment.id] || ''}
                    onChange={(e) => setReasons({ ...reasons, [comment.id]: e.target.value })}
                    aria-label="Reason for removal"
                  />
                )}
                {status !== 'Removed' && (
                  <button type="button" className="button button-outline-danger" disabled={busyId === comment.id} onClick={() => decide(comment.id, 'Remove')}>
                    Remove
                  </button>
                )}
                {status !== 'Visible' && (
                  <button type="button" className="button button-secondary" disabled={busyId === comment.id} onClick={() => decide(comment.id, 'Restore')}>
                    {status === 'Removed' ? 'Restore' : 'Keep visible'}
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
