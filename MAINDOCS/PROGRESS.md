# PROGRESS HANDOFF — Continuity File

**Purpose:** If this chat/context dies, paste this file (or `@PROGRESS.md`) into a new chat and continue without re-deriving the project.

**Last updated:** 2026-08-02  
**Update rule:** After every meaningful step, edit the checkboxes + “Current position” + “Next action” at the top.

---

## CURRENT POSITION (read this first)

```
Phase:          P8 DONE — LLM Incident Explanation and Fallback implemented and verified
Last finished:  P8 — LLM summary (Explain Incident detail generator, grounded in deterministic outputs)
Next action:    P9 — Deploy + video (Compose hardening, public URL setup, demo video preparation)
Blocked by:     None (Docker running)
Active branch:  local workspace /Users/ayushsiddhant/Desktop/assignment
Stack locked:   FastAPI + Redis Streams + PostgreSQL + React/Vite + Leaflet + Docker Compose
```

---

## ONE-PARAGRAPH PROJECT BRIEF (for new LLM)

Build an Intelligent Fault Localization Platform for a fictional Karnataka ESCOM. Pole IoT devices report only LIVE/DARK. Network is a radial tree. Infer EDGE (span) failures from NODE states. Produce one ticket per fault, handle missing topology (~60% DTs), suppress sensor failures and scheduled outages, auto-verify restoration from telemetry. Ship: docker compose one-command, public URL, fault simulator, operator console, 5 docs, demo video. Time budget 15–20h. Do NOT use LLM for localization. Evaluation weights: localization 25%, product 20%, architecture 20%, UX 15%, docs 15%, craft 5%.

Assignment source docs live in this folder: `00`–`05` markdown briefs.

---

## FILES THAT MATTER

| File | What it is |
|------|------------|
| `00-candidate-brief.md` … `05-faq.md` | Official assignment (read-only source of truth) |
| `ARCHITECTURE.md` | Full technical architecture + interview defense |
| `PLAN.md` | Phased P0–P10 hour plan |
| `CHECKLIST.md` | Gates, rubric ticks, self-check |
| `FLOWCHARTS.md` | Detailed product/telemetry flow diagrams |
| `PROGRESS.md` | **This file** — handoff + progress |
| `docssssssss.docx` | Candidate’s own study notes (optional) |

**Not created yet:** full seed/localization/sim code, `DEPLOYMENT.md`, `AI-WORKFLOW.md`

**Created:** `backend/`, `frontend/`, `docker-compose.yml`, `.env.example`, `README.md`, `DECISIONS.md`


---

## KEY DECISIONS ALREADY LOCKED

- [x] Tree / frontier localization (not per-pole alerts)
- [x] Missing topology: geo-infer + degrade to DT-level + honest confidence (not pretend complete)
- [x] Debounce ~20–45s before incident
- [x] Redis Streams buffer; no Kafka
- [x] Single service style (api + worker); no microservices
- [x] Polling UI 3–5s (not WebSocket-first)
- [x] AI = grounded incident summary only
- [x] Simulator shares same `/telemetry` path
- [x] Ticket close only after telemetry verify

---

## PHASE PROGRESS

### Docs / design
- [x] Read all assignment docs
- [x] ARCHITECTURE.md
- [x] PLAN.md
- [x] CHECKLIST.md
- [x] FLOWCHARTS.md
- [x] PROGRESS.md (this)
- [ ] DECISIONS.md (start when coding choices happen)
- [ ] README / DEPLOYMENT / AI-WORKFLOW (P10)

### P0 — Scaffold (~1.5h)
- [x] Repo layout `backend/` `frontend/`
- [x] docker-compose: postgres, redis, api, worker, web
- [x] FastAPI `/health`
- [x] DB models stub / create_all on boot
- [x] Empty Vite React app builds in compose
- [x] `.env.example`
- [ ] `docker compose up` verified on this machine (Docker was not running)


### P1 — Synthetic network + topology (~2.5h)
- [x] Generator (few thousand poles, ratios correct)
- [x] Seed on empty DB
- [x] Recorded + inferred topology + `topology_source`
- [x] In-memory adjacency cache


### P2 — Ingest + state (~2h)
- [x] `POST /telemetry` → Redis → 202
- [x] Worker dedup `(device_id, seq)`
- [x] `device_state` updates
- [x] Burst smoke test noted

### P3 — Localization + tests (~3.5h) ★ critical

- [x] Debounced detector
- [x] span / dt / feeder / sensor_failure
- [x] Grouping = one incident per frontier
- [x] Multi-fault → multi tickets
- [x] Confidence + reasons
- [x] PIN helper (no reviewer key)
- [x] Pytest fixtures green (see PLAN P3 table)


### P4 — Noise + schedule (~1.5h)
- [x] Scheduled outage mock + soft suppress
- [x] Firmware-aware silence
- [x] Dead sensor → no outage ticket


### P5 — Tickets + verify (~2h)
- [x] FSM: detected→ack→assigned→resolved→verified→closed
- [x] Resolve-while-dark pushback
- [x] Auto-verify on restore telemetry


### P6 — Simulator (~2h)
- [x] Inject span/DT/feeder
- [x] Realistic messy telemetry
- [x] Noise inject
- [x] Repair → restore msgs
- [x] Drivable from UI


### P7 — Operator console (~2.5h)
- [x] Incident list + map + detail
- [x] Confidence / topology badge
- [x] Ticket actions
- [x] Sim controls in UI
- [x] Polling


### P8 — LLM summary (~1h, cuttable)
- [x] Grounded summary from JSON
- [x] Degrades without API key


### P9 — Deploy + video (~2h)
- [ ] Compose hardened
- [ ] Public URL live
- [ ] Demo video recorded
- [ ] Fresh-clone verify

### P10 — Docs pass (~1.5h)
- [ ] Five root markdowns match code
- [ ] Submit email draft

---

## GATES (must be green before submit)

- [ ] G1 Public GitHub
- [ ] G2 docker compose up from clean clone
- [ ] G3 Seeded on startup
- [ ] G4 Public URL no login
- [ ] G5 Simulator works for reviewer
- [ ] G6 Demo video

---

## SELF-CHECK (official)

- [ ] Fresh clone compose works
- [ ] Private window URL works
- [ ] Span → exactly 1 ticket + PIN
- [ ] 3 faults → 3 tickets
- [ ] Dead device (power on) → no fault ticket
- [ ] Schedule → no fault ticket
- [ ] Repair → auto-verify
- [ ] False resolve → rejected
- [ ] Docs match code
- [ ] No secrets in git
- [ ] Can explain every file

---

## NEW CHAT STARTER PROMPT (copy-paste)

```
Continue the Karnataka ESCOM Fault Localization assignment in /Users/ayushsiddhant/Desktop/assignment.

Read PROGRESS.md first for current position and next action.
Then read FLOWCHARTS.md for product flow and ARCHITECTURE.md / PLAN.md as needed.

Rules: do not overengineer; no Kafka; no LLM localization; follow PLAN phases; update PROGRESS.md after each step.

Next action is whatever PROGRESS.md says under CURRENT POSITION.
```

---

## SESSION LOG (newest first)

| When | What happened |
|------|----------------|
| 2026-08-02 | P0 scaffold: backend models/API, frontend shell, compose; frontend build OK; Docker daemon unavailable |
| 2026-08-02 | Created FLOWCHARTS.md (detailed fault→telemetry→ticket flows) |
| 2026-08-02 | Created PROGRESS.md handoff tracker |
| 2026-08-02 | Created ARCHITECTURE.md, PLAN.md, CHECKLIST.md |
| 2026-08-02 | Studied briefs 00–05 + personal docx notes; stack locked |

---

## NOTES / ASSUMPTIONS TO REMEMBER

- Debounce 20–45s is intentional (trust > instant noisy alert); still ≪ 120s SLO.
- Geo-infer can be wrong → UI must show inferred/DT-level, never fake certainty.
- `pole_id` is asset key; `device_id` can change.
- Device clocks unreliable; use `(device_id, seq)` + server receive time.
- fw 1.2 never sends `power_lost` — silence after heartbeat miss matters.
- Cut order if late: LLM → map chrome → extras. Never cut: localize, verify, sim, docker, URL, video.
