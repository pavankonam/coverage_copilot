import { useEffect, useId, useRef, useState } from 'react'
import { API_BASE_URL } from '../api'
import './AbsenceReportModal.css'

// Reports one absence (POST /absences) for a working-shift cell clicked
// on the Schedule duty board. Stays open and shows a clear error on
// failure (network error or non-2xx) rather than closing silently;
// only calls onResolved (which closes it) on success.
function AbsenceReportModal({ staffId, staffName, day, shiftCode, onClose, onResolved }) {
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const textareaRef = useRef(null)
  const headingId = useId()

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  useEffect(() => {
    function handleKeyDown(event) {
      if (event.key === 'Escape' && !submitting) {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose, submitting])

  async function handleSubmit(event) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/absences`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          staff_id: staffId,
          day,
          reason: reason.trim() || null,
        }),
      })

      let body = null
      try {
        body = await response.json()
      } catch {
        // No JSON body -- fall back to a status-based message below.
      }

      if (!response.ok) {
        throw new Error(body?.detail ?? `Request failed (${response.status})`)
      }

      onResolved(body)
    } catch (err) {
      setError(
        err instanceof TypeError
          ? "Couldn't reach the API. Check your connection and try again."
          : err.message,
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      className="modal-scrim"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !submitting) onClose()
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby={headingId}>
        <h2 id={headingId} className="modal-heading">
          Report absence
        </h2>
        <p className="modal-subheading">
          {staffName} — {day} ({shiftCode})
        </p>

        <form onSubmit={handleSubmit}>
          <label className="modal-label" htmlFor="absence-reason">
            Reason
          </label>
          <textarea
            id="absence-reason"
            ref={textareaRef}
            className="modal-textarea"
            placeholder="e.g. Called in sick"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            disabled={submitting}
          />

          {error && (
            <p className="modal-error" role="alert">
              {error}
            </p>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="modal-button-ghost"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </button>
            <button type="submit" className="modal-button-primary" disabled={submitting}>
              {submitting ? 'Reporting…' : 'Report Absence'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default AbsenceReportModal
