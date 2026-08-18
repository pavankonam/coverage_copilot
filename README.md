# Coverage Copilot

Sudden-absence coverage matching for a single hotel department manager. See
[`coverage-copilot-prd.md`](./coverage-copilot-prd.md) for the full product spec.

> **Status:** project scaffolding only. UI and business logic are not yet implemented.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the secrets template and fill in your own key (never commit the real file):

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Run the app:

```bash
streamlit run src/app.py
```

## Deployment

Deployed via [Streamlit Community Cloud](https://streamlit.io/cloud) pointed at this
GitHub repo, with `ANTHROPIC_API_KEY` set as a Streamlit Cloud secret (never committed).
