# Analytics Frontend (React SPA)

React + Vite + TypeScript single-page app that replaces the Streamlit analytics
dashboard. It talks to the FastAPI service in [`../api`](../api) over REST and
renders JSON series client-side (Recharts + Plotly.js per the WebGL split in the
design spec). See `docs/fastapi_react_migration_spec.md`.

**Status: Phase 0 scaffold.** Only the `HealthGate` (DB-exists probe) is wired;
the six business views land in later phases (ETF Prices first).

## Dev run (two processes)

From the repo root, start the API first:

```bash
uvicorn api.main:app --reload --port 8000      # serves /api/v1, /docs, /openapi.json
```

Then the SPA:

```bash
cd frontend
npm install
npm run dev                                    # Vite on :5173, proxies /api -> :8000
```

The dev proxy (`vite.config.ts`) forwards `/api` to the API, so CORS does not
bite in dev. To point at a non-proxied API, set `VITE_API_BASE_URL` (see
`.env.example`).

## Scripts

| Script | Purpose |
|---|---|
| `npm run dev` | Vite dev server (HMR) on :5173 |
| `npm run build` | Type-check (`tsc -b`) then production `vite build` to `dist/` |
| `npm run typecheck` | Type-check only |
| `npm run gen:api` | Regenerate `src/api/schema.d.ts` from the live OpenAPI schema (API must be running) |

## Type safety

`npm run gen:api` regenerates TypeScript types from the API's live
`/openapi.json` (spec §7.4) so the Python contract drives the TS types -- drift
becomes a compile error, the frontend analogue of the repo's pyright check on
`EngineContext`.
