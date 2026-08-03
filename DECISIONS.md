# DECISIONS

Newest first.

---

## 2026-08-04 — Groq first for explain, deterministic fallback always

**Chose:** Try Groq, then OpenAI, then a local paragraph from incident fields/reasons.

**Rejected:** LLM-only explanations; LLM localization.

**Why:** Reviewers may have no key. Localization must stay deterministic and testable.

---

## 2026-08-03 — `true_parent_id` vs `parent_id`

**Chose:** Simulator faults follow ground-truth parents; localizer walks `parent_id` (recorded or inferred).

**Rejected:** One parent column for both.

**Why:** Honest demo of inferred-topology error modes without lying in the asset registry.

---

## 2026-08-03 — Geo-infer + DT degrade for missing wiring

**Chose:** Infer a tree from DT/pole GPS when registry parents are blank; lower confidence; DT-level when the whole subtree is dark.

**Rejected:** Assume complete wiring; survey-only with no interim product.

**Why:** ~60% of DTs lack parents in the brief. Fake span precision destroys operator trust.

---

## 2026-08-02 — Redis Streams, not Kafka

**Chose:** Redis Streams between ingest and worker.

**Rejected:** Kafka; localize inside the request.

**Why:** ~39 msg/s steady and 5k/10s bursts. Kafka is ops theater at this scale. Sync localize in HTTP fails the burst story.

---

## 2026-08-02 — Sync SQLAlchemy + `create_all` on boot

**Chose:** Sync sessions; create tables on startup.

**Rejected:** Alembic as a manual reviewer step; full async stack on day one.

**Why:** `docker compose up` must be enough (gate G2).

---

## 2026-08-02 — FastAPI + Vite React monorepo

**Chose:** Python API for the algorithm; thin React console; one compose file.

**Rejected:** Next.js full-stack; microservices per concern.

**Why:** Localization tests and interview walkthroughs are clearer in Python. UI stays a control room, not an eng dashboard.

---

## Assumptions (brief was ambiguous)

- Debounce default **30s** — trust over instant noisy alerts; still ≪ 120s SLO.
- Polling the console every few seconds is fine (no WebSockets required).
- Hardcoded operator identity is enough (auth out of scope).
- Synthetic network ~3k poles, ~48 DTs, ~40% wiring known is enough shape fidelity.

---

## Two more weeks

- Measure ingest burst and publish real numbers in README.
- Learn topology edges from co-dark history.
- Harden schedule soft-suppress with overrun buffers and cancel detection.
- Deploy URL + polished demo video.

## Known fragile / wrong

- Geo-infer can pick the wrong parent in dense clusters.
- Schema changes need `docker compose down -v` (`create_all` does not migrate).
- Free-tier cold starts can look like an outage if undocumented.
- Some early commit messages still say “P0/P1”; newer ones are plain language.
