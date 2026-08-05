# AI workflow

I used AI while building GridLocalizer, but I tried to keep trust-critical paths under my own eyes.

---

## Tools

- **Cursor** for most implementation — API, worker, localizer, simulator, and console.
- Occasional chat for architecture trade-offs and first drafts of documentation.

---

## What I delegated vs what I owned

| Area | How I worked |
|------|----------------|
| Localization, confidence, grouping | Spec’d first, implemented with tests; re-read line by line before shipping |
| Ingest dedup and sequence handling | Written against the brief’s delivery rules |
| Simulator behaviour (missing dying messages, fw 1.2 silence) | Checked against the data/systems brief |
| Operator UI layout | I directed structure; AI helped with JSX and CSS |
| Boilerplate (compose, settings, CRUD shapes) | Mostly AI, then trimmed |

Rule of thumb: anything that affects **trust or localization** got a human pass and a pytest. Chrome and docs could move faster.

---

## Where AI was wrong (and how I caught it)

1. **Per-pole alerting** — early suggestions treated every dark pole as its own incident. The brief’s “forty alerts for one wire” line pushed me toward grouping tests.
2. **LLM for localization** — rejected. The frontier on a tree is deterministic, cheap, and explainable. The only AI feature is grounded explain text.
3. **Missing topology hand-waving** — models often assumed parents always exist. Fixed with seed gaps, geo-infer, confidence penalties, and `true_parent_id` for the simulator.

---

## How much code is AI-assisted

Roughly **60–75%** of lines had AI help at some stage. Localization behaviour, ticket verification rules, and simulator realism were directed and tested by me. I am comfortable walking through `localization.py`, the worker consumer, and `sim.py` without notes.

---

## Prompts that worked well

- “Implement frontier localization on a radial tree; one incident per shared live→dark edge; pytest fixtures for span, DT, feeder, and sensor lie.”
- “Simulator must share `POST /telemetry` and model missing dying messages and fw 1.2 silence.”
- “Explain endpoint: grounded on JSON only; Groq optional; deterministic fallback; never localize with the LLM.”

---

## What to expect in a call

Questions will likely focus on localization, missing topology, and any file that looks AI-generated. That is intentional — a smaller surface I understand beats a larger one I cannot defend.
