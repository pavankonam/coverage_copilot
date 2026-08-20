import { useEffect, useState } from 'react'
import './SchedulePage.css'

// Single source of truth for the API base URL -- see .env.example.
// Vite only exposes env vars prefixed VITE_ to client code.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

// Mirrors src/data_layer.py's DAY_COLUMNS.
const DAY_COLUMNS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

// Mirrors src/data_layer.py's DEFAULT_DEPARTMENTS and the four
// department tag colors defined in styles/tokens.css.
const DEPARTMENT_COLOR_VAR = {
  'Front Desk': '--color-dept-front-desk',
  Housekeeping: '--color-dept-housekeeping',
  'F&B': '--color-dept-fb',
  Concierge: '--color-dept-concierge',
}

function departmentColorVar(department) {
  return DEPARTMENT_COLOR_VAR[department] ?? '--color-text-muted'
}

function SchedulePage() {
  const [state, setState] = useState({ status: 'loading' })

  useEffect(() => {
    let cancelled = false

    fetch(`${API_BASE_URL}/schedule`)
      .then(async (response) => {
        if (cancelled) return

        if (response.status === 400) {
          // No roster has been POSTed to the backend yet -- expected,
          // not an error.
          setState({ status: 'no-roster' })
          return
        }
        if (!response.ok) {
          throw new Error(`Unexpected response: ${response.status}`)
        }

        const data = await response.json()
        setState({ status: 'ok', original: data.original, effective: data.effective })
      })
      .catch((error) => {
        if (!cancelled) {
          setState({ status: 'error', message: error.message })
        }
      })

    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div>
      <h1 className="page-heading">Schedule</h1>
      <p className="api-base">
        API: <code>{API_BASE_URL}</code>
      </p>

      {state.status === 'loading' && <p>Loading schedule…</p>}

      {state.status === 'no-roster' && (
        <p className="notice">No roster loaded yet.</p>
      )}

      {state.status === 'error' && (
        <p className="notice notice-error">
          Couldn't reach the API: {state.message}
        </p>
      )}

      {state.status === 'ok' && state.original.length === 0 && (
        <p className="notice">The loaded roster has no staff.</p>
      )}

      {state.status === 'ok' && state.original.length > 0 && (
        <DutyBoard original={state.original} effective={state.effective} />
      )}
    </div>
  )
}

function DutyBoard({ original, effective }) {
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
                    <span
                      className="dept-tag"
                      style={{ '--dept-color': `var(${departmentColorVar(row.department)})` }}
                    >
                      {row.department}
                    </span>
                  </div>
                  <span className="staff-id">{row.staff_id}</span>
                </th>
                {DAY_COLUMNS.map((day) => {
                  const originalCode = row[day]
                  const effectiveCode = effectiveRow ? effectiveRow[day] : originalCode
                  const changed = effectiveCode !== originalCode
                  return (
                    <td
                      key={day}
                      className="shift-cell"
                      title={changed ? `Originally ${originalCode}` : undefined}
                    >
                      <span
                        className={
                          'shift-code' + (effectiveCode === 'OFF' ? ' shift-code-off' : '')
                        }
                      >
                        {effectiveCode}
                      </span>
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
