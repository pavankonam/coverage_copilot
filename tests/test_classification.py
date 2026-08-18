"""Unit tests for src.classification.classify_absence.

Covers the five acceptance scenarios in coverage-copilot-prd.md Section 10,
by name:
  1. Auto-resolve
  2. Escalate — balance flag
  3. Escalate — multi-candidate
  4. Escalate — no match
  5. Escalate — overtime-only single

Each test builds its roster through data_layer.load_and_validate_roster so
the DataFrame fed to classify_absence matches exactly what the real
pipeline would produce (int-typed hour columns, etc).
"""

import io

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


def test_auto_resolve():
    # Exactly one same-department, non-overtime, available colleague;
    # sufficient balance -> auto-assigns.
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )

    result = classify_absence(roster, "S001", "Mon")

    assert result.decision == "auto"
    assert result.mode == "auto"
    assert result.assigned_staff_id == "S002"
    assert len(result.eligible_candidates) == 1
    assert len(result.clean_matches) == 1
    candidate = result.clean_matches[0]
    assert candidate.same_department is True
    assert candidate.would_overtime is False
    assert candidate.hours_scheduled == 24  # Tue, Thu, Fri = 3 * 8


def test_escalate_balance_flag():
    # Sick balance < 8h, even with an otherwise clean match available -> escalates.
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,4,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )

    result = classify_absence(roster, "S001", "Mon")

    assert result.decision == "escalate"
    assert result.note == "Low balance, flagged for review."
    # One eligible (clean) candidate exists, so mode follows eligible count.
    assert result.mode == "single"
    assert len(result.eligible_candidates) == 1
    assert len(result.clean_matches) == 1


def test_escalate_multi_candidate():
    # Two or more eligible, clean-matching candidates -> escalates, mode=multi.
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
        "S003,Carla,Front Desk Agent,Front Desk,40,16,,OFF,M,OFF,M,M,OFF,OFF",
    )

    result = classify_absence(roster, "S001", "Mon")

    assert result.decision == "escalate"
    assert result.mode == "multi"
    assert result.note == "2 qualified matches, manager's call."
    assert len(result.eligible_candidates) == 2
    assert len(result.clean_matches) == 2
    assert {c.staff_id for c in result.clean_matches} == {"S002", "S003"}


def test_escalate_no_match():
    # Zero eligible candidates -> escalates, mode=none, static message only.
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,40,16,,M,M,OFF,M,M,OFF,OFF",
    )

    result = classify_absence(roster, "S001", "Mon")

    assert result.decision == "escalate"
    assert result.mode == "none"
    assert result.note == "No internal coverage found."
    assert result.eligible_candidates == []
    assert result.clean_matches == []


def test_escalate_overtime_only_single():
    # Exactly one eligible candidate, but assigning them causes overtime ->
    # escalates, single candidate with an overtime warning, manual assign.
    roster = _roster(
        "S001,Alice,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF",
        "S002,Ben,Front Desk Agent,Front Desk,24,16,,OFF,M,M,M,OFF,OFF,OFF",
    )

    result = classify_absence(roster, "S001", "Mon")

    assert result.decision == "escalate"
    assert result.mode == "single"
    assert result.note == "No clean same-department match without overtime."
    assert len(result.eligible_candidates) == 1
    assert result.clean_matches == []
    candidate = result.eligible_candidates[0]
    assert candidate.staff_id == "S002"
    assert candidate.same_department is True
    assert candidate.would_overtime is True
    assert candidate.hours_scheduled == 24  # Tue, Wed, Thu = 3 * 8
