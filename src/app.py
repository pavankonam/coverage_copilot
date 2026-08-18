"""Coverage Copilot — Streamlit entry point.

Implements Screens A, B, C, and D from coverage-copilot-prd.md Section 7:

- A — Upload: file uploader, sample template download, inline validation errors.
- B — Schedule board: weekly grid (staff x day). Clicking a filled (non-OFF)
  cell opens an absence-report form (free-text reason); submitting it calls
  classify_absence() and appends the event to the coverage board.
- C — Coverage board: a list of every reported coverage event. Auto-resolved
  events (decision == "auto") show a distinct "Auto" badge — Section 6 says
  the system assigns these automatically, no manual step needed. Events
  resolved manually via Screen D show a distinct "Approved by you" badge.
  Everything else still open is shown as "Open" with no badge.
- D — Pending review, for every open escalate-* event:
  - mode == "none" shows the static note with no action.
  - mode == "single" shows the one eligible candidate and a manual Assign
    action.
  - mode == "multi" calls get_coverage_brief() (PRD Section 8 — the only
    code path that calls the Anthropic API) once per event and caches the
    ranked candidates on the event itself, so it isn't re-fetched on every
    rerun. Each ranked candidate gets its own manual Assign action. If the
    call fails, the error is shown with a Retry action instead of crashing.
  Clicking Assign in any mode marks the event resolved in place (no
  schedule mutation yet).
- E — Ledger: a chronological (oldest first) log of every resolved event —
  decision == "auto" or resolved_manually == True — tagged with its
  resolution mode (Auto/Manual) and the reason for absence. Reuses the
  existing CoverageEvent fields; no new state.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

# Locally we've always launched via `python3 -m streamlit run src/app.py`,
# and the `-m` flag makes Python add the launch directory (the repo root)
# to sys.path — that's what lets `from src.xxx import ...` below resolve.
# Streamlit Community Cloud instead runs the installed `streamlit` console
# script directly (not `python -m streamlit`), which only puts this file's
# own directory (src/) on sys.path, not its parent — so `src` is never
# importable as a package there, and the same import raises
# ModuleNotFoundError: No module named 'src'. Insert the repo root
# explicitly so these imports resolve the same way regardless of how the
# script is launched.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from src.classification import ClassificationResult, classify_absence
from src.coverage_brief import AbsenceContext, BriefCandidate, CoverageBriefError, get_coverage_brief
from src.data_layer import DAY_COLUMNS, load_and_validate_roster

SAMPLE_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_roster.csv"

st.set_page_config(page_title="Coverage Copilot", layout="wide")


@dataclasses.dataclass(frozen=True)
class CoverageEvent:
    """One reported absence and its classification, for the coverage board."""

    staff_id: str
    day: str
    shift: str
    department: str
    reason: str
    result: ClassificationResult
    resolved_manually: bool = False
    assigned_staff_id: str | None = None
    brief_candidates: list[BriefCandidate] | None = None  # cached get_coverage_brief() result
    brief_error: str | None = None  # cached get_coverage_brief() failure, if any


def _assign_candidate(idx: int, event: CoverageEvent, staff_id: str) -> None:
    """Resolve a pending escalated event by manually assigning staff_id.

    Shared by every Screen D mode (single and multi) so the resolution
    behavior — mark resolved, record who was assigned, rerun so Screen C
    picks up the "Approved by you" badge immediately — lives in one place.
    """
    st.session_state["coverage_events"][idx] = dataclasses.replace(
        event, resolved_manually=True, assigned_staff_id=staff_id
    )
    st.rerun()


def _candidate_display_name(event: CoverageEvent, staff_id: str) -> str:
    """Look up a candidate's name from the event's own eligible_candidates.

    BriefCandidate (the AI brief's ranked output) carries no name field —
    only staff_id/score/reasoning/warning — so cross-reference the
    classification result's eligible_candidates, which does have it.
    """
    for candidate in event.result.eligible_candidates:
        if candidate.staff_id == staff_id:
            return candidate.name
    return staff_id


def _init_session_state() -> None:
    st.session_state.setdefault("roster", None)
    st.session_state.setdefault("validation_errors", [])
    st.session_state.setdefault("uploaded_file_id", None)
    st.session_state.setdefault("selected_cell", None)  # (staff_id, day) or None
    st.session_state.setdefault("coverage_events", [])  # list[CoverageEvent]


_init_session_state()

st.title("Coverage Copilot")

# --- Screen A: Upload --------------------------------------------------------

st.header("A — Upload roster")

upload_col, template_col = st.columns([3, 1])

with upload_col:
    uploaded_file = st.file_uploader("Upload roster CSV", type="csv")

with template_col:
    st.write("")
    st.write("")
    if SAMPLE_TEMPLATE_PATH.exists():
        st.download_button(
            "Download sample template",
            data=SAMPLE_TEMPLATE_PATH.read_bytes(),
            file_name="sample_roster.csv",
            mime="text/csv",
        )

if uploaded_file is not None:
    # Streamlit re-attaches the same uploaded file on every rerun (e.g. a
    # schedule-cell click). Only re-validate when it's actually a new file,
    # so an unrelated interaction elsewhere on the page doesn't wipe the
    # in-progress absence-report form below.
    file_id = getattr(uploaded_file, "file_id", None) or (uploaded_file.name, uploaded_file.size)
    if st.session_state["uploaded_file_id"] != file_id:
        clean_df, errors = load_and_validate_roster(uploaded_file)
        st.session_state["roster"] = clean_df
        st.session_state["validation_errors"] = errors
        st.session_state["uploaded_file_id"] = file_id
        st.session_state["selected_cell"] = None
        st.session_state["coverage_events"] = []

validation_errors = st.session_state["validation_errors"]
if validation_errors:
    st.error(f"{len(validation_errors)} validation issue(s) found — these rows were not loaded:")
    for err in validation_errors:
        st.write(f"- {err}")

roster = st.session_state["roster"]

if roster is None:
    st.info("Upload a roster CSV to continue, or download the sample template above.")
    st.stop()

if roster.empty:
    st.warning("No valid rows were loaded from this file. Fix the errors above and re-upload.")
    st.stop()

st.success(f"{len(roster)} staff loaded.")

# --- Screen C: Coverage board -------------------------------------------------

st.header("C — Coverage board")
st.caption("Every reported absence and its coverage status.")

coverage_events: list[CoverageEvent] = st.session_state["coverage_events"]

if not coverage_events:
    st.info("No coverage events yet. Report an absence below to see it here.")
else:
    board_header = st.columns([2, 1, 1, 2, 1.5, 3, 3])
    for col, label in zip(
        board_header, ["Staff", "Day", "Shift", "Department", "Status", "Note", "Reason"]
    ):
        col.markdown(f"**{label}**")

    for event in reversed(coverage_events):  # most recently reported first
        staff_rows = roster[roster["staff_id"] == event.staff_id]
        staff_name = staff_rows.iloc[0]["name"] if not staff_rows.empty else event.staff_id

        row = st.columns([2, 1, 1, 2, 1.5, 3, 3])
        row[0].write(f"{staff_name} ({event.staff_id})")
        row[1].write(event.day)
        row[2].write(event.shift)
        row[3].write(event.department)
        if event.result.decision == "auto":
            with row[4]:
                st.badge("Auto", color="green")
        elif event.resolved_manually:
            with row[4]:
                st.badge("Approved by you", color="blue")
        else:
            row[4].write("Open")
        row[5].write(event.result.note)
        row[6].write(event.reason or "—")

# --- Screen D: Pending review -------------------------------------------------

st.header("D — Pending review")
st.caption("Escalated events awaiting your decision.")

pending_events = [
    (idx, event)
    for idx, event in enumerate(coverage_events)
    if event.result.decision == "escalate" and not event.resolved_manually
]

if not pending_events:
    st.info("No escalations awaiting review.")
else:
    for idx, event in reversed(pending_events):  # most recently reported first
        staff_rows = roster[roster["staff_id"] == event.staff_id]
        staff_name = staff_rows.iloc[0]["name"] if not staff_rows.empty else event.staff_id

        with st.container(border=True):
            st.markdown(f"**{staff_name} ({event.staff_id})** — {event.day}, mode: {event.result.mode}")
            st.write(f"**Note:** {event.result.note}")

            if event.result.mode == "none":
                st.write("No candidates available — no action to take.")

            elif event.result.mode == "single":
                candidate = event.result.eligible_candidates[0]
                dept_desc = "same department" if candidate.same_department else "different department"
                overtime_desc = "would cause overtime" if candidate.would_overtime else "no overtime"
                st.write(
                    f"**Candidate:** {candidate.name} ({candidate.staff_id}) — {dept_desc}, {overtime_desc}."
                )
                if st.button(f"Assign {candidate.name}", key=f"assign_{idx}"):
                    _assign_candidate(idx, event, candidate.staff_id)

            elif event.result.mode == "multi":
                # Fetch the AI brief once per event and cache it on the event
                # itself, so it isn't re-fetched on every rerun.
                if event.brief_candidates is None and event.brief_error is None:
                    absence_context = AbsenceContext(
                        staff_id=event.staff_id,
                        name=staff_name,
                        department=event.department,
                        day=event.day,
                        reason=event.reason or None,
                    )
                    try:
                        brief_candidates = get_coverage_brief(event.result, absence_context)
                    except CoverageBriefError as exc:
                        event = dataclasses.replace(event, brief_error=str(exc))
                    else:
                        event = dataclasses.replace(event, brief_candidates=brief_candidates)
                    st.session_state["coverage_events"][idx] = event

                if event.brief_error is not None:
                    st.error(event.brief_error)
                    if st.button("Retry", key=f"retry_{idx}"):
                        st.session_state["coverage_events"][idx] = dataclasses.replace(
                            event, brief_error=None
                        )
                        st.rerun()
                elif event.brief_candidates is not None:
                    for brief_candidate in event.brief_candidates:
                        candidate_name = _candidate_display_name(event, brief_candidate.staff_id)
                        st.markdown(
                            f"**{candidate_name} ({brief_candidate.staff_id})** — "
                            f"score {brief_candidate.score:.0f}"
                        )
                        st.write(brief_candidate.reasoning)
                        if brief_candidate.warning:
                            st.warning(brief_candidate.warning)
                        if st.button(
                            f"Assign {candidate_name}", key=f"assign_{idx}_{brief_candidate.staff_id}"
                        ):
                            _assign_candidate(idx, event, brief_candidate.staff_id)

# --- Screen B: Schedule board -------------------------------------------------

st.header("B — Schedule board")
st.caption("Click a shift cell to report a sudden absence.")

header_cols = st.columns([2] + [1] * len(DAY_COLUMNS))
header_cols[0].markdown("**Staff**")
for i, day in enumerate(DAY_COLUMNS):
    header_cols[i + 1].markdown(f"**{day}**")

for _, staff_row in roster.iterrows():
    row_cols = st.columns([2] + [1] * len(DAY_COLUMNS))
    row_cols[0].write(f"{staff_row['name']} ({staff_row['staff_id']})")
    for i, day in enumerate(DAY_COLUMNS):
        shift = staff_row[day]
        cell = row_cols[i + 1]
        if shift == "OFF":
            cell.write("OFF")
        elif cell.button(shift, key=f"cell_{staff_row['staff_id']}_{day}"):
            st.session_state["selected_cell"] = (staff_row["staff_id"], day)

# --- Absence-report form (opened by clicking a filled cell) ------------------

selected = st.session_state["selected_cell"]
if selected is not None:
    sel_staff_id, sel_day = selected
    sel_rows = roster[roster["staff_id"] == sel_staff_id]

    if sel_rows.empty:
        st.warning("Selected staff member is no longer in the loaded roster.")
        st.session_state["selected_cell"] = None
    else:
        sel_staff = sel_rows.iloc[0]
        st.divider()
        st.subheader(f"Report absence — {sel_staff['name']} ({sel_staff_id}), {sel_day}")

        with st.form(key=f"absence_form_{sel_staff_id}_{sel_day}"):
            reason = st.text_area("Reason for absence", placeholder="e.g. called in sick")
            submitted = st.form_submit_button("Log absence")

        if submitted:
            result = classify_absence(roster, sel_staff_id, sel_day)
            st.session_state["coverage_events"].append(
                CoverageEvent(
                    staff_id=sel_staff_id,
                    day=sel_day,
                    shift=sel_staff[sel_day],
                    department=sel_staff["department"],
                    reason=reason,
                    result=result,
                )
            )
            # Force an immediate rerun so the Coverage board above reflects
            # this event right away, instead of on the next interaction.
            st.rerun()

# --- Screen E: Ledger ---------------------------------------------------------

st.header("E — Ledger")
st.caption("Chronological log of every resolved coverage event.")

ledger_events = [event for event in coverage_events if event.result.decision == "auto" or event.resolved_manually]

if not ledger_events:
    st.info("No resolved events yet.")
else:
    ledger_header = st.columns([2, 1, 1, 2, 1.5, 3, 3])
    for col, label in zip(
        ledger_header, ["Staff", "Day", "Shift", "Department", "Resolution", "Note", "Reason"]
    ):
        col.markdown(f"**{label}**")

    for event in ledger_events:  # chronological — oldest first, as reported
        staff_rows = roster[roster["staff_id"] == event.staff_id]
        staff_name = staff_rows.iloc[0]["name"] if not staff_rows.empty else event.staff_id

        row = st.columns([2, 1, 1, 2, 1.5, 3, 3])
        row[0].write(f"{staff_name} ({event.staff_id})")
        row[1].write(event.day)
        row[2].write(event.shift)
        row[3].write(event.department)
        with row[4]:
            if event.result.decision == "auto":
                st.badge("Auto", color="green")
            else:
                st.badge("Manual", color="blue")
        row[5].write(event.result.note)
        row[6].write(event.reason or "—")
