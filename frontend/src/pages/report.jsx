import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import AppShell from '../components/appshell.jsx'
import MapPicker from '../components/MapPicker.jsx'
import CameraCapture from '../components/CameraCapture.jsx'
import { apiErrorMessage } from '../services/api.js'
import { createComplaint } from '../services/complaintservice.js'

export default function Report() {
  const [form, setForm] = useState({
    title: '',
    description: '',
    location: null,
    image: null,
  })

  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  const handleLocationSelect = (selection) => {
    if (!selection) {
      setForm((current) => ({
        ...current,
        location: null,
      }))
      return
    }

    setForm((current) => ({
      ...current,
      location: selection,
    }))
  }

  const locationConfirmed = Boolean(form.location?.confirmed)

  const submit = async (event) => {
    event.preventDefault()
    setError('')

    if (!locationConfirmed) {
      setError(
        'Please select your complaint location on the map and press "Confirm Location".',
      )
      return
    }

    if (!form.image) {
      setError('Please capture a photo of the issue with your camera.')
      return
    }

    setSubmitting(true)

    try {
      const payload = new FormData()

      payload.append('title', form.title)
      payload.append('description', form.description)
      payload.append('latitude', form.location.latitude)
      payload.append('longitude', form.location.longitude)

      if (form.location.address) {
        payload.append('address', form.location.address)
      }

      payload.append('image', form.image)

      await createComplaint(payload)

      navigate('/complaints', { replace: true })
    } catch (requestError) {
      setError(
        apiErrorMessage(
          requestError,
          'We could not submit this report.',
        ),
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AppShell eyebrow="New report" title="Report a civic issue">
      <section className="form-layout">
        <div>
          <h2>Share what you have noticed.</h2>

          <p>
            Clear details and a photo can help the appropriate civic
            team understand the issue and what needs attention.
          </p>
        </div>

        <form className="app-form" onSubmit={submit}>
          <label>
            Issue title
            <input
              value={form.title}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  title: event.target.value,
                }))
              }
              required
            />
          </label>

          <label>
            Description
            <textarea
              rows="6"
              value={form.description}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  description: event.target.value,
                }))
              }
              required
            />
          </label>

          <MapPicker onLocationSelect={handleLocationSelect} />

          {!locationConfirmed && (
            <p className="form-message">
              Select a point on the map, then press "Confirm Location"
              before submitting.
            </p>
          )}

          <label>
            Photo of the issue (camera only)
            <CameraCapture
              onCapture={(file) =>
                setForm((current) => ({
                  ...current,
                  image: file,
                }))
              }
            />
          </label>

          {error && (
            <p className="form-message error" role="alert">
              {error}
            </p>
          )}

          <button
            className="button button-primary"
            disabled={submitting || !locationConfirmed || !form.image}
          >
            {submitting ? 'Submitting…' : 'Submit report'}
            <span aria-hidden="true">→</span>
          </button>
        </form>
      </section>
    </AppShell>
  )
}