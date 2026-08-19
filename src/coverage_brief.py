"""AI-drafted coverage brief for the genuine multi-candidate trade-off case.

Implements coverage-copilot-prd.md Section 8 exactly:

- The Anthropic API is called in EXACTLY ONE code path: escalate-multi.
  get_coverage_brief() raises ValueError immediately if called with any
  other classification mode, before any network call is attempted — this
  is enforced in code, not just by convention.
- The prompt is given the FULL eligible candidate pool (not just
  clean_matches), since a genuine multi-candidate trade-off may reasonably
  recommend a cross-department fit when same-department options are weak.
- The model ranks candidates and explains trade-offs/overtime risk. It
  never claims to authorize or assign anyone — output is JSON only.
- The API key is read from the ANTHROPIC_API_KEY environment variable.
  Never hardcoded.
- API failures (missing key, network, malformed response) never crash the
  caller — they raise CoverageBriefError, which a UI layer can catch to
  offer a retry action.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
from dataclasses import dataclass

import anthropic

from src.classification import ClassificationResult

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are assisting a hotel department manager who must choose \
internal coverage for a sudden staff absence. You are given the absent \
employee's context and the full pool of eligible candidates (staff who are \
off that day and not otherwise unavailable) for a genuine multi-candidate \
trade-off — this prompt is only used when more than one reasonable option \
exists.

Rank the candidates and briefly explain the trade-offs and overtime risk \
for each. Same-department, non-overtime candidates are usually the \
strongest fits, but a reasonable cross-department candidate may be worth \
surfacing when the same-department options are weak (e.g. all would incur \
overtime).

You are NOT authorizing or assigning anyone. The manager makes the final \
call. Never state or imply that a candidate is assigned, approved, or \
authorized — describe them only as ranked options with reasoning.

Respond with JSON only, no prose before or after, matching exactly this \
shape:

{"candidates":[{"staff_id": "...", "score": <number 0-100>, "reasoning": \
"...", "warning": "..."}]}

- "score": your ranking, higher is a stronger fit.
- "reasoning": one or two sentences on why this candidate is a reasonable \
(or weak) fit.
- "warning": a short note on overtime or other risk for this candidate, \
or an empty string if none.
- Include one entry per candidate you were given, ordered best first.
"""


class CoverageBriefError(RuntimeError):
    """Raised when a coverage brief cannot be produced.

    Covers a missing API key, an Anthropic API failure, and a malformed
    model response. Callers (the eventual UI layer) should catch this and
    offer the user a retry action rather than letting the app crash.
    """


@dataclass(frozen=True)
class AbsenceContext:
    """Context about the absent employee, for the prompt only."""

    staff_id: str
    name: str
    department: str
    day: str
    reason: str | None = None


@dataclass(frozen=True)
class BriefCandidate:
    """One ranked candidate as returned by the model."""

    staff_id: str
    score: float
    reasoning: str
    warning: str


def _get_api_key() -> str | None:
    """Resolve the Anthropic API key from the ANTHROPIC_API_KEY env var.

    Never hardcoded.
    """
    return os.environ.get("ANTHROPIC_API_KEY")


def _build_user_message(
    classification_result: ClassificationResult, absence_context: AbsenceContext
) -> str:
    payload = {
        "absence": dataclasses.asdict(absence_context),
        "eligible_candidates": [
            dataclasses.asdict(c) for c in classification_result.eligible_candidates
        ],
    }
    return (
        "Absence event and eligible candidate pool (JSON):\n"
        f"{json.dumps(payload, indent=2)}\n\n"
        "Return the ranked brief as JSON only, per the schema in your instructions."
    )


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json_text(text: str) -> str:
    """Pull a JSON object out of the model's text, tolerating code fences."""
    text = text.strip()
    match = _JSON_FENCE_RE.search(text)
    return match.group(1).strip() if match else text


def _parse_candidates(text: str) -> list[BriefCandidate]:
    json_text = _extract_json_text(text)
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise CoverageBriefError(
            f"Model response was not valid JSON: {exc}. Raw response: {text!r}"
        ) from exc

    if not isinstance(data, dict) or "candidates" not in data:
        raise CoverageBriefError(
            f"Model response JSON is missing the 'candidates' key. Got: {data!r}"
        )

    candidates_raw = data["candidates"]
    if not isinstance(candidates_raw, list):
        raise CoverageBriefError(
            f"'candidates' must be a list. Got: {candidates_raw!r}"
        )

    required_fields = ("staff_id", "score", "reasoning", "warning")
    candidates: list[BriefCandidate] = []
    for i, entry in enumerate(candidates_raw):
        if not isinstance(entry, dict):
            raise CoverageBriefError(f"candidates[{i}] is not an object: {entry!r}")
        missing = [f for f in required_fields if f not in entry]
        if missing:
            raise CoverageBriefError(
                f"candidates[{i}] is missing field(s) {missing}: {entry!r}"
            )
        try:
            score = float(entry["score"])
        except (TypeError, ValueError) as exc:
            raise CoverageBriefError(
                f"candidates[{i}]['score'] is not numeric: {entry['score']!r}"
            ) from exc
        candidates.append(
            BriefCandidate(
                staff_id=str(entry["staff_id"]),
                score=score,
                reasoning="" if entry["reasoning"] is None else str(entry["reasoning"]),
                warning="" if entry["warning"] is None else str(entry["warning"]),
            )
        )
    return candidates


def get_coverage_brief(
    classification_result: ClassificationResult,
    absence_context: AbsenceContext,
    client: anthropic.Anthropic | None = None,
) -> list[BriefCandidate]:
    """Get an AI-drafted, ranked coverage brief for a multi-candidate escalation.

    Only valid when classification_result.mode == "multi" (PRD Section 8:
    the API is called in exactly one code path). Any other mode raises
    ValueError immediately, before any network call.

    Args:
        classification_result: the result of classify_absence(); must have
            mode == "multi".
        absence_context: context about the absent employee, for the prompt.
        client: optional pre-built anthropic.Anthropic client (mainly for
            tests). Defaults to a client built from the resolved API key.

    Returns:
        A list of BriefCandidate, one per candidate the model ranked.

    Raises:
        ValueError: if classification_result.mode != "multi".
        CoverageBriefError: on a missing API key, an Anthropic API
            failure, or a malformed/unparseable model response.
    """
    if classification_result.mode != "multi":
        raise ValueError(
            "get_coverage_brief() may only be called for mode == 'multi' "
            f"(the genuine multi-candidate trade-off case); got mode={classification_result.mode!r}. "
            "Auto-resolve, escalate-none, and escalate-single must never call the API."
        )

    if client is None:
        api_key = _get_api_key()
        if not api_key:
            raise CoverageBriefError(
                "No Anthropic API key found. Set the ANTHROPIC_API_KEY "
                "environment variable."
            )
        client = anthropic.Anthropic(api_key=api_key)

    user_message = _build_user_message(classification_result, absence_context)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        raise CoverageBriefError(f"Anthropic API call failed: {exc}") from exc

    text_blocks = [block.text for block in response.content if block.type == "text"]
    if not text_blocks:
        raise CoverageBriefError(f"Model response had no text content: {response.content!r}")

    return _parse_candidates("\n".join(text_blocks))
