# Coverage Copilot

Sudden-absence coverage matching for a single hotel department manager. See
[`coverage-copilot-prd.md`](./coverage-copilot-prd.md) for the full product spec.

> **Status:** backend implemented (roster validation, deterministic classification,
> AI-drafted multi-candidate brief, REST API). No frontend yet — a React frontend is
> planned as a later step.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set your Anthropic API key as an environment variable (never commit it):

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Run the API:

```bash
uvicorn src.api:app --reload
```

The API is then available at `http://127.0.0.1:8000` (interactive docs at `/docs`).

## Deployment

Deployed from this GitHub repo, with `ANTHROPIC_API_KEY` set as an environment
variable on the host (never committed).
