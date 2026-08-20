import { NavLink, Outlet } from 'react-router-dom'
import './AppShell.css'

// Two routed pages. Schedule absorbs the old Upload flow (shown inline
// when no roster is loaded yet); Coverage absorbs the old Pending and
// Ledger pages behind a segmented control -- see CoveragePage.jsx. This
// is a deliberate departure from PRD Section 7's five separate screens
// (A-E), not an oversight.
const NAV_ITEMS = [
  { to: '/schedule', label: 'Schedule' },
  { to: '/coverage', label: 'Coverage' },
]

function AppShell() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-wordmark">Coverage Copilot</div>
        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                'sidebar-link' + (isActive ? ' sidebar-link-active' : '')
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}

export default AppShell
