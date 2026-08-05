# Decisions

Major trade-offs in **Chose / Rejected / Why** form, plus assumptions where the brief was silent.

---

## Groq first for explain, deterministic fallback always

**Chose:** Try Groq, then OpenAI, then a local paragraph built only from incident fields and reasons.

**Rejected:** LLM-only explanations; using an LLM for localization.

**Why:** Reviewers may not have API keys. Localization has to stay deterministic and testable.

---

## `true_parent_id` vs `parent_id`

**Chose:** The simulator follows ground-truth parents; the localizer walks `parent_id` (recorded or inferred).

**Rejected:** One parent column for both roles.

**Why:** We can demo inferred-topology mistakes honestly without corrupting the asset registry.

---

## Geo-infer plus DT degrade for missing wiring

**Chose:** When registry parents are blank, infer a tree from DT and pole GPS; lower confidence; if the whole subtree is dark, report DT level.

**Rejected:** Pretend wiring is complete; block the product until a survey finishes.

**Why:** Roughly 60% of DTs lack ordering in the brief. Fake span precision would erode operator trust.

---

## Redis Streams, not Kafka

**Chose:** Redis Streams between ingest and the worker.

**Rejected:** Kafka; running localization inside the HTTP handler.

**Why:** The load profile (~39 msg/s steady, bursts to thousands in ten seconds) does not need Kafka ops. Synchronous localize on POST would fail the burst story.

---

## Sync SQLAlchemy and `create_all` on boot

**Chose:** Sync sessions; create tables at startup.

**Rejected:** Alembic as a manual reviewer step; full async on day one.

**Why:** `docker compose up` alone must satisfy gate G2.

---

## FastAPI plus Vite React in one repo

**Chose:** Python for the algorithm; thin React console; one compose file.

**Rejected:** Next.js full-stack; microservices per concern.

**Why:** Localization is easier to test and walk through in Python. The UI is a control room, not an engineering dashboard.

---

## Assumptions where the brief was ambiguous

- Debounce default around **10–30 seconds** — prefer trustworthy grouping over instant noisy tickets; still well under a two-minute style SLO.
- Polling the console every few seconds is acceptable; WebSockets are not required.
- A hardcoded operator identity is enough; auth is out of scope.
- A synthetic network on the order of ~3k poles and ~48 DTs, with ~40% wiring known is enough to show the hard parts.
