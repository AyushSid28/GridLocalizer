# AI-WORKFLOW

## Tools

- **Cursor** for most implementation (API, worker, localizer, sim, console).
- Occasional chat for architecture trade-offs and doc drafts.

## What I delegated vs wrote carefully

| Area | Approach |
|------|----------|
| Localization, confidence, grouping | Spec’d first, implemented with tests; re-read line by line |
| Ingest dedup / seq handling | Written against the brief’s delivery rules |
| Simulator physics (70% dying msg, fw 1.2 silence) | Hand-checked against `02-data-and-systems` |
| Operator UI layout | Directed; AI filled JSX/CSS |
| Boilerplate (compose, settings, CRUD shapes) | Mostly AI, then trimmed |

Rule of thumb: anything that affects **trust or localization** gets a human pass and a pytest. Chrome can be faster AI.

## Where AI was wrong (and how I caught it)

1. **Per-pole alerting instincts** — early drafts treated every dark pole as an incident. Caught by re-reading the brief (“40 alerts for one wire is worse than nothing”) and adding grouping tests.
2. **LLM-for-localization suggestions** — rejected; graph frontier is deterministic, free, and explainable. AI feature is explain-only.
3. **`git add -A` staged-commit scripts** — would dump all remaining work into one commit. Replaced with path-grouped commits so history matches real chunks.
4. **Missing-topology hand-waving** — AI sometimes assumed parents always exist. Fixed with seed gaps + infer + confidence penalties + `true_parent_id` for sim.

## How much code is AI-generated

Roughly **60–75%** of lines had AI assistance. The localization behaviour, ticket verify rules, and sim realism were directed and tested by me. I can walk `localization.py`, the worker consumer, and `sim.py` without notes.

## Prompts / sessions that worked best

- “Implement frontier localization on a radial tree; one incident per shared live→dark edge; pytest fixtures for span/DT/feeder/sensor.”
- “Simulator must share `POST /telemetry` and model 30% missing dying messages and fw 1.2 silence.”
- “Explain endpoint: grounded on JSON only; Groq optional; deterministic fallback; never localize with the LLM.”

## Call expectation

Expect questions on localization, missing topology, and any AI-touched file. That is intentional — smaller surface I understand beats a larger one I cannot defend.
