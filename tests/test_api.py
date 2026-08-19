"""Tests for the src.api REST endpoints.

Covers:
- POST /absences: a multi-candidate absence gets the AI-drafted ranked
  brief attached to the *same* response, and auto/none/single modes make
  zero API calls (mirroring PRD Section 8's enforcement at this new call
  site too).
- POST /roster: loads a roster and initializes derived state.
- The state-transition behavior from PRD Section 12: an auto-resolved
  absence updates the effective schedule immediately; a multi-mode event
  stays pending until POST /events/{id}/assign is called and only then
  updates the schedule; GET /schedule shows the original and effective
  schedules correctly diverging after a resolution.
- That POST /absences classifies against the effective schedule, not the
  original upload: a person already covering one absence isn't offered
  again for a different absence on the same day.
- GET /events and POST /events/{id}/assign edge cases (404, 409, mode
  "none").

The Anthropic client is always mocked via dependency override, so no real
network call is ever made.
"""

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api import app, get_anthropic_client, set_roster
from src.classification import classify_absence
from src.data_layer import load_and_validate_roster

HEADER = (
    "staff_id,name,role,department,weekly_cap_hours,sick_balance_hours,"
    "unavailable_days,Mon,Tue,Wed,Thu,Fri,Sat,Sun"
)


def _roster(*rows: str):
    csv_text = HEADER + "\n" + "\n".join(rows) + "\n"
    clean_df, errors = load_and_validate_roster(io.StringIO(csv_text))
    assert errors == [], f"unexpected validation errors in test fixture: {errors}"
    return clean_df


def _mock_client_with_text(text: str) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)]
    )
    return client


def _schedule_row(schedule_side: list[dict], staff_id: str) -> dict:
    return next(r for r in schedule_side if r["staff_id"] == staff_id)


@pytest.fixture()
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- POST /absences ---------------------------------------------------------


def test_post_absence_multi_mode_includes_ranked_candidates(client):
    # Two eligible, clean-matching candidates -> classify_absence lands on
    # mode "multi". The endpoint must call get_coverage_brief itself and
    # return the ranked candidates in the same response, not just the
    # bare classification result.
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
        "S003,Carla,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )
    set_roster(roster)

    brief_json = json.dumps(
        {
            "candidates": [
                {"staff_id": "S002", "score": 90, "reasoning": "Same department, no overtime.", "warning": ""},
                {"staff_id": "S003", "score": 80, "reasoning": "Same department, no overtime.", "warning": ""},
            ]
        }
    )
    mock_client = _mock_client_with_text(brief_json)
    app.dependency_overrides[get_anthropic_client] = lambda: mock_client

    response = client.post(
        "/absences", json={"staff_id": "S001", "day": "Mon", "reason": "Sick"}
    )

    assert response.status_code == 200
    body = response.json()

    assert body["mode"] == "multi"
    assert body["resolved"] is False
    assert body["covered_by"] is None
    # The response actually contains the ranked brief, not just the
    # classification -- this is the behavior being tested.
    assert "candidates" in body
    assert mock_client.messages.create.call_count == 1
    assert len(body["candidates"]) == 2
    assert {c["staff_id"] for c in body["candidates"]} == {"S002", "S003"}
    assert body["candidates"][0]["score"] == 90.0
    assert body["candidates"][0]["reasoning"] == "Same department, no overtime."
    assert body["candidates"][1]["warning"] == ""


def test_post_absence_auto_resolve_mode_makes_no_api_call_and_has_no_candidates(client):
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )
    set_roster(roster)

    mock_client = MagicMock()
    app.dependency_overrides[get_anthropic_client] = lambda: mock_client

    response = client.post("/absences", json={"staff_id": "S001", "day": "Mon"})

    assert response.status_code == 200
    body = response.json()

    assert body["mode"] == "auto"
    assert body["resolved"] is True
    assert body["resolution"] == "auto"
    assert body["covered_by"] == "S002"
    assert "candidates" not in body
    mock_client.messages.create.assert_not_called()


# --- POST /roster ------------------------------------------------------------


def test_post_roster_loads_valid_csv_and_initializes_schedule(client):
    csv_text = HEADER + "\n" + "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF\n"

    response = client.post(
        "/roster", files={"file": ("roster.csv", csv_text.encode(), "text/csv")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["errors"] == []
    assert body["staff_count"] == 1

    schedule = client.get("/schedule").json()
    assert schedule["original"] == schedule["effective"]
    assert schedule["original"][0]["staff_id"] == "S001"


def test_post_roster_reports_errors_without_crashing(client):
    # Missing the Sun column entirely -> load_and_validate_roster reports
    # it and returns nothing as clean.
    bad_csv = HEADER.replace(",Sun", "") + "\nS001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF\n"

    response = client.post(
        "/roster", files={"file": ("roster.csv", bad_csv.encode(), "text/csv")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert body["staff_count"] == 0
    assert any("Sun" in e for e in body["errors"])


# --- Effective schedule state transitions (PRD Section 12) ------------------


def test_auto_resolve_updates_effective_schedule_immediately(client):
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )
    set_roster(roster)

    response = client.post("/absences", json={"staff_id": "S001", "day": "Mon", "reason": "Sick"})
    assert response.status_code == 200
    assert response.json()["resolved"] is True

    schedule = client.get("/schedule").json()

    # Original schedule is untouched...
    assert _schedule_row(schedule["original"], "S001")["Mon"] == "M"
    assert _schedule_row(schedule["original"], "S002")["Mon"] == "OFF"
    # ...but the effective schedule reflects the resolution immediately:
    # the absent person is now OFF, the covering person now has the shift.
    assert _schedule_row(schedule["effective"], "S001")["Mon"] == "OFF"
    assert _schedule_row(schedule["effective"], "S002")["Mon"] == "M"


def test_multi_mode_event_stays_pending_until_assign_then_updates_schedule(client):
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
        "S003,Carla,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )
    set_roster(roster)

    brief_json = json.dumps(
        {
            "candidates": [
                {"staff_id": "S002", "score": 90, "reasoning": "r", "warning": ""},
                {"staff_id": "S003", "score": 80, "reasoning": "r", "warning": ""},
            ]
        }
    )
    app.dependency_overrides[get_anthropic_client] = lambda: _mock_client_with_text(brief_json)

    post_response = client.post("/absences", json={"staff_id": "S001", "day": "Mon"})
    assert post_response.status_code == 200
    event = post_response.json()
    assert event["mode"] == "multi"
    assert event["resolved"] is False
    event_id = event["id"]

    # Nothing applied to the effective schedule yet -- still pending.
    schedule_before = client.get("/schedule").json()
    assert _schedule_row(schedule_before["effective"], "S001")["Mon"] == "M"
    assert _schedule_row(schedule_before["effective"], "S003")["Mon"] == "OFF"

    assign_response = client.post(f"/events/{event_id}/assign", json={"staff_id": "S003"})
    assert assign_response.status_code == 200
    resolved = assign_response.json()
    assert resolved["resolved"] is True
    assert resolved["resolution"] == "manual"
    assert resolved["covered_by"] == "S003"

    # Only now does the effective schedule change.
    schedule_after = client.get("/schedule").json()
    assert _schedule_row(schedule_after["effective"], "S001")["Mon"] == "OFF"
    assert _schedule_row(schedule_after["effective"], "S003")["Mon"] == "M"
    # S002 was ranked but not assigned -- untouched.
    assert _schedule_row(schedule_after["effective"], "S002")["Mon"] == "OFF"

    # GET /events reflects the same resolved state.
    events = client.get("/events").json()
    assert len(events) == 1
    assert events[0]["resolved"] is True
    assert events[0]["covered_by"] == "S003"


def test_effective_schedule_prevents_reoffering_a_now_busy_covering_staff(client):
    """Proves the fix: POST /absences classifies against the effective
    schedule, not the original upload, so a person already covering one
    absence isn't offered again for a different absence on the same day.

    S001's own unavailable_days additionally excludes them from being a
    *candidate* here -- not from being reported absent themselves -- so
    this test stays narrowly focused on S002/X's diminished eligibility.
    That exclusion would now also follow automatically from S001's own
    absence resolving (see
    test_own_absence_marks_person_unavailable_for_other_absences_same_day
    below, PRD Section 12) -- keeping it explicit here just isolates this
    test from that separate mechanism.
    """
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,Mon,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,24,,OFF,M,OFF,M,M,OFF,OFF",
        "S003,Carla,Front Desk Agent,Front Desk,40,24,,M,OFF,OFF,OFF,OFF,OFF,OFF",
    )
    set_roster(roster)

    # First absence: S001 out Monday. S002 (X) is the only clean match ->
    # auto-resolves, and S002's effective Monday flips from OFF to the
    # shift they're now covering.
    first = client.post("/absences", json={"staff_id": "S001", "day": "Mon"})
    assert first.status_code == 200
    assert first.json()["decision"] == "auto"
    assert first.json()["covered_by"] == "S002"

    # Sanity check on the bug this fixes: classified against the
    # *original* roster, S002 would still show as OFF Monday and be
    # offered again.
    pre_fix_result = classify_absence(roster, "S003", "Mon")
    assert "S002" in {c.staff_id for c in pre_fix_result.eligible_candidates}

    # Second, different absence, same day: S003 out Monday. Post-fix, the
    # API classifies against the *effective* schedule, where S002 is now
    # busy covering S001's Monday shift -> not offered.
    second = client.post("/absences", json={"staff_id": "S003", "day": "Mon"})
    assert second.status_code == 200
    body = second.json()

    offered_ids = {c["staff_id"] for c in body["eligible_candidates"]}
    assert "S002" not in offered_ids
    assert body["mode"] == "none"
    assert body["note"] == "No internal coverage found."


def test_own_absence_marks_person_unavailable_for_other_absences_same_day(client):
    """Proves the fix for the gap flagged last turn: resolving X's own
    absence marks X unavailable (not just OFF) in the effective schedule,
    so X isn't offered -- or worse, auto-assigned -- to cover a
    *different* absence on the same day X is actually out.

    Unlike the covering-staff case above, X here never covers anyone --
    X is the one who was absent. Pre-fix, X's effective day would be OFF
    like any ordinary day off, with nothing to distinguish "day off" from
    "out sick"; this asserts X is excluded from eligible_candidates
    entirely, not merely filtered out of clean_matches.
    """
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,24,,OFF,M,OFF,M,M,OFF,OFF",
        "S003,Carla,Front Desk Agent,Front Desk,40,24,,M,OFF,OFF,OFF,OFF,OFF,OFF",
    )
    set_roster(roster)

    # First absence: S001 (X) out Monday. S002 is the only clean match ->
    # auto-resolves. S001's effective Monday flips to OFF, and (the fix
    # under test) "Mon" is added to S001's effective unavailable_days.
    first = client.post("/absences", json={"staff_id": "S001", "day": "Mon"})
    assert first.status_code == 200
    assert first.json()["decision"] == "auto"
    assert first.json()["covered_by"] == "S002"

    # Sanity check on how bad the pre-fix bug was: patch a copy of the
    # roster the same way the *shift cells alone* would have ended up
    # (S001 -> OFF, S002 -> now working Monday) but WITHOUT the
    # unavailable_days fix, and classify S003's Monday absence against
    # that. S001 -- out sick that very day -- doesn't just get offered,
    # they're the sole clean match and would have been auto-assigned.
    unfixed_schedule = roster.copy()
    unfixed_schedule.loc[unfixed_schedule["staff_id"] == "S001", "Mon"] = "OFF"
    unfixed_schedule.loc[unfixed_schedule["staff_id"] == "S002", "Mon"] = "M"
    pre_fix_result = classify_absence(unfixed_schedule, "S003", "Mon")
    assert pre_fix_result.decision == "auto"
    assert pre_fix_result.assigned_staff_id == "S001"

    # Second, different absence, same day: S003 out Monday. Post-fix, the
    # API classifies against the effective schedule, where S001 is now
    # marked unavailable Monday (not just OFF) -> excluded entirely, and
    # S002 is excluded too (busy covering, per the other fix) -> nobody
    # left, so this escalates instead of auto-assigning the sick person.
    second = client.post("/absences", json={"staff_id": "S003", "day": "Mon"})
    assert second.status_code == 200
    body = second.json()

    offered_ids = {c["staff_id"] for c in body["eligible_candidates"]}
    assert "S001" not in offered_ids
    assert offered_ids == set()
    assert body["decision"] == "escalate"
    assert body["mode"] == "none"
    assert body["note"] == "No internal coverage found."

    # And the effective schedule itself records the exclusion.
    schedule = client.get("/schedule").json()
    assert _schedule_row(schedule["effective"], "S001")["unavailable_days"] == "Mon"
    assert _schedule_row(schedule["original"], "S001")["unavailable_days"] in ("", None)


def test_get_schedule_shows_original_and_effective_diverging_after_resolution(client):
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )
    set_roster(roster)

    before = client.get("/schedule").json()
    assert before["original"] == before["effective"]  # nothing resolved yet

    client.post("/absences", json={"staff_id": "S001", "day": "Mon"})

    after = client.get("/schedule").json()
    assert after["original"] != after["effective"]
    assert after["original"] == before["original"]  # original is stable


# --- GET /events, POST /events/{id}/assign edge cases ------------------------


def test_get_events_is_oldest_first_and_covers_multiple_reports(client):
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )
    set_roster(roster)

    client.post("/absences", json={"staff_id": "S001", "day": "Mon"})
    client.post("/absences", json={"staff_id": "S002", "day": "Wed"})

    events = client.get("/events").json()
    assert len(events) == 2
    assert events[0]["staff_id"] == "S001"
    assert events[1]["staff_id"] == "S002"


def test_assign_unknown_event_id_returns_404(client):
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )
    set_roster(roster)

    response = client.post("/events/does-not-exist/assign", json={"staff_id": "S002"})
    assert response.status_code == 404


def test_assign_already_resolved_event_returns_409(client):
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )
    set_roster(roster)

    event_id = client.post("/absences", json={"staff_id": "S001", "day": "Mon"}).json()["id"]
    assert client.get("/events").json()[0]["resolved"] is True  # auto-resolved already

    response = client.post(f"/events/{event_id}/assign", json={"staff_id": "S002"})
    assert response.status_code == 409


def test_assign_on_mode_none_event_returns_400(client):
    # Zero eligible candidates -> mode "none" -> nothing to assign.
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,M,M,OFF,M,M,OFF,OFF",
    )
    set_roster(roster)

    event_id = client.post("/absences", json={"staff_id": "S001", "day": "Mon"}).json()["id"]

    response = client.post(f"/events/{event_id}/assign", json={"staff_id": "S002"})
    assert response.status_code == 400
