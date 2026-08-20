import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../api'
import PendingEventCard from '../components/PendingEventCard'
import './PendingPage.css'

const CONFIRMATION_TIMEOUT_MS = 6000

function PendingPage() {
  const [state, setState] = useState({ status: 'loading' })
  const [assigning, setAssigning] = useState(null) // {eventId, staffId} | null
  const [cardErrors, setCardErrors] = useState({}) // {[eventId]: message}
  const [confirmation, setConfirmation] = useState(null) // string | null
  const confirmTimerRef = useRef(null)

  const loadEvents = useCallback(() => {
    return fetch(`${API_BASE_URL}/events`)
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Unexpected response: ${response.status}`)
        }
        const events = await response.json()
        // "Pending" == escalated and not yet resolved. decision alone
        // isn't enough: a manually-assigned escalation keeps
        // decision === "escalate" but resolved becomes true.
        const pending = events.filter((event) => event.decision === 'escalate' && !event.resolved)
        setState({ status: 'ok', events: pending })
      })
      .catch((error) => {
        setState({ status: 'error', message: error.message })
      })
  }, [])

  useEffect(() => {
    loadEvents()
  }, [loadEvents])

  useEffect(() => {
    return () => clearTimeout(confirmTimerRef.current)
  }, [])

  async function handleAssign(event, staffId, staffName) {
    setAssigning({ eventId: event.id, staffId })
    setCardErrors((prev) => ({ ...prev, [event.id]: null }))

    try {
      const response = await fetch(`${API_BASE_URL}/events/${event.id}/assign`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ staff_id: staffId }),
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

      setState((prev) => ({
        ...prev,
        events: prev.events.filter((e) => e.id !== event.id),
      }))

      clearTimeout(confirmTimerRef.current)
      setConfirmation(`Assigned ${staffName} to cover ${event.staff_name}, ${event.day}.`)
      confirmTimerRef.current = setTimeout(() => setConfirmation(null), CONFIRMATION_TIMEOUT_MS)
    } catch (err) {
      setCardErrors((prev) => ({
        ...prev,
        [event.id]:
          err instanceof TypeError
            ? "Couldn't reach the API. Check your connection and try again."
            : err.message,
      }))
    } finally {
      setAssigning(null)
    }
  }

  return (
    <div>
      <h1 className="page-heading">Pending Review</h1>

      {confirmation && (
        <div className="banner" role="status">
          <span>{confirmation}</span>
          <button
            type="button"
            className="banner-dismiss"
            aria-label="Dismiss"
            onClick={() => setConfirmation(null)}
          >
            ×
          </button>
        </div>
      )}

      {state.status === 'loading' && <p>Loading pending escalations…</p>}

      {state.status === 'error' && (
        <p className="notice notice-error">
          Couldn't reach the API: {state.message}
        </p>
      )}

      {state.status === 'ok' && state.events.length === 0 && (
        <p className="notice">No escalations awaiting review.</p>
      )}

      {state.status === 'ok' && state.events.length > 0 && (
        <div className="pending-list">
          {state.events.map((event) => (
            <PendingEventCard
              key={event.id}
              event={event}
              assigning={assigning}
              error={cardErrors[event.id]}
              onAssign={(staffId, staffName) => handleAssign(event, staffId, staffName)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default PendingPage
