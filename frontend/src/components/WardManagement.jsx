import { useCallback, useEffect, useRef, useState } from 'react'
import { apiErrorMessage } from '../services/api.js'
import {
  activateWard, assignOfficer, createWard, deactivateWard, endAssignment,
  listWardAssignments, listWards, updateWard,
} from '../services/wardservice.js'
import { formatDateTime } from '../utils/formatDateTime.js'
import { assignableOfficers, describeAssignmentState, validateWardForm } from '../utils/wards.js'

const EMPTY_FORM = { name: '', code: '', source: '' }

function WardForm({ initial, submitLabel, onSubmit, onCancel }) {
  const [form, setForm] = useState(initial)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const inFlight = useRef(false)

  const submit = async (event) => {
    event.preventDefault()
    if (inFlight.current) return
    const problem = validateWardForm(form)
    if (problem) { setError(problem); return }
    inFlight.current = true
    setBusy(true)
    setError('')
    try {
      await onSubmit({ name: form.name.trim(), code: form.code.trim() || null, source: form.source.trim() || null })
      if (!onCancel) setForm(EMPTY_FORM)
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not save the ward.'))
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const bind = (field) => ({ value: form[field], disabled: busy, onChange: (event) => setForm({ ...form, [field]: event.target.value }) })
  return (
    <form className="app-form ward-form" onSubmit={submit}>
      <label>Ward name<input type="text" {...bind('name')} /></label>
      <label>Official code (optional)<input type="text" {...bind('code')} /></label>
      <label>Source of this name/code (optional)<input type="text" placeholder="e.g. the circular or dataset it came from" {...bind('source')} /></label>
      {error && <p className="form-message error" role="alert">{error}</p>}
      <div className="resolution-actions">
        <button type="submit" className="button button-primary" disabled={busy}>{busy ? 'Saving…' : submitLabel}</button>
        {onCancel && <button type="button" className="button" disabled={busy} onClick={onCancel}>Cancel</button>}
      </div>
    </form>
  )
}

function AssignmentPanel({ ward, users, onChanged }) {
  const [state, setState] = useState({ status: 'loading', assignments: [], error: '' })
  const [officerId, setOfficerId] = useState('')
  const [reason, setReason] = useState('')
  const [endingId, setEndingId] = useState(null)
  const [endReason, setEndReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)

  const load = useCallback(async () => {
    try {
      const { data } = await listWardAssignments(ward.id)
      setState({ status: 'ready', assignments: data.assignments || [], error: '' })
    } catch (err) {
      setState((current) => ({ ...current, status: 'error', error: apiErrorMessage(err, 'Could not load the assignment history.') }))
    }
  }, [ward.id])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const run = async (action) => {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError('')
    try {
      await action()
      await load()
      await onChanged()
    } catch (err) {
      setError(apiErrorMessage(err, 'That change could not be saved.'))
      await load()
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const assign = (event) => {
    event.preventDefault()
    if (!officerId) { setError('Choose an Officer to assign.'); return }
    run(async () => {
      await assignOfficer(ward.id, Number(officerId), reason.trim())
      setOfficerId('')
      setReason('')
    })
  }

  const end = (assignmentId) => run(async () => {
    await endAssignment(ward.id, assignmentId, endReason.trim())
    setEndingId(null)
    setEndReason('')
  })

  if (state.status === 'loading') return <p className="page-state">Loading assignments…</p>
  if (state.status === 'error') {
    return (
      <div>
        <p className="form-message error" role="alert">{state.error}</p>
        <button type="button" className="button" onClick={load}>Try again</button>
      </div>
    )
  }

  const candidates = assignableOfficers(users, state.assignments)
  return (
    <div className="ward-assignments">
      <h3>Responsible Officers for {ward.name}</h3>
      <p className="resolution-muted">
        These are records of who is responsible. They do not yet limit which complaints an Officer can see or handle.
      </p>

      {ward.is_active ? (
        <form className="app-form ward-assign-form" onSubmit={assign}>
          <label>Officer
            <select value={officerId} disabled={busy} onChange={(event) => setOfficerId(event.target.value)}>
              <option value="">{candidates.length ? 'Choose an Officer' : 'No assignable Officers'}</option>
              {candidates.map((user) => <option key={user.id} value={user.id}>{user.name} ({user.email})</option>)}
            </select>
          </label>
          <label>Reason (optional)<input type="text" value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} /></label>
          <button type="submit" className="button button-primary" disabled={busy || !candidates.length}>{busy ? 'Saving…' : 'Assign Officer'}</button>
        </form>
      ) : (
        <p className="resolution-banner banner-stale">This ward is inactive. Reactivate it to assign an Officer.</p>
      )}
      {error && <p className="form-message error" role="alert">{error}</p>}

      {state.assignments.length === 0 ? (
        <p className="resolution-muted">No Officer has been assigned to this ward yet.</p>
      ) : (
        <ul className="resolution-log">
          {state.assignments.map((row) => (
            <li key={row.id}>
              <strong>{row.officer.name}</strong> <span className="resolution-muted">{row.officer.email}</span>
              <span className={`resolution-chip ${row.is_active ? 'chip-eligible' : ''}`}>{describeAssignmentState(row)}</span>
              {row.officer.role !== 'Officer' && <span className="resolution-chip chip-blocked">Now {row.officer.role}</span>}
              {row.officer.is_suspended && <span className="resolution-chip chip-blocked">Suspended</span>}
              <p>Assigned {formatDateTime(row.assigned_at)}{row.reason ? ` - ${row.reason}` : ''}</p>
              {!row.is_active && <p>Ended {formatDateTime(row.ended_at)}{row.end_reason ? ` - ${row.end_reason}` : ''}</p>}
              {row.is_active && (endingId === row.id ? (
                <div className="resolution-confirm">
                  <label>Reason for ending (optional)<input type="text" value={endReason} disabled={busy} onChange={(event) => setEndReason(event.target.value)} /></label>
                  <div className="resolution-actions">
                    <button type="button" className="button button-outline-danger" disabled={busy} onClick={() => end(row.id)}>{busy ? 'Ending…' : 'Confirm end assignment'}</button>
                    <button type="button" className="button" disabled={busy} onClick={() => setEndingId(null)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <button type="button" className="button" onClick={() => { setEndingId(row.id); setEndReason('') }}>End assignment</button>
              ))}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function WardManagement({ users }) {
  const [state, setState] = useState({ status: 'loading', wards: [], error: '' })
  const [editingId, setEditingId] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [actionError, setActionError] = useState('')
  const [togglingId, setTogglingId] = useState(null)

  const load = useCallback(async () => {
    try {
      const { data } = await listWards()
      setState({ status: 'ready', wards: data.wards || [], error: '' })
    } catch (err) {
      setState((current) => ({ ...current, status: 'error', error: apiErrorMessage(err, 'Could not load wards.') }))
    }
  }, [])

  useEffect(() => {
    const timer = window.setTimeout(load, 0)
    return () => window.clearTimeout(timer)
  }, [load])

  const toggleActive = async (ward) => {
    if (togglingId) return
    setTogglingId(ward.id)
    setActionError('')
    try {
      await (ward.is_active ? deactivateWard(ward.id) : activateWard(ward.id))
      await load()
    } catch (err) {
      setActionError(apiErrorMessage(err, 'Could not change the ward’s status.'))
    } finally {
      setTogglingId(null)
    }
  }

  if (state.status === 'loading') return <p className="page-state">Loading wards…</p>
  if (state.status === 'error') {
    return (
      <div>
        <p className="form-message error" role="alert">{state.error}</p>
        <button type="button" className="button" onClick={load}>Try again</button>
      </div>
    )
  }

  const selected = state.wards.find((ward) => ward.id === selectedId) || null
  return (
    <section className="ward-management">
      <p className="resolution-kicker">
        Add the wards your municipality officially defines, and record which Officers are responsible for each.
        Nothing here is pre-filled: names and codes must come from an official source. Deactivating a ward keeps all of its history.
      </p>

      <h2>Add a ward</h2>
      <WardForm
        initial={EMPTY_FORM}
        submitLabel="Add ward"
        onSubmit={async (values) => { await createWard(values); await load() }}
      />

      {actionError && <p className="form-message error" role="alert">{actionError}</p>}

      <h2>Wards ({state.wards.length})</h2>
      {state.wards.length === 0 ? (
        <div className="empty-state">
          <h2>No wards recorded yet</h2>
          <p>Add the first ward above once you have the official list.</p>
        </div>
      ) : (
        <div className="officer-complaint-list">
          {state.wards.map((ward) => (
            <article className="officer-card" key={ward.id}>
              {editingId === ward.id ? (
                <WardForm
                  initial={{ name: ward.name, code: ward.code || '', source: ward.source || '' }}
                  submitLabel="Save changes"
                  onSubmit={async (values) => { await updateWard(ward.id, values); setEditingId(null); await load() }}
                  onCancel={() => setEditingId(null)}
                />
              ) : (
                <div className="officer-card-header">
                  <div>
                    {ward.code && <span className="complaint-category">{ward.code}</span>}
                    <span className={`resolution-chip ${ward.is_active ? 'chip-eligible' : 'chip-excluded'}`}>{ward.is_active ? 'Active' : 'Inactive'}</span>
                    <h2>{ward.name}</h2>
                    <p className="officer-meta">
                      {ward.active_assignment_count} active Officer{ward.active_assignment_count === 1 ? '' : 's'}
                      {ward.source ? ` • Source: ${ward.source}` : ' • No source recorded'}
                    </p>
                  </div>
                  <div className="status-action-box">
                    <button type="button" className="button" onClick={() => setEditingId(ward.id)}>Edit</button>
                    <button type="button" className="button" aria-expanded={selectedId === ward.id}
                      onClick={() => setSelectedId(selectedId === ward.id ? null : ward.id)}>
                      {selectedId === ward.id ? 'Hide assignments' : 'Assignments'}
                    </button>
                    <button type="button" className={`button ${ward.is_active ? 'button-outline-danger' : ''}`}
                      disabled={togglingId === ward.id} onClick={() => toggleActive(ward)}>
                      {ward.is_active ? 'Deactivate' : 'Reactivate'}
                    </button>
                  </div>
                </div>
              )}
              {selected?.id === ward.id && editingId !== ward.id && (
                <AssignmentPanel ward={ward} users={users} onChanged={load} />
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
