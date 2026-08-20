import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../api'
import PendingEventCard from '../components/PendingEventCard'
import ResolvedEventRow from '../components/ResolvedEventRow'
import SegmentedControl from '../components/SegmentedControl'
import './CoveragePage.css'

const CONFIRMATION_TIMEOUT_MS = 6000

// Replaces the old separate Coverage / Pending / Ledger routes with one
// page: fetch GET /events once, filter the same list client-side by
// segment. "Needs Review" is the old Pending Review page's cards
// unchanged; "Resolved" is PRD Section 7 Screen E's chronological
// ledger (new -- the old /ledger route was always a placeholder).
function CoveragePage() {
  const [state, setState] = useState({ status: 'loading' })
  const [segment, setSegment] = useState('needs-review')
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
        setState({ status: 'ok', events })
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

      // Update the event in place rather than removing it -- it needs
      // to stay in the list so it correctly reappears under Resolved,
      // not disappear from the page entirely.
      setState((prev) => ({
        ...prev,
        events: prev.events.map((e) => (e.id === event.id ? body : e)),
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

  const events = state.status === 'ok' ? state.events : []
  // "Needs Review" == escalated and not yet resolved. decision alone
  // isn't enough: a manually-assigned escalation keeps
  // decision === "escalate" but resolved becomes true.
  const needsReview = events.filter((event) => event.decision === 'escalate' && !event.resolved)
  // "Resolved" == every resolved event, auto or manual -- PRD Section 7
  // Screen E's ledger, not just the escalations.
  const resolved = events.filter((event) => event.resolved)

  return (
    <div>
      <h1 className="page-heading">Coverage</h1>

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

      {state.status === 'loading' && <p>Loading events…</p>}

      {state.status === 'error' && (
        <p className="notice notice-error">Couldn't reach the API: {state.message}</p>
      )}

      {state.status === 'ok' && (
        <>
          <SegmentedControl
            value={segment}
            onChange={setSegment}
            options={[
              { value: 'needs-review', label: 'Needs Review', count: needsReview.length },
              { value: 'resolved', label: 'Resolved', count: resolved.length },
            ]}
          />

          {segment === 'needs-review' &&
            (needsReview.length === 0 ? (
              <p className="notice">No escalations awaiting review.</p>
            ) : (
              <div className="pending-list">
                {needsReview.map((event) => (
                  <PendingEventCard
                    key={event.id}
                    event={event}
                    assigning={assigning}
                    error={cardErrors[event.id]}
                    onAssign={(staffId, staffName) => handleAssign(event, staffId, staffName)}
                  />
                ))}
              </div>
            ))}

          {segment === 'resolved' &&
            (resolved.length === 0 ? (
              <p className="notice">No resolved events yet.</p>
            ) : (
              <div className="resolved-list">
                {resolved.map((event) => (
                  <ResolvedEventRow key={event.id} event={event} />
                ))}
              </div>
            ))}
        </>
      )}
    </div>
  )
}

export default CoveragePage
