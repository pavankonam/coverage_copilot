import { RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { API_BASE_URL } from '../api'
import AbsenceReportModal from '../components/AbsenceReportModal'
import DeptTag from '../components/DeptTag'
import RosterUpload from '../components/RosterUpload'
import { ICON_SIZE, ICON_STROKE_WIDTH } from '../iconStyle'
import './SchedulePage.css'

// Mirrors src/data_layer.py's DAY_COLUMNS.
const DAY_COLUMNS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

const NOTICE_TIMEOUT_MS = 7000

function SchedulePage() {
  const [state, setState] = useState({ status: 'loading' })
  const [reportTarget, setReportTarget] = useState(null) // {staffId, staffName, day, shiftCode} | null
  const [notice, setNotice] = useState(null) // string | null
  // User-triggered replacement of an already-loaded roster, as opposed
  // to the 'no-roster' status that embeds the same upload flow
  // automatically. Both end up rendering the identical <RosterUpload>
  // below -- this only decides whether that happens.
  const [isReplacingRoster, setIsReplacingRoster] = useState(false)
  const noticeTimerRef = useRef(null)

  const loadSchedule = useCallback(() => {
    // No "reset to loading" here: the initial mount already starts in
    // 'loading' state, and a post-submit refetch should update the grid
    // in place rather than flashing back to a loading spinner. Returns
    // the parsed data (or null) so callers can act on it, e.g. deriving
    // an upload summary without a second fetch.
    return fetch(`${API_BASE_URL}/schedule`)
      .then(async (response) => {
        if (response.status === 400) {
          // No roster has been POSTed to the backend yet -- expected,
          // not an error. The empty state below handles this by
          // embedding the upload flow directly, not routing away.
          setState({ status: 'no-roster' })
          return null
        }
        if (!response.ok) {
          throw new Error(`Unexpected response: ${response.status}`)
        }

        const data = await response.json()
        setState({ status: 'ok', original: data.original, effective: data.effective })
        return data
      })
      .catch((error) => {
        setState({ status: 'error', message: error.message })
        return null
      })
  }, [])

  useEffect(() => {
    loadSchedule()
  }, [loadSchedule])

  useEffect(() => {
    return () => clearTimeout(noticeTimerRef.current)
  }, [])

  function showNotice(message) {
    clearTimeout(noticeTimerRef.current)
    setNotice(message)
    noticeTimerRef.current = setTimeout(() => setNotice(null), NOTICE_TIMEOUT_MS)
  }

  function handleReportAbsence(target) {
    setNotice(null)
    setReportTarget(target)
  }

  function handleResolved(data) {
    setReportTarget(null)
    loadSchedule() // reflect any auto-resolved change immediately

    // decision == "auto" is already visible as a grid change (the
    // brass changed-cell dot) -- nothing else needed there. decision
    // == "escalate" doesn't touch the grid, so without this the
    // manager would see nothing happen at all.
    if (data?.decision === 'escalate') {
      showNotice(`Escalated for review — ${data.note} See Coverage to assign.`)
    }
  }

  async function handleUploaded(body) {
    setIsReplacingRoster(false)
    const data = await loadSchedule() // 'no-roster' (or replacing) -> 'ok', board appears in place
    if (data) {
      const departments = [...new Set(data.original.map((row) => row.department))].sort()
      const departmentSummary =
        departments.length > 0
          ? ` across ${departments.length} department${departments.length === 1 ? '' : 's'}: ${departments.join(', ')}`
          : ''
      showNotice(`Roster loaded — ${body.staff_count} staff${departmentSummary}.`)
    }
  }

  return (
    <div>
      <h1 className="page-heading">Schedule</h1>

      {notice && (
        <div className="banner" role="status">
          <span>{notice}</span>
          <button
            type="button"
            className="banner-dismiss"
            aria-label="Dismiss"
            onClick={() => setNotice(null)}
          >
            ×
          </button>
        </div>
      )}

      {state.status === 'loading' && <p>Loading schedule…</p>}

      {state.status === 'error' && (
        <p className="notice notice-error">
          Couldn't reach the API: {state.message}
        </p>
      )}

      {state.status === 'ok' && !isReplacingRoster && (
        <button
          type="button"
          className="btn btn-ghost replace-roster-button"
          onClick={() => setIsReplacingRoster(true)}
        >
          <RefreshCw size={ICON_SIZE.sm} strokeWidth={ICON_STROKE_WIDTH} aria-hidden="true" />
          Replace roster
        </button>
      )}

      {(state.status === 'no-roster' || (state.status === 'ok' && isReplacingRoster)) && (
        <RosterUpload
          onUploaded={handleUploaded}
          onCancel={isReplacingRoster ? () => setIsReplacingRoster(false) : undefined}
        />
      )}

      {state.status === 'ok' && !isReplacingRoster && state.original.length === 0 && (
        <p className="notice">The loaded roster has no staff.</p>
      )}

      {state.status === 'ok' && !isReplacingRoster && state.original.length > 0 && (
        <DutyBoard
          original={state.original}
          effective={state.effective}
          onReportAbsence={handleReportAbsence}
        />
      )}

      {reportTarget && (
        <AbsenceReportModal
          staffId={reportTarget.staffId}
          staffName={reportTarget.staffName}
          day={reportTarget.day}
          shiftCode={reportTarget.shiftCode}
          onClose={() => setReportTarget(null)}
          onResolved={handleResolved}
        />
      )}
    </div>
  )
}

function DutyBoard({ original, effective, onReportAbsence }) {
  const effectiveById = new Map(effective.map((row) => [row.staff_id, row]))

  return (
    <div className="duty-board-wrap">
      <table className="duty-board">
        <thead>
          <tr>
            <th scope="col" className="staff-col">
              Staff
            </th>
            {DAY_COLUMNS.map((day) => (
              <th scope="col" key={day}>
                {day}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {original.map((row) => {
            const effectiveRow = effectiveById.get(row.staff_id)
            return (
              <tr key={row.staff_id}>
                <th scope="row" className="staff-col">
                  <div className="staff-name-row">
                    <span className="staff-name">{row.name}</span>
                    <DeptTag department={row.department} />
                  </div>
                  <span className="staff-id">{row.staff_id}</span>
                </th>
                {DAY_COLUMNS.map((day) => {
                  const originalCode = row[day]
                  const effectiveCode = effectiveRow ? effectiveRow[day] : originalCode
                  const changed = effectiveCode !== originalCode
                  const isWorkingShift = effectiveCode !== 'OFF'

                  return (
                    <td
                      key={day}
                      className="shift-cell"
                      title={changed ? `Originally ${originalCode}` : undefined}
                    >
                      {isWorkingShift ? (
                        <button
                          type="button"
                          className="shift-cell-button"
                          aria-label={`Report absence for ${row.name}, ${day} (${effectiveCode})`}
                          onClick={() =>
                            onReportAbsence({
                              staffId: row.staff_id,
                              staffName: row.name,
                              day,
                              shiftCode: effectiveCode,
                            })
                          }
                        >
                          <span className="shift-code">{effectiveCode}</span>
                        </button>
                      ) : (
                        <span className="shift-cell-static">
                          <span className="shift-code shift-code-off">OFF</span>
                        </span>
                      )}
                      {changed && (
                        <>
                          <span className="changed-dot" aria-hidden="true" />
                          <span className="sr-only"> (changed from {originalCode})</span>
                        </>
                      )}
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default SchedulePage
