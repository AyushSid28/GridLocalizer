# DECISIONS

Newest first.

---

## 2026-08-02 — Monorepo layout

**Chose:** `backend/` (FastAPI) + `frontend/` (Vite React) + root `docker-compose.yml`.

**Rejected:** Next.js full-stack, separate microservice per concern.

**Why:** One Python process owns localization (easier to test and explain). Frontend stays a thin console. Compose stays reviewable.

---

## 2026-08-02 — Sync SQLAlchemy + psycopg3

**Chose:** Sync sessions, `create_all` on startup.

**Rejected:** Alembic from day one, async SQLAlchemy everywhere.

**Why:** Reviewer must not run migrations by hand. Async adds noise before we have load that needs it.
