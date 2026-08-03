# DEPLOYMENT

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- ~4 GB free RAM for the full stack
- Ports free: `3000` (web), `8000` (api), `5432` (postgres), `6379` (redis)

## Run locally

```bash
git clone <your-repo-url>
cd <repo>
cp .env.example .env
docker compose up --build
```

Open http://localhost:3000. You should see network stats (poles / DTs / devices) and an empty incident list until you inject a fault.

API check:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/network/summary
```

## Environment variables

Committed template: `.env.example`.

| Name | Required | Default | Purpose |
|------|----------|---------|---------|
| `DATABASE_URL` | yes (compose sets it) | local Postgres URL | SQLAlchemy DSN |
| `REDIS_URL` | yes | `redis://redis:6379/0` | Telemetry stream |
| `TELEMETRY_STREAM` | no | `telemetry.inbound` | Redis stream key |
| `DETECT_WAIT_SEC` | no | `30` | Debounce before localize |
| `CORS_ORIGINS` | no | localhost Vite/web | Allowed browser origins |
| `GROQ_API_KEY` | no | empty | LLM explain (preferred) |
| `OPENAI_API_KEY` | no | empty | LLM explain fallback |
| `POSTGRES_USER` / `PASSWORD` / `DB` | compose | `outage` | Database bootstrap |

The app runs without any LLM key.

## Verify end-to-end

1. Console loads, API pill is green.
2. Inject a span fault from the UI (or `POST /sim/inject`).
3. Exactly one incident appears with span / coords / PIN / confidence.
4. Acknowledge → assign → repair (or `POST /sim/repair`).
5. Ticket moves to verified/closed from telemetry without faking close.

## Reset to a clean state

```bash
docker compose down -v
docker compose up --build
```

`-v` drops the Postgres volume so seed runs again.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `docker compose` cannot connect | Docker Desktop not running | Start Docker, retry |
| API unhealthy / web 502 | Postgres not ready yet | Wait for healthchecks; `docker compose logs api` |
| Empty network summary (`poles: 0`) | Seed did not run or volume from old schema | `docker compose down -v && up --build` |
| Schema / missing column errors after pull | Old volume vs new models | Reset volume as above (`create_all` does not migrate) |
| Port 3000 / 8000 in use | Local process conflict | Stop the other process or change published ports in compose |
| CORS errors from Vite on `:5173` | Origin not listed | Add it to `CORS_ORIGINS` |
| Explain returns only fallback text | No `GROQ_API_KEY` / `OPENAI_API_KEY` | Expected; core product works without LLM |
| Free-host URL looks dead | Cold start | Wait 30–90s; noted in README |
| ARM Mac image weirdness | Platform mismatch | Use stock `python:3.12-slim` / `node:22-alpine` (compose as shipped) |
| Worker idle forever, no incidents | Inject not reaching stream / debounce | Check `docker compose logs worker`; wait `DETECT_WAIT_SEC` |

## Public deploy (sketch)

Any Docker host works (Railway / Render / Fly / a VM).

1. Set the same env vars as compose.
2. Expose the `web` service (nginx already proxies `/health`, `/telemetry`, `/incidents`, `/sim`, `/network` to the API).
3. Put the public URL and demo video link in `README.md`.
4. Expect cold starts on free tiers; document the wait.
