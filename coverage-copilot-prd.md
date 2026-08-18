# Coverage Copilot — Product Requirements Document (v1)

## 1. Overview

When a hotel employee has a sudden, unplanned absence (sick leave, same-day PTO), a manager currently has to manually find coverage. Coverage Copilot resolves this automatically when the answer is unambiguous, and hands the manager a ready-to-decide brief when it isn't — it never makes the judgment call itself in ambiguous cases, and it never decides whether the absence is "allowed."

## 2. Goals (In Scope)

- A single Streamlit app for sudden absence coverage matching.
- CSV upload of roster + weekly schedule (no manual data entry screen required for v1).
- Deterministic auto-resolve for unambiguous, policy-clean matches.
- Escalation to a human decision for everything else. An AI-drafted brief is used **only** in the genuine multi-candidate trade-off case.
- A ledger recording every resolution (auto and manual) with its reasoning.
- Deployable from GitHub to Streamlit Community Cloud.

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

- Python, Streamlit, pandas, the official `anthropic` SDK.
- Repo hosted on GitHub; deployed via Streamlit Community Cloud pointed at that repo.
- `ANTHROPIC_API_KEY` set as a Streamlit Cloud secret, never committed.
- Pinned `requirements.txt`. README with local run instructions and deploy steps.

## 10. Acceptance Test Scenarios (must all pass)

1. **Auto-resolve:** exactly one same-department, non-overtime, available colleague, sufficient balance → system auto-assigns; zero API calls made.
2. **Escalate — balance flag:** sick balance < 8h, even with an otherwise clean match available → escalates; zero API calls; balance note shown.
3. **Escalate — multi-candidate:** two or more eligible candidates → escalates; exactly one API call; ranked brief shown; manual Assign required.
4. **Escalate — no match:** zero eligible candidates → escalates; zero API calls; static message only.
5. **Escalate — overtime-only single:** exactly one eligible candidate, but assigning them causes overtime → escalates; zero API calls; single candidate shown with overtime warning and manual Assign.

## 11. Reminder for the builder

This is v1 of the sick-leave / sudden-absence coverage module only. Do not generalize to rooms, events, guests, or cross-property logic, even if it looks like natural reuse — that boundary is intentional, not an oversight.
