import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './layout/AppShell'
import CoveragePage from './pages/CoveragePage'
import LedgerPage from './pages/LedgerPage'
import PendingPage from './pages/PendingPage'
import SchedulePage from './pages/SchedulePage'
import UploadPage from './pages/UploadPage'

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Navigate to="/upload" replace />} />
        <Route path="upload" element={<UploadPage />} />
        <Route path="schedule" element={<SchedulePage />} />
        <Route path="coverage" element={<CoveragePage />} />
        <Route path="pending" element={<PendingPage />} />
        <Route path="ledger" element={<LedgerPage />} />
      </Route>
    </Routes>
  )
}

export default App
