"""Unit tests for src.coverage_brief.get_coverage_brief.

Covers: a normal multi-candidate call returns parsed candidates, malformed
JSON raises a clear error, and calling with mode "auto"/"none"/"single"
raises ValueError before any network call is attempted.
"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.classification import Candidate, ClassificationResult
from src.coverage_brief import AbsenceContext, CoverageBriefError, get_coverage_brief

ABSENCE_CONTEXT = AbsenceContext(
    staff_id="S001", name="Alice Ramirez", department="Front Desk", day="Mon", reason="Sick"
)

ELIGIBLE_CANDIDATES = [
    Candidate(staff_id="S002", name="Ben Okafor", same_department=True, hours_scheduled=24, would_overtime=False),
    Candidate(staff_id="S003", name="Carla Nguyen", same_department=True, hours_scheduled=32, would_overtime=True),
]


def _multi_result() -> ClassificationResult:
    return ClassificationResult(
        decision="escalate",
        mode="multi",
        note="2 qualified matches, manager's call.",
        eligible_candidates=ELIGIBLE_CANDIDATES,
        clean_matches=[ELIGIBLE_CANDIDATES[0]],
    )


def _mock_client_with_text(text: str) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)]
    )
    return client


def test_multi_candidate_call_returns_parsed_candidates():
    valid_json = json.dumps(
        {
            "candidates": [
                {"staff_id": "S002", "score": 90, "reasoning": "Same department, no overtime.", "warning": ""},
                {"staff_id": "S003", "score": 40, "reasoning": "Same department but would incur overtime.", "warning": "Overtime risk."},
            ]
        }
    )
    client = _mock_client_with_text(valid_json)

    candidates = get_coverage_brief(_multi_result(), ABSENCE_CONTEXT, client=client)

    assert client.messages.create.call_count == 1
    _, kwargs = client.messages.create.call_args
    assert kwargs["model"] == "claude-sonnet-4-6"

    assert len(candidates) == 2
    assert candidates[0].staff_id == "S002"
    assert candidates[0].score == 90.0
    assert candidates[0].reasoning == "Same department, no overtime."
    assert candidates[1].staff_id == "S003"
    assert candidates[1].warning == "Overtime risk."


def test_null_warning_parses_as_empty_string_not_literal_none():
    valid_json = json.dumps(
        {
            "candidates": [
                {"staff_id": "S002", "score": 90, "reasoning": "Clean fit.", "warning": None},
            ]
        }
    )
    client = _mock_client_with_text(valid_json)

    candidates = get_coverage_brief(_multi_result(), ABSENCE_CONTEXT, client=client)

    assert candidates[0].warning == ""
    assert candidates[0].warning != "None"


def test_malformed_json_raises_clear_error():
    client = _mock_client_with_text("this is not JSON at all {")

    with pytest.raises(CoverageBriefError, match="not valid JSON"):
        get_coverage_brief(_multi_result(), ABSENCE_CONTEXT, client=client)


def test_missing_candidates_key_raises_clear_error():
    client = _mock_client_with_text(json.dumps({"oops": []}))

    with pytest.raises(CoverageBriefError, match="candidates"):
        get_coverage_brief(_multi_result(), ABSENCE_CONTEXT, client=client)


@pytest.mark.parametrize("mode", ["auto", "none", "single"])
def test_non_multi_modes_raise_value_error_before_any_network_call(mode):
    result = ClassificationResult(
        decision="auto" if mode == "auto" else "escalate",
        mode=mode,
        note="irrelevant",
        eligible_candidates=ELIGIBLE_CANDIDATES,
        clean_matches=[],
    )
    client = MagicMock()

    with pytest.raises(ValueError, match="mode == 'multi'"):
        get_coverage_brief(result, ABSENCE_CONTEXT, client=client)

    client.messages.create.assert_not_called()
