"""REST API layer for Coverage Copilot's absence-coverage classification.

This is the app's backend, per coverage-copilot-prd.md Section 9 (Python,
FastAPI, pandas, the Anthropic SDK -- no Streamlit). A separate React
frontend is planned as a later step. Keep this module a thin wrapper over
the existing, already-correct classification/brief logic in
src/classification.py and src/coverage_brief.py, not a place to add new
rules -- those two modules (plus src/data_layer.py) are unmodified here.

See PRD Section 12 for the full description of this module's surface,
including the "effective schedule" concept, which is new and not part of
the original v1 scope in Sections 1-11.

Endpoints:
- POST /roster                    load + validate a roster CSV
- POST /absences                  report and classify an absence
- GET  /events                    every reported absence, oldest first
- GET  /schedule                  original schedule vs. effective schedule
- POST /events/{event_id}/assign  manually resolve a pending escalation

Per PRD Section 8, the Anthropic API is called in exactly one path --
escalate-multi -- and nowhere else: when classify_absence lands on
mode == "multi", POST /absences immediately calls
src.coverage_brief.get_coverage_brief and includes the ranked candidates
in the same response, rather than returning the bare classification and
making the caller fetch the brief separately.
"""

from __future__ import annotations

import dataclasses
import io
import json
import uuid
from dataclasses import dataclass

import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from src.classification import Candidate, classify_absence
from src.coverage_brief import (
    AbsenceContext,
    BriefCandidate,
    CoverageBriefError,
    get_coverage_brief,
)
from src.data_layer import DAY_COLUMNS, load_and_validate_roster

app = FastAPI(title="Coverage Copilot API")

# --- In-memory state ------------------------------------------------------
# No persistent DB (PRD Section 3 non-goal) -- one roster, one effective
# schedule, one event list, held in module state. Not thread-safe / not
# multi-tenant -- fine for v1's single-shared-manager-view scope.

_original_roster: pd.DataFrame | None = None
_effective_schedule: pd.DataFrame | None = None
_events: list["AbsenceEvent"] = []


@dataclass
class AbsenceEvent:
    """One reported absence: its classification and its resolution state.

    Unlike ClassificationResult (frozen, a pure function of roster/staff_id
    /day), this is mutated in place as a pending escalation gets manually
    resolved -- see assign_event().
    """

    id: str
    staff_id: str
    staff_name: str
    department: str
    day: str
    reason: str | None
    decision: str  # "auto" | "escalate"
    mode: str  # "auto" | "none" | "single" | "multi"
    note: str
    eligible_candidates: list[Candidate]
    clean_matches: list[Candidate]
    resolved: bool = False
    resolution: str | None = None  # "auto" | "manual" | None while pending
    covered_by: str | None = None
    candidates: list[BriefCandidate] | None = None  # cached AI brief, multi-mode only


def set_roster(df: pd.DataFrame) -> None:
    """Set the current roster.

    This is the baseline the effective schedule is (re)initialized from --
    and, from that point on, classify_absence evaluates every absence
    against the *effective* schedule, not this original one (PRD Section
    12). Resets the effective schedule and the event list, since events
    and coverage already recorded against a previous roster no longer
    correspond to this one.
    """
    global _original_roster, _effective_schedule, _events
    _original_roster = df
    _effective_schedule = df.copy()
    _events = []


def get_effective_schedule() -> pd.DataFrame:
    """FastAPI dependency: the current effective schedule, or a 400.

    This is what classify_absence evaluates against (PRD Section 12) --
    eligibility and overtime math reflect anyone already covering another
    shift, not just the original upload.
    """
    if _effective_schedule is None:
        raise HTTPException(
            status_code=400,
            detail="No roster loaded. Load a roster before reporting an absence.",
        )
    return _effective_schedule


def get_anthropic_client():
    """FastAPI dependency for the Anthropic client used by /absences.

    Defaults to None so get_coverage_brief() builds its own client from
    the resolved API key (production behavior). Tests override this
    dependency with a mock client -- see tests/test_api.py.
    """
    return None


class AbsenceRequest(BaseModel):
    staff_id: str
    day: str
    reason: str | None = None


class AssignRequest(BaseModel):
    staff_id: str


def _candidate_dict(candidate: Candidate) -> dict:
    return dataclasses.asdict(candidate)


def _brief_candidate_dict(candidate: BriefCandidate) -> dict:
    return dataclasses.asdict(candidate)


def _df_records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe records for a roster/schedule DataFrame.

    Goes through DataFrame.to_json rather than to_dict: to_dict leaves
    values exactly as pandas stores them -- numpy scalar types (e.g.
    numpy.int64 in the hour columns) and NaN (e.g. an empty
    unavailable_days cell) -- neither of which is directly JSON-safe the
    way a plain Python int/None is. to_json handles both correctly (NaN
    becomes JSON null).
    """
    return json.loads(df.to_json(orient="records"))


def _parse_unavailable_days(value) -> set[str]:
    """Parse an unavailable_days cell into a set of day names.

    Mirrors classification._parse_unavailable_days's parsing rules
    exactly (comma-separated, blanks/NaN -> empty set), reimplemented
    here rather than imported so this module doesn't reach into
    classification.py's private helpers -- classification.py stays
    untouched and unimported-from for this.
    """
    if pd.isna(value) or str(value).strip() == "":
        return set()
    return {d.strip() for d in str(value).split(",") if d.strip()}


def _mark_unavailable(staff_id: str, day: str) -> None:
    """Add `day` to staff_id's unavailable_days in the effective schedule.

    Called whenever an absence resolves, so the absent person's now-OFF
    effective cell doesn't read as an ordinary day off: without this, they
    could be offered -- or even auto-assigned -- to cover a *different*
    absence on the same day they're actually out (PRD Section 12).
    classify_absence's eligibility check already excludes candidates with
    `day in unavailable_days` (unmodified, in classification.py); this
    only changes what string gets written into the effective schedule's
    unavailable_days column, not that check itself.
    """
    mask = _effective_schedule["staff_id"] == staff_id
    current_days = _parse_unavailable_days(_effective_schedule.loc[mask, "unavailable_days"].iloc[0])
    current_days.add(day)
    # DAY_COLUMNS order, not set-iteration order, so the written string is
    # stable and matches the CSV's own day ordering (PRD Section 5).
    ordered_days = [d for d in DAY_COLUMNS if d in current_days]
    _effective_schedule.loc[mask, "unavailable_days"] = ",".join(ordered_days)


def _apply_coverage(absent_staff_id: str, day: str, covering_staff_id: str) -> None:
    """Update the effective schedule for one resolved absence (PRD Section 12).

    The covering person's day flips from OFF to the shift being covered;
    the absent person's day flips to OFF, and that day is added to their
    effective unavailable_days so they aren't mistaken for someone who
    simply has that day off. The covered shift is always read from the
    *original* uploaded schedule, not the possibly already-mutated
    effective one, so this stays correct even if the same (staff_id, day)
    is somehow resolved more than once.
    """
    covered_shift = _original_roster.loc[
        _original_roster["staff_id"] == absent_staff_id, day
    ].iloc[0]
    _effective_schedule.loc[_effective_schedule["staff_id"] == absent_staff_id, day] = "OFF"
    _effective_schedule.loc[
        _effective_schedule["staff_id"] == covering_staff_id, day
    ] = covered_shift
    _mark_unavailable(absent_staff_id, day)


def _event_response(event: AbsenceEvent) -> dict:
    data = {
        "id": event.id,
        "staff_id": event.staff_id,
        "staff_name": event.staff_name,
        "department": event.department,
        "day": event.day,
        "reason": event.reason,
        "decision": event.decision,
        "mode": event.mode,
        "note": event.note,
        "eligible_candidates": [_candidate_dict(c) for c in event.eligible_candidates],
        "clean_matches": [_candidate_dict(c) for c in event.clean_matches],
        "resolved": event.resolved,
        "resolution": event.resolution,
        "covered_by": event.covered_by,
    }
    if event.candidates is not None:
        data["candidates"] = [_brief_candidate_dict(c) for c in event.candidates]
    return data


@app.post("/roster")
async def post_roster(file: UploadFile = File(...)) -> dict:
    """Load and validate a roster CSV; store it and reset derived state.

    Always stores whatever clean rows load_and_validate_roster returns,
    even when some rows are invalid (PRD Section 5: invalid rows are
    reported, not silently dropped from the response -- but the valid
    rows are still usable).
    """
    content = await file.read()
    clean_df, errors = load_and_validate_roster(io.BytesIO(content))
    set_roster(clean_df)
    return {
        "success": len(errors) == 0,
        "errors": errors,
        "staff_count": len(clean_df),
    }


@app.post("/absences")
def post_absence(
    request: AbsenceRequest,
    schedule: pd.DataFrame = Depends(get_effective_schedule),
    anthropic_client=Depends(get_anthropic_client),
) -> dict:
    """Classify a reported absence and record it as an event.

    Classifies against the *effective* schedule (PRD Section 12), so
    eligibility and overtime math reflect anyone already covering another
    shift, not just the original upload.

    decision == "auto" resolves the event immediately and updates the
    effective schedule. decision == "escalate" stores the event pending;
    mode == "multi" additionally fetches the AI brief and returns the
    ranked candidates in this same response (PRD Section 8), caching them
    on the event so GET /events can show the same ranking without
    re-calling the API.
    """
    try:
        result = classify_absence(schedule, request.staff_id, request.day)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    absent_row = schedule.loc[schedule["staff_id"] == request.staff_id].iloc[0]
    event = AbsenceEvent(
        id=str(uuid.uuid4()),
        staff_id=request.staff_id,
        staff_name=absent_row["name"],
        department=absent_row["department"],
        day=request.day,
        reason=request.reason,
        decision=result.decision,
        mode=result.mode,
        note=result.note,
        eligible_candidates=result.eligible_candidates,
        clean_matches=result.clean_matches,
    )

    if result.decision == "auto":
        event.resolved = True
        event.resolution = "auto"
        event.covered_by = result.assigned_staff_id
        _apply_coverage(event.staff_id, event.day, event.covered_by)

    # Record the event before attempting the AI call, so a failed brief
    # fetch still leaves the absence recorded (visible via GET /events,
    # pending, without a cached brief) instead of silently disappearing.
    _events.append(event)

    if result.mode == "multi":
        absence_context = AbsenceContext(
            staff_id=request.staff_id,
            name=event.staff_name,
            department=event.department,
            day=request.day,
            reason=request.reason,
        )
        try:
            event.candidates = get_coverage_brief(result, absence_context, client=anthropic_client)
        except CoverageBriefError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    return _event_response(event)


@app.get("/events")
def get_events() -> list[dict]:
    """Every reported absence, oldest first (creation order)."""
    return [_event_response(event) for event in _events]


@app.get("/schedule")
def get_schedule() -> dict:
    """The original uploaded schedule and the current effective schedule."""
    if _original_roster is None or _effective_schedule is None:
        raise HTTPException(status_code=400, detail="No roster loaded.")
    return {
        "original": _df_records(_original_roster),
        "effective": _df_records(_effective_schedule),
    }


@app.post("/events/{event_id}/assign")
def assign_event(event_id: str, request: AssignRequest) -> dict:
    """Manually resolve a pending escalation by assigning a covering staff_id."""
    event = next((e for e in _events if e.id == event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail=f"No event with id '{event_id}'.")
    if event.resolved:
        raise HTTPException(status_code=409, detail=f"Event '{event_id}' is already resolved.")
    if event.mode == "none":
        raise HTTPException(
            status_code=400,
            detail="This event has no eligible candidates -- there is nothing to "
            "assign (PRD Section 7: escalate-none has no assign action).",
        )
    if (
        _effective_schedule is None
        or _effective_schedule.loc[_effective_schedule["staff_id"] == request.staff_id].empty
    ):
        raise HTTPException(
            status_code=400, detail=f"staff_id '{request.staff_id}' not found in roster."
        )

    event.resolved = True
    event.resolution = "manual"
    event.covered_by = request.staff_id
    _apply_coverage(event.staff_id, event.day, request.staff_id)

    return _event_response(event)
