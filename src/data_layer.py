"""Data layer for Coverage Copilot.

Loads and validates an uploaded roster CSV against the schema in
coverage-copilot-prd.md Section 5. Invalid rows are reported, never
silently dropped or auto-corrected (PRD Section 5, "Validation rules").

No UI or coverage-matching logic lives here — see Section 6 of the PRD
for that (not yet implemented).
"""

from __future__ import annotations

import pandas as pd

# --- Schema constants (PRD Section 5) --------------------------------------

DAY_COLUMNS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

REQUIRED_COLUMNS = [
    "staff_id",
    "name",
    "role",
    "department",
    "weekly_cap_hours",
    "sick_balance_hours",
    "unavailable_days",
    *DAY_COLUMNS,
]

VALID_SHIFT_CODES = {"M", "A", "E", "OFF"}

VALID_DAYS = set(DAY_COLUMNS)

# "configurable fixed list" per PRD Section 5 — swap/extend as needed.
DEFAULT_DEPARTMENTS = ["Front Desk", "Housekeeping", "F&B", "Concierge"]

HOUR_COLUMNS = ["weekly_cap_hours", "sick_balance_hours"]


def load_and_validate_roster(
    file, departments: list[str] | None = None
) -> tuple[pd.DataFrame, list[str]]:
    """Load a roster CSV and validate it against the PRD Section 5 schema.

    Args:
        file: path or file-like object accepted by ``pandas.read_csv``
            (e.g. a Streamlit ``UploadedFile``).
        departments: allowed department values. Defaults to
            ``DEFAULT_DEPARTMENTS``.

    Returns:
        A tuple of ``(clean_df, errors)``:
        - ``clean_df``: a DataFrame containing only rows that passed every
          validation rule, with hour columns coerced to ``int``.
        - ``errors``: human-readable strings describing every problem
          found. Empty if the file is fully valid.
    """
    allowed_departments = set(departments) if departments else set(DEFAULT_DEPARTMENTS)

    try:
        df = pd.read_csv(file, dtype=str, keep_default_na=True)
    except Exception as exc:  # noqa: BLE001 - surface any parse failure to the user
        return pd.DataFrame(columns=REQUIRED_COLUMNS), [f"Could not read CSV file: {exc}"]

    missing_columns = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_columns:
        return (
            pd.DataFrame(columns=REQUIRED_COLUMNS),
            [f"Missing required column(s): {', '.join(missing_columns)}"],
        )

    errors: list[str] = []
    valid_row_indices: list[int] = []

    # staff_id uniqueness is a file-wide check, not a per-row one.
    staff_id_counts = df["staff_id"].astype(str).str.strip().value_counts()
    duplicate_ids = set(staff_id_counts[staff_id_counts > 1].index)

    for idx, row in df.iterrows():
        csv_row_num = idx + 2  # +1 for header, +1 for 1-indexing
        raw_staff_id = row["staff_id"]
        staff_id = str(raw_staff_id).strip() if pd.notna(raw_staff_id) else ""
        label = f"Row {csv_row_num}" + (f" (staff_id '{staff_id}')" if staff_id else "")

        row_errors: list[str] = []

        for col in ["staff_id", "name", "role"]:
            value = row[col]
            if pd.isna(value) or str(value).strip() == "":
                row_errors.append(f"{label}: missing required value in column '{col}'")

        if staff_id and staff_id in duplicate_ids:
            row_errors.append(f"{label}: duplicate staff_id '{staff_id}' — staff_id must be unique")

        department = row["department"]
        if pd.isna(department) or str(department).strip() == "":
            row_errors.append(f"{label}: missing required value in column 'department'")
        elif str(department).strip() not in allowed_departments:
            row_errors.append(
                f"{label}: invalid department '{department}' — must be one of "
                f"{', '.join(sorted(allowed_departments))}"
            )

        for col in HOUR_COLUMNS:
            value = row[col]
            if pd.isna(value) or str(value).strip() == "":
                row_errors.append(f"{label}: missing required value in column '{col}'")
                continue
            try:
                numeric_value = float(str(value).strip())
            except ValueError:
                row_errors.append(f"{label}: '{col}' must be numeric, got '{value}'")
                continue
            if numeric_value < 0:
                row_errors.append(f"{label}: '{col}' must be non-negative, got {value}")
            elif not numeric_value.is_integer():
                row_errors.append(f"{label}: '{col}' must be a whole number, got {value}")

        unavailable_days_raw = row["unavailable_days"]
        if pd.isna(unavailable_days_raw) or str(unavailable_days_raw).strip() == "":
            unavailable_days = []
        else:
            unavailable_days = [d.strip() for d in str(unavailable_days_raw).split(",") if d.strip()]
        invalid_days = [d for d in unavailable_days if d not in VALID_DAYS]
        if invalid_days:
            row_errors.append(
                f"{label}: invalid value(s) in 'unavailable_days': {', '.join(invalid_days)} — "
                f"must be a subset of {', '.join(DAY_COLUMNS)}"
            )

        for col in DAY_COLUMNS:
            value = row[col]
            if pd.isna(value) or str(value).strip() == "":
                row_errors.append(f"{label}: missing shift value in column '{col}'")
                continue
            shift = str(value).strip()
            if shift not in VALID_SHIFT_CODES:
                row_errors.append(
                    f"{label}: invalid shift code '{shift}' in column '{col}' — "
                    f"must be one of {', '.join(sorted(VALID_SHIFT_CODES))}"
                )

        if row_errors:
            errors.extend(row_errors)
        else:
            valid_row_indices.append(idx)

    clean_df = df.loc[valid_row_indices].reset_index(drop=True).copy()
    for col in HOUR_COLUMNS:
        if not clean_df.empty:
            clean_df[col] = clean_df[col].astype(float).astype(int)
        else:
            clean_df[col] = clean_df[col]

    return clean_df, errors
