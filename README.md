# Outage Fault Localizer

Intelligent fault localization for a radial LT distribution network.

## Quick start

```bash
cp .env.example .env
docker compose up --build
```

- Operator console: http://localhost:3000
- API health: http://localhost:8000/health
- OpenAPI: http://localhost:8000/docs

## Status

P0 scaffold is up. Seed network, ingest queue, and localization are next — see `PROGRESS.md`.

## Docs

| File | Contents |
|------|----------|
| `ARCHITECTURE.md` | Design |
| `PLAN.md` | Build phases |
| `CHECKLIST.md` | Gates / rubric |
| `FLOWCHARTS.md` | Product flows |
| `PROGRESS.md` | Handoff tracker |
| `DECISIONS.md` | Decision log |
