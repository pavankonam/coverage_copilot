import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layout/AppShell'
import CoveragePage from './pages/CoveragePage'
import SchedulePage from './pages/SchedulePage'

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/schedule" replace />} />
        <Route path="schedule" element={<SchedulePage />} />
        <Route path="coverage" element={<CoveragePage />} />
        {/* Old /upload, /pending, /ledger routes are gone -- send any
            stale link (or typo) back to the default route rather than
            rendering nothing. */}
        <Route path="*" element={<Navigate to="/schedule" replace />} />
      </Route>
    </Routes>
  )
}

export default App
