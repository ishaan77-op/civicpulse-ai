import { useCallback, useEffect, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import { deleteComment, editComment, getIssueComments, postIssueComment, reportComment } from '../services/communityservice.js'
import { relativeTime } from '../utils/community.js'
import { formatDateTime } from '../utils/formatDateTime.js'

const MAX_LENGTH = 1000

// Comment text is always rendered as a React text node - never as HTML -
// so markup a citizen types is displayed literally, not executed.
export default function CommunityComments({ issueId, onCountChange }) {
  const [comments, setComments] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [draft, setDraft] = useState('')
  const [posting, setPosting] = useState(false)
  const [formError, setFormError] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editDraft, setEditDraft] = useState('')
  const [notice, setNotice] = useState('')

  const load = useCallback(async (pageToLoad) => {
    try {
      setError('')
      const { data } = await getIssueComments(issueId, { page: pageToLoad })
      setComments((current) => (pageToLoad === 1 ? data.comments : [...current, ...data.comments]))
      setTotal(data.total)
      setHasMore(data.has_more)
      setPage(pageToLoad)
      onCountChange?.(data.total)
    } catch (err) {
      setError(apiErrorMessage(err, 'We could not load comments.'))
    } finally {
      setLoading(false)
    }
  }, [issueId, onCountChange])

  useEffect(() => {
    const timer = window.setTimeout(() => load(1), 0)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [issueId])

  const submit = async (event) => {
    event.preventDefault()
    const content = draft.trim()
    if (!content) { setFormError('Write something before posting.'); return }
    try {
      setPosting(true)
      setFormError('')
      await postIssueComment(issueId, content)
      setDraft('')
      await load(1)
    } catch (err) {
      setFormError(apiErrorMessage(err, 'Your comment could not be posted.'))
    } finally {
      setPosting(false)
    }
  }

  const saveEdit = async (commentId) => {
    const content = editDraft.trim()
    if (!content) return
    try {
      const { data } = await editComment(commentId, content)
      setComments((current) => current.map((c) => (c.id === commentId ? data.comment : c)))
      setEditingId(null)
    } catch (err) {
      setNotice(apiErrorMessage(err, 'Your edit could not be saved.'))
    }
  }

  const remove = async (commentId) => {
    try {
      await deleteComment(commentId)
      await load(1)
    } catch (err) {
      setNotice(apiErrorMessage(err, 'Your comment could not be deleted.'))
    }
  }

  const report = async (commentId) => {
    try {
      const { data } = await reportComment(commentId, 'Reported from the community thread')
      setNotice(data.message)
    } catch (err) {
      setNotice(apiErrorMessage(err, 'The report could not be sent.'))
    }
  }

  return (
    <section className="issue-panel" id="comments">
      <h2 className="issue-subhead">Community discussion <span className="issue-count">{total}</span></h2>
      <p className="signal-note">Share what you’ve seen on the ground. You appear only by your anonymous civic ID.</p>

      <form className="comment-form" onSubmit={submit}>
        <label htmlFor="comment-draft" className="visually-hidden">Add a comment</label>
        <textarea
          id="comment-draft"
          rows="3"
          maxLength={MAX_LENGTH}
          placeholder="e.g. Still present today - it got bigger after the rain."
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
        <div className="comment-form-row">
          <span className="comment-counter">{draft.length}/{MAX_LENGTH}</span>
          <button type="submit" className="button button-primary button-small" disabled={posting || !draft.trim()}>
            {posting ? 'Posting…' : 'Post comment'}
          </button>
        </div>
        {formError && <p className="form-message error" role="alert">{formError}</p>}
      </form>

      {notice && <p className="form-message success" role="status">{notice}</p>}

      {loading ? (
        <p className="page-state">Loading comments…</p>
      ) : error ? (
        <p className="form-message error" role="alert">{error}</p>
      ) : comments.length === 0 ? (
        <p className="signal-note">No comments yet. Be the first to share an update.</p>
      ) : (
        <ul className="comment-list">
          {comments.map((comment) => (
            <li key={comment.id} className={`comment ${comment.author.is_official ? 'comment-official' : ''}`}>
              <div className="comment-head">
                <span className="comment-author">
                  {comment.author.is_official ? '🏛️' : '👤'} {comment.author.handle}
                  {comment.author.is_you && <em> (you)</em>}
                </span>
                <time dateTime={comment.created_at} title={formatDateTime(comment.created_at)}>
                  {relativeTime(comment.created_at)}{comment.edited && ' · edited'}
                </time>
              </div>

              {editingId === comment.id ? (
                <div className="comment-edit">
                  <textarea rows="3" maxLength={MAX_LENGTH} value={editDraft} onChange={(e) => setEditDraft(e.target.value)} aria-label="Edit your comment" />
                  <div className="comment-tools">
                    <button type="button" onClick={() => saveEdit(comment.id)}>Save</button>
                    <button type="button" onClick={() => setEditingId(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <p className="comment-body">{comment.content}</p>
              )}

              {editingId !== comment.id && (
                <div className="comment-tools">
                  {comment.can_edit ? (
                    <>
                      <button type="button" onClick={() => { setEditingId(comment.id); setEditDraft(comment.content) }}>Edit</button>
                      <button type="button" onClick={() => remove(comment.id)}>Delete</button>
                    </>
                  ) : (
                    <button type="button" onClick={() => report(comment.id)}>Report</button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}

      {hasMore && (
        <button type="button" className="button button-secondary button-small" onClick={() => load(page + 1)}>
          Show older comments
        </button>
      )}
    </section>
  )
}
