"""Unit tests for src.data_layer.load_and_validate_roster.

Covers the scenarios called out for the data layer: a valid file, a
missing column, an invalid shift code, and a negative hour value.
"""

import io
from pathlib import Path

from src.data_layer import load_and_validate_roster

REPO_ROOT = Path(__file__).resolve().parent.parent

VALID_CSV = """staff_id,name,role,department,weekly_cap_hours,sick_balance_hours,unavailable_days,Mon,Tue,Wed,Thu,Fri,Sat,Sun
S001,Alice Ramirez,Front Desk Agent,Front Desk,40,24,,M,M,OFF,M,M,OFF,OFF
S002,Ben Okafor,Front Desk Agent,Front Desk,40,16,Sun,OFF,M,M,OFF,M,M,OFF
"""


def test_valid_file_returns_clean_df_and_no_errors():
    # The shipped sample template should itself be fully valid.
    clean_df, errors = load_and_validate_roster(REPO_ROOT / "data" / "sample_roster.csv")

    assert errors == []
    assert len(clean_df) == 7
    assert list(clean_df.columns) == [
        "staff_id",
        "name",
        "role",
        "department",
        "weekly_cap_hours",
        "sick_balance_hours",
        "unavailable_days",
        "Mon",
        "Tue",
        "Wed",
        "Thu",
        "Fri",
        "Sat",
        "Sun",
    ]
    # Hour columns should be coerced to int.
    assert clean_df["weekly_cap_hours"].tolist() == [40, 40, 32, 40, 40, 40, 24]


def test_missing_column_is_reported_and_nothing_is_returned_as_clean():
    # Drop the Sun column entirely (header + both data rows' last field).
    lines = VALID_CSV.strip("\n").split("\n")
    header = lines[0].split(",")
    sun_idx = header.index("Sun")
    new_lines = []
    for line in lines:
        fields = line.split(",")
        del fields[sun_idx]
        new_lines.append(",".join(fields))
    csv_text = "\n".join(new_lines) + "\n"

    clean_df, errors = load_and_validate_roster(io.StringIO(csv_text))

    assert clean_df.empty
    assert len(errors) == 1
    assert "Missing required column(s): Sun" in errors[0]


def test_invalid_shift_code_is_reported_and_row_excluded():
    lines = VALID_CSV.strip("\n").split("\n")
    # Corrupt S002's Wed shift (valid codes are M, A, E, OFF).
    fields = lines[2].split(",")
    header = lines[0].split(",")
    wed_idx = header.index("Wed")
    fields[wed_idx] = "NIGHT"
    lines[2] = ",".join(fields)
    csv_text = "\n".join(lines) + "\n"

    clean_df, errors = load_and_validate_roster(io.StringIO(csv_text))

    # S001 is untouched and still valid; S002 is dropped.
    assert clean_df["staff_id"].tolist() == ["S001"]
    assert any("invalid shift code 'NIGHT'" in e and "Wed" in e for e in errors)
    assert any("S002" in e for e in errors)


def test_negative_hour_value_is_reported_and_row_excluded():
    lines = VALID_CSV.strip("\n").split("\n")
    fields = lines[1].split(",")
    header = lines[0].split(",")
    cap_idx = header.index("weekly_cap_hours")
    fields[cap_idx] = "-5"
    lines[1] = ",".join(fields)
    csv_text = "\n".join(lines) + "\n"

    clean_df, errors = load_and_validate_roster(io.StringIO(csv_text))

    # S002 is untouched and still valid; S001 is dropped.
    assert clean_df["staff_id"].tolist() == ["S002"]
    assert any(
        "weekly_cap_hours" in e and "non-negative" in e and "-5" in e for e in errors
    )
    assert any("S001" in e for e in errors)
