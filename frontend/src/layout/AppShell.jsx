import { NavLink, Outlet } from 'react-router-dom'
import './AppShell.css'

// PRD Section 7 screens A-E, in that order. Routed as real pages
// (react-router), not scrolled sections.
const NAV_ITEMS = [
  { to: '/upload', label: 'Upload' },
  { to: '/schedule', label: 'Schedule' },
  { to: '/coverage', label: 'Coverage' },
  { to: '/pending', label: 'Pending' },
  { to: '/ledger', label: 'Ledger' },
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
