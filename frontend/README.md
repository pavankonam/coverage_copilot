# Coverage Copilot — frontend

React (Vite, plain JavaScript) frontend for Coverage Copilot. See the
[root README](../README.md) and
[`coverage-copilot-prd.md`](../coverage-copilot-prd.md) for the product spec
and backend API.

> **Status:** connectivity proof only. On load, the page fetches `GET
> /schedule` from the deployed backend and displays the result (or a "no
> roster loaded yet" message) -- nothing else is built here yet.

## Local setup

```bash
cd frontend
npm install
cp .env.example .env   # adjust VITE_API_BASE_URL if pointing at a local backend
npm run dev
```

Then open the URL Vite prints (typically `http://localhost:5173`).

## Configuration

`VITE_API_BASE_URL` (see `.env.example`) is the single source of truth for
the backend's base URL -- set once, read via `import.meta.env.VITE_API_BASE_URL`
in `src/App.jsx`, never hardcoded elsewhere.
