# CHECKLIST — Gates, rubric, and self-check

Use this before every “are we done?” moment. Tick only what you have **proven**, not planned.

---

## A. Acceptance gates (pass/fail — unscored if any fail)

| ID | Requirement | Evidence | ☐ |
|----|-------------|----------|---|
| G1 | Public GitHub repo, clone without access grant | Repo URL in submit email | ☐ |
| G2 | `git clone && docker compose up` brings full stack | Fresh directory test on your machine | ☐ |
| G3 | Seeded synthetic network on startup | UI shows poles/incidents capability immediately | ☐ |
| G4 | Public URL, no account/VPN/reviewer API key | Private/incognito browser open | ☐ |
| G5 | Simulator from URL or one documented command; inject → localized ticket | Demo path written in README | ☐ |
| G6 | ≤5 min demo video: inject→detect→localize→ticket→repair→auto-verify | Loom/YT/Drive link | ☐ |

**Cold start:** If free tier sleeps, README says “wait N seconds” — still tick G4 only if it comes up.

---

## B. Rubric coverage (optimize hours here)

### B1. Fault localization — 25%

| Item | ☐ |
|------|---|
| Live/dark frontier finds **edge**, not “dark pole” | ☐ |
| Many dark poles → **one** incident | ☐ |
| Multiple simultaneous faults → multiple incidents | ☐ |
| Span / DT / feeder classes distinguished | ☐ |
| 60% missing topology: explicit strategy + UI honesty | ☐ |
| Confidence + machine reasons (not vibes) | ☐ |
| Robust to missing / duplicate / late / OOOrder telemetry | ☐ |
| Pytest fixtures for known topologies (see PLAN P3) | ☐ |

### B2. Product judgment — 20%

| Item | ☐ |
|------|---|
| Solved department problem (localize + verify), not shiny extras | ☐ |
| False positives taken seriously (sensor, schedule) | ☐ |
| AI feature earns keep **or** written argument for none | ☐ |
| LLM does **not** perform localization | ☐ |
| Out-of-scope items not built instead of core | ☐ |

### B3. Architecture & data — 20%

| Item | ☐ |
|------|---|
| Ingest survives burst (measured or honestly missed) | ☐ |
| Topology representation documented and implemented | ☐ |
| Schema quality; `pole_id` as asset key | ☐ |
| API table / OpenAPI matches code | ☐ |
| Know what breaks at 30 subdivisions | ☐ |

### B4. Operator experience — 15%

| Item | ☐ |
|------|---|
| Non-engineer can see what/where/how bad in seconds | ☐ |
| Most important info dominates screen | ☐ |
| Map + list work together | ☐ |
| Ambiguity / low confidence visible | ☐ |
| Ticket workflow matches real work; verify not fake | ☐ |

### B5. Docs & reproducibility — 15%

| Item | ☐ |
|------|---|
| README alone enough to run | ☐ |
| ARCHITECTURE diagram matches shipped system | ☐ |
| DEPLOYMENT troubleshooting = failures you hit | ☐ |
| DECISIONS: choices, rejects, assumptions, known broken | ☐ |
| AI-WORKFLOW: tools, throws-away, understanding bar | ☐ |

### B6. Craft & AI leverage — 5%

| Item | ☐ |
|------|---|
| Tests on localization logic | ☐ |
| Incremental meaningful commits (not one dump) | ☐ |
| No secrets in git | ☐ |
| Linter/format actually run | ☐ |
| You can explain AI-touched files line-by-line | ☐ |

---

## C. Official self-check (from deliverables — run before email)

| # | Check | ☐ |
|---|-------|---|
| 1 | Cloned own repo fresh; `docker compose up` worked | ☐ |
| 2 | Public URL in private window; no login | ☐ |
| 3 | Span fault → exactly one ticket, located, with PIN | ☐ |
| 4 | Three simultaneous faults → three tickets | ☐ |
| 5 | Kill device telemetry, power still on → **no** fault ticket | ☐ |
| 6 | Scheduled outage → **no** fault ticket | ☐ |
| 7 | Repair fault → ticket auto-verified (no click) | ☐ |
| 8 | Mark resolved while dark → system pushes back | ☐ |
| 9 | Five docs present; architecture matches code | ☐ |
| 10 | Stranger could follow DEPLOYMENT without messaging you | ☐ |
| 11 | No secrets in git history | ☐ |
| 12 | You can explain every file | ☐ |

---

## D. Component readiness (map to ARCHITECTURE)

| Component | Min bar | ☐ |
|-----------|---------|---|
| Telemetry ingest | 202 + Redis; duplicates safe | ☐ |
| Device state | seq dedup; fw-aware silence | ☐ |
| Topology | recorded + inferred + source flag | ☐ |
| Filters | sensor impossible; schedule soft | ☐ |
| Localizer | 4 classes; grouping; confidence | ☐ |
| Tickets | full FSM; telemetry verify | ☐ |
| Simulator | span/DT/feeder/noise/repair | ☐ |
| Console | list+map+actions+sim | ☐ |
| PIN helper | works without reviewer key | ☐ |
| LLM summary | optional; grounded; degrades | ☐ |
| Compose | one command, seeded | ☐ |
| Deploy | public URL + video | ☐ |

---

## E. Cut list (if time blows up)

**Cut first (score impact low if core solid)**
- [ ] LLM summary (replace with short “why no LLM” paragraph only if cut)
- [ ] Households-based severity niceties
- [ ] SSE / live animations
- [ ] Extra map styling / motion
- [ ] Repeat-fault badges

**Never cut**
- [ ] Localization correctness + tests
- [ ] Grouping (one ticket per fault)
- [ ] Missing-topology honesty
- [ ] Sensor vs outage
- [ ] Schedule non-ticket
- [ ] Telemetry verification
- [ ] Simulator driveability
- [ ] docker compose + public URL + video
- [ ] Honest docs

---

## F. Submit email body (<300 words) — draft skeleton

```
Repo: ...
Live: ...
Video: ...

Works:
- ...
- ...

Doesn't / cut:
- ...
- ...

First fix with more time:
- ...
```

Tone: straight. Known gaps = positive signal.

---

## G. Session tracker

| Doc | Status |
|-----|--------|
| ARCHITECTURE.md | Drafted — update when code diverges |
| PLAN.md | Ready to execute |
| CHECKLIST.md | This file — tick during build |
| DECISIONS.md | Create at first real choice; append-only |
| README / DEPLOYMENT / AI-WORKFLOW | Write in P10 (stubs earlier OK) |

**Next action:** start **P0 scaffold** when you say go — compose + FastAPI health + empty web.
