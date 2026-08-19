import { useEffect, useState } from 'react'

// Single source of truth for the API base URL -- see .env.example.
// Vite only exposes env vars prefixed VITE_ to client code.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL

function App() {
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
        setState({ status: 'ok', data })
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
    <main className="page">
      <h1>Coverage Copilot</h1>
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

      {state.status === 'ok' && (
        <pre className="schedule">{JSON.stringify(state.data, null, 2)}</pre>
      )}
    </main>
  )
}

export default App
