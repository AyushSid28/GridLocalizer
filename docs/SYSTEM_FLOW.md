# GridLocalizer — main system flow (Mermaid source)

Editable source for the diagram in the [README](../README.md) and [ARCHITECTURE.md](ARCHITECTURE.md).

**Mermaid Chart (edit online):** https://mermaid.ai/app/projects/c8a88bf0-6185-46de-8264-3d9d3631bdc5/diagrams/24a90605-4b73-4d7b-b8c4-d24d10c8e364/version/v0.1/edit

Committed diagram: `images/system-flow.svg` (export from Mermaid Chart).

---

## Main flow — fault to closed ticket

```mermaid
flowchart TB
  subgraph GRID["Electrical grid"]
    FAULT["Fault: span, DT, or feeder"]
    FAULT --> DARK["Downstream poles lose power"]
    DARK --> IOT["Pole devices: heartbeat / power_lost / silence"]
  end

  subgraph INGEST["Ingest & state"]
    IOT --> API["POST /telemetry"]
    SIM["Simulator: inject · repair · noise · scenario"] --> API
    SIM --> SYNC["Sim: update pole_states in Postgres"]
    API --> REDIS[(Redis Stream)]
    REDIS --> WORKER["Worker: dedup by device_id + seq"]
    WORKER --> STATE[(pole_states)]
    WORKER --> DEBOUNCE["dt_dirty debounce DETECT_WAIT_SEC"]
    SYNC --> LOC["run_global_localization"]
    DEBOUNCE --> LOC
  end

  subgraph LOCALIZE["Localize & trust"]
    LOC --> FILTER{"Trust filters"}
    FILTER -->|Dark pole, live children| NOISE["Sensor issue — no outage ticket"]
    FILTER -->|Scheduled outage soft-match| SUPPRESS["Suppress or note"]
    FILTER -->|Real outage| CLASSIFY{"Pattern?"}
    CLASSIFY -->|All feeder dark| KIND_F["feeder ticket"]
    CLASSIFY -->|Whole DT dark| KIND_D["DT ticket"]
    CLASSIFY -->|Live to dark on tree| KIND_S["span ticket at frontier edge"]
    KIND_F --> ONE["One incident per fault"]
    KIND_D --> ONE
    KIND_S --> ONE
    ONE --> DETECTED["status: detected"]
  end

  subgraph CONSOLE["Operator console"]
    DETECTED --> UI["Incident Center + map + PIN + confidence"]
    UI --> ACK["acknowledge"]
    ACK --> CREW["assign crew"]
    CREW --> ASSIGNED["status: crew_assigned"]
    ASSIGNED --> REPAIR["Simulation repair — same scope as fault"]
    REPAIR --> REST["boot + power_restored telemetry"]
    REST --> READY{"Restoration telemetry ready?"}
    READY -->|No| BLOCK["Confirm repair disabled / HTTP 409"]
    READY -->|Yes| RESOLVE["confirm repair — POST resolve"]
    RESOLVE --> VERIFY["Verifier: boot + power_restored after outage"]
    VERIFY --> CLOSED["status: closed"]
  end

  GRID --> INGEST
  INGEST --> LOCALIZE
  LOCALIZE --> CONSOLE
```

---

**Live demo:** https://gridlocalizer.vercel.app  
**Video:** https://www.loom.com/share/2e9c151eef86404ebd19678d7fe4e5dc
