# Deployment

Written for someone who has the repo and Docker — no third-party API keys required for the core demo path.

---

## Prerequisites

- Docker Engine 24+ and Docker Compose v2
- Roughly 4 GB free RAM for the full stack
- Free ports: `3000` (web), `8000` (api), `6379` (redis). Postgres is published on host port **5433** (not 5432) to avoid clashes.

---

## Run locally (copy-paste)

```bash
git clone https://github.com/AyushSid28/GridLocalizer.git
cd GridLocalizer
docker compose up --build
```

Compose sets database and Redis URLs inline; you do not need to copy `.env` for Docker. Use `.env.example` only if you run the API outside Compose.

Open http://localhost:3000. You should see network stats (poles, DTs, devices) and an empty incident list until you inject a fault.

Quick checks:

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/network/summary
```

---

## Environment variables

Committed template: `.env.example`.

| Name | Required | Default | Purpose |
|------|----------|---------|---------|
| `DATABASE_URL` | yes (compose sets it) | local Postgres URL | SQLAlchemy DSN |
| `REDIS_URL` | yes | `redis://redis:6379/0` | Telemetry stream |
| `TELEMETRY_STREAM` | no | `telemetry.inbound` | Redis stream key |
| `DETECT_WAIT_SEC` | no | `10` | Debounce before localize |
| `CORS_ORIGINS` | no | localhost Vite/web | Allowed browser origins |
| `GROQ_API_KEY` | no | empty | LLM explain (preferred) |
| `OPENAI_API_KEY` | no | empty | LLM explain fallback |
| `POSTGRES_USER` / `PASSWORD` / `DB` | compose | `outage` | Database bootstrap |

You do not need any LLM key for localization, ticketing, or repair verification.

---

## Verify it worked

1. Console loads; API status looks healthy.
2. Inject a span or DT fault from the UI (or `POST /sim/inject`).
3. One incident appears with scope, coordinates or PIN, and confidence.
4. Acknowledge → assign crew → repair the same scope (`POST /sim/repair` or UI).
5. After restore telemetry is ready, confirm repair; ticket moves to verified/closed.

---

## Reset to a clean state

```bash
docker compose down -v
docker compose up --build
```

The `-v` flag drops the Postgres volume so seed data runs again from scratch.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `docker compose` cannot connect | Docker Desktop not running | Start Docker and retry |
| API unhealthy / web 502 | Postgres not ready yet | Wait for healthchecks; `docker compose logs api` |
| Network summary shows `poles: 0` | Seed did not run or old volume | `docker compose down -v && docker compose up --build` |
| Missing column / schema errors after `git pull` | Old volume vs new models | Same volume reset (`create_all` does not migrate) |
| Port 3000 or 8000 in use | Another local service | Stop it or change published ports in compose |
| CORS errors from Vite on `:5173` | Origin not listed | Add origin to `CORS_ORIGINS` |
| Explain always shows fallback text | No Groq/OpenAI key | Expected; core flows work without LLM |
| Public URL feels dead on first open | Free-tier cold start | Wait 30–90 seconds (see [README](../README.md)) |
| Weird images on ARM Mac | Platform mismatch | Use stock `python:3.12-slim` / `node:22-alpine` as in compose |
| Worker idle, no incidents after inject | Stream/debounce timing | `docker compose logs worker`; wait `DETECT_WAIT_SEC` |
| Confirm repair returns 409 | Restore telemetry not seen yet | Run repair for the same scope; wait for UI “restoration telemetry ready” |

---

## Public deploy (sketch)

Any Docker-capable host works (Render, Railway, Fly, a small VM).

1. Set the same environment variables as in compose.
2. Expose the web service (nginx in the frontend image proxies `/health`, `/telemetry`, `/incidents`, `/sim`, `/network` to the API).
3. Put the public URL and demo video link in [README.md](../README.md).
4. On free tiers, document cold starts so reviewers do not assume an outage.

**This project:** frontend on Vercel, API and worker on Render (`render.yaml` sets `DETECT_WAIT_SEC=10`).
