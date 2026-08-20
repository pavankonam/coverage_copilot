import DeptTag from './DeptTag'
import './PendingEventCard.css'

function candidateName(event, staffId) {
  const match = event.eligible_candidates.find((c) => c.staff_id === staffId)
  return match ? match.name : staffId
}

function PendingEventCard({ event, assigning, error, onAssign }) {
  const isCardAssigning = assigning?.eventId === event.id

  return (
    <article className="pending-card">
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

      <p className="pending-card-note">{event.note}</p>

      {event.mode === 'single' && (
        <SingleCandidate
          candidate={event.eligible_candidates[0]}
          isAssigning={isCardAssigning}
          disabled={isCardAssigning}
          onAssign={onAssign}
        />
      )}

      {event.mode === 'multi' && (
        <RankedCandidates
          event={event}
          assigning={isCardAssigning ? assigning : null}
          onAssign={onAssign}
        />
      )}

      {event.mode === 'none' && <NoCandidates />}

      {error && (
        <p className="pending-card-error" role="alert">
          {error}
        </p>
      )}
    </article>
  )
}

function SingleCandidate({ candidate, isAssigning, disabled, onAssign }) {
  return (
    <div className="candidate-row">
      <div className="candidate-info">
        <div className="candidate-info-who">
          <span className="candidate-name">{candidate.name}</span>
          <span className="staff-id">{candidate.staff_id}</span>
        </div>
        <div className="candidate-facts">
          <span className="fact-badge">
            {candidate.same_department ? 'Same department' : 'Different department'}
          </span>
          <span className="fact-badge fact-badge-mono">{candidate.hours_scheduled}h scheduled</span>
          {candidate.would_overtime && (
            <span className="fact-badge fact-badge-warning">Would exceed weekly cap</span>
          )}
        </div>
      </div>
      <button
        type="button"
        className="btn btn-primary assign-button"
        disabled={disabled}
        onClick={() => onAssign(candidate.staff_id, candidate.name)}
      >
        {isAssigning ? 'Assigning…' : 'Assign'}
      </button>
    </div>
  )
}

function RankedCandidates({ event, assigning, onAssign }) {
  // get_coverage_brief() runs synchronously inside POST /absences, so by
  // the time an event exists at all its brief has already either
  // succeeded (candidates present) or failed (candidates stays null --
  // see PRD Section 8 / CoverageBriefError). This loading state covers
  // that transient window on this page's own initial fetch, and reads
  // honestly rather than promising a "still generating" retry that
  // isn't actually wired up to anything.
  if (event.candidates == null) {
    return (
      <div className="ai-section ai-section-loading">
        <AiSectionLabel />
        <p className="ai-loading-text">Ranked recommendations aren't available for this event.</p>
      </div>
    )
  }

  return (
    <div className="ai-section">
      <AiSectionLabel />
      <ul className="ranked-list">
        {event.candidates.map((candidate) => {
          const isThisAssigning = assigning?.staffId === candidate.staff_id
          return (
            <li key={candidate.staff_id} className="ranked-item">
              <div className="ranked-item-header">
                <span className="ranked-score" aria-hidden="true">
                  {Math.round(candidate.score)}
                </span>
                <div className="ranked-item-who">
                  <span className="candidate-name">{candidateName(event, candidate.staff_id)}</span>
                  <span className="staff-id">{candidate.staff_id}</span>
                </div>
                <button
                  type="button"
                  className="btn btn-primary assign-button"
                  disabled={assigning != null}
                  onClick={() => onAssign(candidate.staff_id, candidateName(event, candidate.staff_id))}
                >
                  {isThisAssigning ? 'Assigning…' : 'Assign'}
                </button>
              </div>
              <p className="ranked-reasoning">
                <span className="sr-only">Score {Math.round(candidate.score)} out of 100. </span>
                {candidate.reasoning}
              </p>
              {candidate.warning && <p className="ranked-warning">{candidate.warning}</p>}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function AiSectionLabel() {
  return (
    <div className="ai-section-label">
      <span aria-hidden="true">✦</span> Ranked by AI
    </div>
  )
}

function NoCandidates() {
  return (
    <div className="none-explanation">
      <p>No eligible candidates were found for this shift.</p>
      <p className="none-explanation-manual">
        This needs manual handling outside the system — there is no automatic match to assign.
      </p>
    </div>
  )
}

export default PendingEventCard
