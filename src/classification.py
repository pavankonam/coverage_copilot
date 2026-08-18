"""Deterministic absence-coverage classification for Coverage Copilot.

Implements coverage-copilot-prd.md Section 6 exactly as written. This is
the product's core IP — no added heuristics, no "improvements" beyond
what Section 6 specifies.

Pure Python / pandas only: no Streamlit, no Anthropic API calls. The
escalate-multi AI brief (PRD Section 8) is a separate, later concern —
this module only produces the classification the LLM path would consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.data_layer import DAY_COLUMNS

SHIFT_HOURS = 8
BALANCE_THRESHOLD_HOURS = 8


@dataclass(frozen=True)
class Candidate:
    """One eligible coverage candidate (PRD Section 6, step 2)."""

    staff_id: str
    name: str
    same_department: bool
    hours_scheduled: int
    would_overtime: bool


@dataclass(frozen=True)
class ClassificationResult:
    """Structured output of classify_absence."""

    decision: str  # "auto" | "escalate"
    mode: str  # "auto" | "none" | "single" | "multi"
    note: str
    eligible_candidates: list[Candidate] = field(default_factory=list)
    clean_matches: list[Candidate] = field(default_factory=list)
    assigned_staff_id: str | None = None


def _parse_unavailable_days(value) -> set[str]:
    if pd.isna(value) or str(value).strip() == "":
        return set()
    return {d.strip() for d in str(value).split(",") if d.strip()}


def _mode_from_eligible_count(eligible_count: int) -> str:
    if eligible_count == 0:
        return "none"
    if eligible_count == 1:
        return "single"
    return "multi"


def classify_absence(roster: pd.DataFrame, staff_id: str, day: str) -> ClassificationResult:
    """Classify a single absence event per PRD Section 6.

    Args:
        roster: the clean DataFrame returned by
            ``data_layer.load_and_validate_roster``.
        staff_id: the absent employee's staff_id.
        day: one of Mon, Tue, Wed, Thu, Fri, Sat, Sun.

    Returns:
        A ClassificationResult describing the auto-resolve or escalate
        decision, per the exact rule tree in Section 6.
    """
    if day not in DAY_COLUMNS:
        raise ValueError(f"Invalid day '{day}' — must be one of {', '.join(DAY_COLUMNS)}")

    absent_rows = roster[roster["staff_id"] == staff_id]
    if absent_rows.empty:
        raise ValueError(f"staff_id '{staff_id}' not found in roster")
    absent = absent_rows.iloc[0]

    absent_department = absent["department"]
    sick_balance_hours = int(absent["sick_balance_hours"])

    # --- Step 1: eligible pool -------------------------------------------
    eligible_candidates: list[Candidate] = []
    others = roster[roster["staff_id"] != staff_id]
    for _, row in others.iterrows():
        unavailable_days = _parse_unavailable_days(row["unavailable_days"])
        if row[day] != "OFF" or day in unavailable_days:
            continue

        # --- Step 2: per-candidate fields ---------------------------------
        hours_scheduled = sum(
            SHIFT_HOURS for d in DAY_COLUMNS if row[d] != "OFF"
        )
        same_department = row["department"] == absent_department
        would_overtime = hours_scheduled + SHIFT_HOURS > int(row["weekly_cap_hours"])

        eligible_candidates.append(
            Candidate(
                staff_id=row["staff_id"],
                name=row["name"],
                same_department=same_department,
                hours_scheduled=hours_scheduled,
                would_overtime=would_overtime,
            )
        )

    # --- Step 3: clean matches --------------------------------------------
    clean_matches = [c for c in eligible_candidates if c.same_department and not c.would_overtime]

    # --- Step 4: balance flag ----------------------------------------------
    balance_flag = sick_balance_hours < BALANCE_THRESHOLD_HOURS

    # --- Decision (in order, per Section 6) ---------------------------------
    if balance_flag:
        return ClassificationResult(
            decision="escalate",
            mode=_mode_from_eligible_count(len(eligible_candidates)),
            note="Low balance, flagged for review.",
            eligible_candidates=eligible_candidates,
            clean_matches=clean_matches,
        )

    if len(eligible_candidates) == 0:
        return ClassificationResult(
            decision="escalate",
            mode="none",
            note="No internal coverage found.",
            eligible_candidates=eligible_candidates,
            clean_matches=clean_matches,
        )

    if len(clean_matches) == 1:
        match = clean_matches[0]
        return ClassificationResult(
            decision="auto",
            mode="auto",
            note=f"Auto-resolved: {match.name} ({match.staff_id}) assigned — "
            "same department, no overtime.",
            eligible_candidates=eligible_candidates,
            clean_matches=clean_matches,
            assigned_staff_id=match.staff_id,
        )

    if len(clean_matches) == 0:
        mode = "single" if len(eligible_candidates) == 1 else "multi"
        return ClassificationResult(
            decision="escalate",
            mode=mode,
            note="No clean same-department match without overtime.",
            eligible_candidates=eligible_candidates,
            clean_matches=clean_matches,
        )

    # clean_matches count >= 2
    return ClassificationResult(
        decision="escalate",
        mode="multi",
        note=f"{len(clean_matches)} qualified matches, manager's call.",
        eligible_candidates=eligible_candidates,
        clean_matches=clean_matches,
    )
