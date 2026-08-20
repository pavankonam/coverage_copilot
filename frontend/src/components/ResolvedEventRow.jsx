import { candidateName } from '../eventHelpers'
import DeptTag from './DeptTag'
import './ResolvedEventRow.css'

// One row in the Resolved list -- PRD Section 7 Screen E: "chronological
// log of resolved events, each tagged with its resolution mode
// (auto/manual) and the reason for absence." Covers both decision ==
// "auto" (always resolved) and decision == "escalate" events a manager
// has since assigned (resolved == true either way).
function ResolvedEventRow({ event }) {
  const coveredByName = event.covered_by ? candidateName(event, event.covered_by) : null

  return (
    <article className="resolved-row">
      <header className="pending-card-header">
        <div className="pending-card-who">
          <span className="staff-name">{event.staff_name}</span>
          <DeptTag department={event.department} />
        </div>
        <div className="pending-card-meta">
          <span className="staff-id">{event.staff_id}</span>
          <span className="pending-card-day">{event.day}</span>
        </div>
      </header>

      {event.reason && <p className="pending-card-reason">"{event.reason}"</p>}

      <div className="resolved-row-footer">
        <ResolutionBadge resolution={event.resolution} />
        {coveredByName && (
          <span className="resolved-covered-by">
            Covered by {coveredByName} ({event.covered_by})
          </span>
        )}
      </div>
    </article>
  )
}

function ResolutionBadge({ resolution }) {
  // Distinct at a glance, per PRD Section 7 Screen C's badge language:
  // filled brass for a system auto-resolve, an outlined pill for a
  // human decision.
  if (resolution === 'auto') {
    return <span className="resolution-badge resolution-badge-auto">Auto</span>
  }
  return <span className="resolution-badge resolution-badge-manual">Approved by you</span>
}

export default ResolvedEventRow
