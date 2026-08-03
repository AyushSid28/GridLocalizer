# Outage Fault Localizer

Control-room system for a radial LT distribution network. Pole IoT devices report only live/dark. The backend infers the failed **span** (or DT/feeder), opens one ticket per fault, and closes it only after telemetry shows power restored.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

| What | URL |
|------|-----|
| Operator console | http://localhost:3000 |
| API health | http://localhost:8000/health |
| OpenAPI | http://localhost:8000/docs |

First boot seeds a synthetic network (thousands of poles). Cold start on free hosts can take a minute — wait before assuming it is broken.

## Public demo

- **Live URL:** _(add after deploy)_
- **Demo video:** _(add Loom / YouTube link)_

## How to try a fault

From the console simulator, inject a **span** / **DT** / **feeder** fault, or:

```bash
curl -s -X POST http://localhost:8000/sim/inject \
  -H 'Content-Type: application/json' \
  -d '{"kind":"span","dt_id":"D-0001"}'
```

Watch the incident list. Repair from the UI or `POST /sim/repair`. The ticket should auto-verify when poles report live again.

## Docs (required)

| File | Contents |
|------|----------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Data flow, localization, APIs, AI feature |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Env vars, runbook, troubleshooting |
| [DECISIONS.md](DECISIONS.md) | Trade-offs and assumptions |
| [AI-WORKFLOW.md](AI-WORKFLOW.md) | How AI was used while building |

## Stack

FastAPI · Redis Streams · PostgreSQL · React/Vite · Docker Compose

LLM explain (optional): set `GROQ_API_KEY` or `OPENAI_API_KEY`. Without a key, explain falls back to a deterministic summary.
