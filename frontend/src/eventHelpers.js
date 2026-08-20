// Shared helpers for rendering an event (from GET /events / POST
// /absences / POST /events/{id}/assign -- all three return the same
// shape). Used by both the Needs Review cards and the Resolved list.

// BriefCandidate (the AI brief's ranked output) carries no name field --
// only staff_id/score/reasoning/warning -- and covered_by is likewise
// just a staff_id. Cross-reference the event's own eligible_candidates,
// which does have names, for display.
export function candidateName(event, staffId) {
  const match = event.eligible_candidates.find((c) => c.staff_id === staffId)
  return match ? match.name : staffId
}
