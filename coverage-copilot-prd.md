# Coverage Copilot — Product Requirements Document (v1)

## 1. Overview

When a hotel employee has a sudden, unplanned absence (sick leave, same-day PTO), a manager currently has to manually find coverage. Coverage Copilot resolves this automatically when the answer is unambiguous, and hands the manager a ready-to-decide brief when it isn't — it never makes the judgment call itself in ambiguous cases, and it never decides whether the absence is "allowed."

## 2. Goals (In Scope)

- A backend service for sudden absence coverage matching (see Section 9 for the current stack).
- CSV upload of roster + weekly schedule (no manual data entry screen required for v1).
- Deterministic auto-resolve for unambiguous, policy-clean matches.
- Escalation to a human decision for everything else. An AI-drafted brief is used **only** in the genuine multi-candidate trade-off case.
- A ledger recording every resolution (auto and manual) with its reasoning.
- Deployable from GitHub.

## 3. Non-Goals (Explicitly Out of Scope for v1)

- Room, event space, or asset scheduling.
- Guest-facing bookings (spa, dining, activities).
- Cross-property / multi-hotel logic.
- Employee login or per-user auth — v1 is a single shared manager view.
- Any automatic approval or denial of the leave itself. The system never decides whether someone is allowed to be out — only whether coverage can be found.
- A persistent database. v1 uses in-memory/session state only.
- Slack/Teams/mobile integration.
- Predictive or forecasting features (e.g., anticipating future gaps).

**If it's not in Section 2, don't build it — flag it as a future idea instead.**

## 4. Users

A single hotel department manager persona, using the app directly in-browser.

## 5. Data Input — CSV Schema

One CSV upload. Required columns:

| Column | Type | Notes |
|---|---|---|
| staff_id | string | unique |
| name | string | |
| role | string | |
| department | string | one of a configurable fixed list, e.g. Front Desk, Housekeeping, F&B, Concierge |
| weekly_cap_hours | integer | ≥ 0 |
| sick_balance_hours | integer | ≥ 0 |
| unavailable_days | string | comma-separated subset of Mon,Tue,Wed,Thu,Fri,Sat,Sun; may be empty |
| Mon, Tue, Wed, Thu, Fri, Sat, Sun | string | each one of M, A, E, OFF |

**Validation rules:** all required columns present; shift values restricted to {M, A, E, OFF}; hour fields numeric and non-negative; department in the allowed list; unavailable_days values are valid day names. Invalid rows are reported to the user, not silently dropped or auto-corrected.

The app must offer a downloadable sample template CSV with a few valid example rows.

## 6. Core Logic — Deterministic Classification

**This rule tree is the product's core IP. Implement it exactly as written — no added heuristics, no "improvements."**

Given an absence event (staff_id, day):

1. **Eligible pool** = all other staff where `schedule[day] == OFF` AND `day not in unavailable_days`.
2. For each eligible candidate, compute:
   - `same_department` (bool)
   - `hours_scheduled` = sum of non-OFF shifts × 8
   - `would_overtime` = `hours_scheduled + 8 > weekly_cap_hours`
3. `clean_matches` = eligible candidates where `same_department` AND NOT `would_overtime`.
4. `balance_flag` = the absent employee's `sick_balance_hours < 8`.

**Decision (in this order):**

- If `balance_flag` → **ESCALATE** (mode = none/single/multi based on eligible count). Note: low balance, flagged for review.
- Else if eligible count == 0 → **ESCALATE**, mode = none. Note: no internal coverage found.
- Else if `clean_matches` count == 1 → **AUTO-RESOLVE** to that one candidate. No AI call.
- Else if `clean_matches` count == 0 → **ESCALATE**, mode = single if eligible count == 1, else multi. Note: no clean same-department match without overtime.
- Else (`clean_matches` count ≥ 2) → **ESCALATE**, mode = multi. Note: N qualified matches, manager's call.

## 7. User Flows / Screens

- **A — Upload:** file uploader, sample template download, inline validation errors.
- **B — Schedule board:** weekly grid (staff × day) from the uploaded data. Clicking a filled cell opens an absence-report form (free-text reason).
- **C — Coverage board:** visual list of open/resolved coverage events. Auto-resolved events show a distinct "Auto" badge; manually-resolved events show a distinct "Approved by you" badge. These two must be visually distinguishable at a glance.
- **D — Pending review:** for escalate-single and escalate-multi, shows the escalation note plus candidate(s) and a manual Assign action. Escalate-none shows a static message with no assign action available.
- **E — Ledger:** chronological log of resolved events, each tagged with its resolution mode (auto/manual) and the reason for absence.

## 8. LLM Integration Scope (narrow — read carefully)

- The Anthropic API (model `claude-sonnet-4-6`) is called in **exactly one** code path: escalate-multi.
- It is **never** called for auto-resolve, escalate-none, or escalate-single. This must be enforced at the code level (e.g., the API-calling function is only reachable from the multi-candidate branch) — not just true by convention. Add a test asserting the other three paths make zero API calls.
- System prompt instructs the model to rank candidates and briefly explain trade-offs and overtime risk. It must **not** claim to authorize or assign anyone — output is JSON only: `{"candidates":[{"staff_id","score","reasoning","warning"}]}`.
- API key is read from `st.secrets["ANTHROPIC_API_KEY"]` or the `ANTHROPIC_API_KEY` environment variable. Never hardcoded, never committed to the repo.
- API failures must be handled gracefully (a retry action) — never crash the app.

## 9. Tech Stack & Deployment

- Python, FastAPI, pandas, the official `anthropic` SDK. A separate React frontend
  is planned as a later step; no Streamlit.
- Repo hosted on GitHub.
- `ANTHROPIC_API_KEY` set as an environment variable, never committed.
- Pinned `requirements.txt`. README with local run instructions and deploy steps.

## 10. Acceptance Test Scenarios (must all pass)

1. **Auto-resolve:** exactly one same-department, non-overtime, available colleague, sufficient balance → system auto-assigns; zero API calls made.
2. **Escalate — balance flag:** sick balance < 8h, even with an otherwise clean match available → escalates; zero API calls; balance note shown.
3. **Escalate — multi-candidate:** two or more eligible candidates → escalates; exactly one API call; ranked brief shown; manual Assign required.
4. **Escalate — no match:** zero eligible candidates → escalates; zero API calls; static message only.
5. **Escalate — overtime-only single:** exactly one eligible candidate, but assigning them causes overtime → escalates; zero API calls; single candidate shown with overtime warning and manual Assign.

## 11. Reminder for the builder

This is v1 of the sick-leave / sudden-absence coverage module only. Do not generalize to rooms, events, guests, or cross-property logic, even if it looks like natural reuse — that boundary is intentional, not an oversight.

## 12. Extension — REST API surface & effective schedule (post-v1, not in Sections 1–11)

**Sections 1–11 above are not the complete picture.** This section documents functionality added after the original v1 scope was written — a deliberate extension, built out on top of the FastAPI backend described in Section 9, not a restatement of it and not a port of the old Streamlit screens (Section 7). A future session should read this section too, not just Sections 1–11.

### API surface (`src/api.py`)

- **`POST /roster`** — upload a roster CSV, run it through `data_layer.load_and_validate_roster` (unmodified), store the resulting clean roster, and reset both the effective schedule (below) and the event list from it. Returns validation errors or a success/staff-count summary — never silently drops invalid rows, per Section 5.
- **`POST /absences`** — classify a reported absence via `classification.classify_absence` (unmodified). Every classification, not just multi-mode, is now stored as an event with a generated id, in creation order:
  - `decision == "auto"` → resolved immediately; the assigned candidate is recorded as `covered_by`, and the effective schedule updates immediately.
  - `decision == "escalate"` → stored pending. `mode == "multi"` still triggers exactly one `get_coverage_brief()` call (Section 8 is unchanged — still the only code path that reaches the Anthropic API) and returns the ranked candidates in this same response; the event itself stays unresolved until a human resolves it via `POST /events/{id}/assign`.
- **`GET /events`** — the full event list, oldest first: id, staff_id/day/reason, decision/mode/note, eligible_candidates/clean_matches, resolved/resolution/covered_by, and (multi-mode only) the cached ranked candidates.
- **`GET /schedule`** — the original uploaded schedule and the current effective schedule, side by side.
- **`POST /events/{event_id}/assign`** — manually resolve a pending event by assigning a covering staff_id. 404 for an unknown event id, 409 if already resolved, 400 if the event's mode is `"none"` (no eligible candidates exist to assign — consistent with Section 7's "escalate-none shows... no assign action available") or the given staff_id isn't in the roster.

### Effective schedule (new concept)

Separate from the originally-uploaded schedule. Every resolution — auto or manual — updates it: the covering person's day flips from `OFF` to the shift they're now covering (the absent person's originally-scheduled shift that day); the absent person's day flips to `OFF`, **and that day is added to the absent person's `unavailable_days` in the effective schedule** (not the original roster) — see below for why. It is a derived record of who is actually covering what, built from resolutions — but see below, it is not merely informational anymore.

**The effective schedule is the source of truth for classification, not the original upload.** `classify_absence`'s rule tree itself is unchanged (Section 6, still not to be modified) — but `POST /absences` now feeds it the *effective* schedule, not the originally-uploaded one. Concretely: eligibility (`schedule[day] == OFF`) and every candidate's `hours_scheduled`/`would_overtime` reflect anyone already covering another shift, not just what they were originally scheduled for. A person who has already picked up one covering shift on a given day is therefore excluded from being offered again for a different absence that same day — or, if their week is now busier, may instead show up correctly overtime-flagged rather than as a clean match. (`POST /events/{event_id}/assign` does not call `classify_absence` at all — it never did, and still doesn't; it only validates the assigned staff_id exists, now checked against the effective schedule too for consistency, though the two always share the same staff_id membership so this has no observable effect.) `_apply_coverage()`'s own lookup of *which shift is being covered* is unaffected by this and still reads the originally-uploaded schedule — the covering person needs the shift the absent person actually had that day, not whatever the absent person's now-mutated effective cell says.

Uploading a new roster (`POST /roster`) resets the effective schedule to a fresh copy of it, and clears the event list — events and coverage recorded against a previous roster don't carry forward.

**Known, deliberate gap — sick-balance depletion is not tracked.** `sick_balance_hours` is never decremented anywhere in this system: not by `classify_absence` (unmodified, Section 6 has no such rule) and not by this API layer, which never mutates that column. A person's balance is the same static number on every absence they're ever involved in — someone flagged low-balance on their first absence this quarter is flagged identically (not more, not less) on every later one, and someone with a comfortably high balance never gets flagged no matter how many absences accumulate. This is a known gap, not an oversight; fixing it would mean adding a mutation this PRD doesn't yet specify, and is out of scope here.

**Fixed — an absence is no longer indistinguishable from a day off, in the effective schedule.** The schema (Section 5) still only has `OFF` for "not scheduled to work" — there's still no distinct shift-code for "was scheduled, but is out sick," and none was added. Instead, `_apply_coverage()` now also writes the resolved day into the absent person's `unavailable_days` cell in the effective schedule (parsed/joined the same comma-separated way Section 5 already specifies for that column). `classify_absence`'s existing, unmodified eligibility check already excludes any candidate with `day in unavailable_days` (Section 6) — so an absent person's `OFF` cell alone no longer makes them look available to cover someone else the same day; the `unavailable_days` entry is what actually excludes them. This was previously an open gap (see prior revisions of this section); it's closed as of this change, at the effective-schedule-data level only — `classification.py` and the CSV schema are both untouched.
