# SYSTEM FLOW — Detailed Flowcharts

Visual-only. No tech thesis. Follow arrows top → bottom / left → right.

---

## 1. Big picture (fault → closed ticket)

```mermaid
flowchart TD
  A[⚡ FAULT OCCURS on the network] --> B{What broke?}
  B -->|Wire between two poles| C[SPAN FAULT]
  B -->|Transformer / fuse| D[DT FAULT]
  B -->|11kV feeder| E[FEEDER FAULT]

  C --> F[All poles DOWNSTREAM of break go DARK]
  D --> G[ALL poles under that DT go DARK]
  E --> H[ALL poles under ALL DTs on feeder go DARK]

  F --> I[Upstream poles stay LIVE]
  G --> I
  H --> I

  I --> J[IoT devices on poles try to report]
  J --> K[TELEMETRY STREAM enters system]
  K --> L[System updates LIVE / DARK belief per pole]
  L --> M[Wait briefly — collect sibling reports]
  M --> N{Is this a real outage?}
  N -->|No — sensor lie / schedule / noise| O[No ticket — log only]
  N -->|Yes| P[Find LIVE → DARK boundary]
  P --> Q[ONE incident = ONE fault location]
  Q --> R[Create TICKET: detected]
  R --> S[Operator sees map + PIN + confidence]
  S --> T[Ack → Assign crew → Crew repairs]
  T --> U[Poles become LIVE again]
  U --> V[Devices send restore / heartbeat LIVE]
  V --> W{Telemetry confirms LIVE?}
  W -->|No| X[Do NOT close — push back]
  W -->|Yes| Y[Ticket VERIFIED → CLOSED]
```

---

## 2. Physical world: what a span fault looks like

```mermaid
flowchart TD
  subgraph BEFORE["BEFORE FAULT — all LIVE"]
    DT1[DT] --> P1[P1 🟢 LIVE]
    P1 --> P2[P2 🟢 LIVE]
    P2 --> P3[P3 🟢 LIVE]
    P3 --> P4[P4 🟢 LIVE]
  end

  subgraph BREAK["FAULT MOMENT"]
    W[Wire snaps between P2 and P3]
  end

  subgraph AFTER["AFTER FAULT — boundary appears"]
    DT2[DT] --> A1[P1 🟢 LIVE]
    A1 --> A2[P2 🟢 LIVE]
    A2 -.->|BROKEN SPAN| A3[P3 🔴 DARK]
    A3 --> A4[P4 🔴 DARK]
  end

  BEFORE --> BREAK --> AFTER
  AFTER --> R[System must report: fault on span P2↔P3<br/>NOT four separate alerts]
```

---

## 3. How LIVE / DARK gets into software (telemetry path)

```mermaid
flowchart TD
  P[Pole lamp / supply] --> D{Device still has power?}

  D -->|Yes — normal| H[Send HEARTBEAT every ~15 min<br/>energized = true → LIVE]
  D -->|Power just lost| L{Firmware + capacitor OK?}

  L -->|fw ≥ 1.3 and lucky ~70%| PL[Send power_lost once<br/>energized = false → DARK]
  L -->|fw ≥ 1.3 but fail ~30%| S1[Go SILENT — no dying message]
  L -->|fw 1.2.x| S2[Never sends power_lost<br/>just STOPS heartbeating]

  PL --> IN[HTTPS POST /telemetry]
  H --> IN
  S1 --> AMB[Silence is AMBIGUOUS]
  S2 --> AMB
  AMB --> T{Missed heartbeats + context?}
  T -->|Children still LIVE| SF[Treat as SENSOR FAILURE<br/>not outage]
  T -->|Downstream also dark / pattern matches| IN2[Infer DARK from silence]
  IN2 --> IN

  IN --> Q[Message queue]
  Q --> U[Update pole state: LIVE or DARK]
```

---

## 4. Messy telemetry reality (same fault, ugly arrival)

```mermaid
flowchart LR
  F[Span breaks at T=0] --> M1[P3 power_lost arrives]
  F --> M2[P4 power_lost arrives FIRST<br/>out of order]
  F --> M3[P5 dying message NEVER arrives]
  F --> M4[Duplicate power_lost retry<br/>hours later]
  F --> M5[P3 heartbeat was fw1.2<br/>only silence]

  M1 --> S[State store]
  M2 --> S
  M3 --> S
  M4 --> S
  M5 --> S

  S --> DEDUP[Drop duplicates via device seq]
  DEDUP --> ORDER[Order by receive time<br/>not device clock]
  ORDER --> WAIT[Debounce window<br/>wait for cluster to form]
  WAIT --> READY[Snapshot of LIVE/DARK map<br/>ready for localization]
```

---

## 5. From dark poles → one fault location

```mermaid
flowchart TD
  SNAP[Pole LIVE/DARK snapshot] --> GROUP[Group dark poles by DT / feeder]

  GROUP --> CHK1{Scheduled outage<br/>matches this pattern?}
  CHK1 -->|Yes + pattern expected| SUP[Suppress — not a fault ticket]
  CHK1 -->|No or weird shape| CHK2

  CHK2{Any dark pole with<br/>LIVE children downstream?}
  CHK2 -->|Yes| SENSOR[SENSOR FAILURE<br/>device lying — no outage ticket]
  CHK2 -->|No| CLS{Darkness pattern?}

  CLS -->|Whole feeder dark| FEED[FEEDER FAULT<br/>asset = feeder_id]
  CLS -->|Whole DT dark, no live under DT| DT[DT FAULT<br/>asset = dt_id]
  CLS -->|Mix of LIVE and DARK on line| SPAN

  SPAN[Walk tree: find last LIVE → first DARK]
  SPAN --> EDGE[Fault = EDGE between those poles]
  EDGE --> COUNT[Count downstream dark poles]
  COUNT --> PIN[Coords = midpoint of span<br/>+ PIN code]
  PIN --> CONF[Confidence + reasons<br/>topology known? sensors missing?]
  CONF --> ONE[Open / update ONE incident<br/>for this frontier]

  FEED --> ONE2[One feeder incident]
  DT --> ONE3[One DT incident]
  ONE --> TKT[Ticket status = detected]
  ONE2 --> TKT
  ONE3 --> TKT
```

---

## 6. Multiple faults at once (storm day)

```mermaid
flowchart TD
  STORM[Three spans fail in minutes] --> D1[DT-A: dark cluster #1]
  STORM --> D2[DT-A: dark cluster #2<br/>different frontier]
  STORM --> D3[DT-B: dark cluster #3]

  D1 --> L1[Localize frontier A1]
  D2 --> L2[Localize frontier A2]
  D3 --> L3[Localize frontier B1]

  L1 --> T1[Ticket 1]
  L2 --> T2[Ticket 2]
  L3 --> T3[Ticket 3]

  NOTE[Wrong: merge all into one ticket<br/>Wrong: one ticket per dark pole<br/>Right: one ticket per frontier]
```

---

## 7. Missing topology branch (60% of DTs)

```mermaid
flowchart TD
  NEED[Need parent→child tree to find span] --> HAS{parent_pole_id<br/>recorded?}

  HAS -->|Yes ~40%| USE[Use surveyed tree<br/>high confidence path]
  HAS -->|No ~60%| INF[Infer tree from GPS + DT location]

  INF --> OK{Inference stable?}
  OK -->|Yes| USE2[Use inferred tree<br/>lower confidence + UI badge]
  OK -->|No| DEGRADE[Do NOT invent exact span<br/>Report DT-level location<br/>honest low confidence]

  USE --> LOC[Span-level localization]
  USE2 --> LOC
  DEGRADE --> DTLOC[DT-level incident]
  LOC --> UI[Operator sees mode:<br/>surveyed / inferred / DT-only]
  DTLOC --> UI
```

---

## 8. Ticket lifecycle + restoration verify

```mermaid
flowchart TD
  D[detected] --> A[acknowledged<br/>operator saw it]
  A --> C[crew_assigned]
  C --> R[resolved<br/>crew claims fixed]

  R --> V{Affected poles LIVE<br/>in telemetry?}
  V -->|Still DARK| BACK[Reject close / flag failed verify<br/>do not trust the click]
  V -->|LIVE and stable| VER[verified]
  VER --> CL[closed]

  subgraph AUTO["Auto path — no click needed for truth"]
    REP[Crew repairs wire] --> DEV[Devices: boot + power_restored<br/>or heartbeat energized=true]
    DEV --> V
  end
```

---

## 9. Operator console flow (what human does)

```mermaid
flowchart TD
  OP[Operator at console] --> SEE[Sees new incident dominate screen]
  SEE --> READ[Reads: what broke · where · PIN · how many poles · confidence]
  READ --> MAP[Map highlights span / DT]
  MAP --> ACK[Acknowledge]
  ACK --> ASG[Assign crew stub]
  ASG --> WAIT[Wait for field work]
  WAIT --> FIX[Crew fixes OR sim repair]
  FIX --> AUTO[System auto-verifies from LIVE telemetry]
  AUTO --> DONE[Ticket closed — operator confirms visually]
```

---

## 10. Simulator = same path as real world

```mermaid
flowchart TD
  REV[Reviewer / you] --> SIM[Simulator UI / command]
  SIM --> INJ{Inject what?}
  INJ -->|Span / DT / Feeder fault| GEN[Generate realistic telemetry<br/>missing msgs, fw silence, dups, reorder]
  INJ -->|Dead sensor noise| NOISE[One pole dark, children LIVE]
  INJ -->|Scheduled outage| SCH[Dark pattern under schedule window]
  INJ -->|Repair| REST[Generate restore telemetry]

  GEN --> PIPE[Same POST /telemetry as real devices]
  NOISE --> PIPE
  SCH --> PIPE
  REST --> PIPE

  PIPE --> BACKEND[Normal detect → localize → ticket path]
  BACKEND --> UI[Dashboard updates]
```

---

## 11. End-to-end swimlane (who does what)

```mermaid
sequenceDiagram
  participant Grid as Electrical grid
  participant Dev as Pole IoT device
  participant Sys as Backend
  participant Op as Operator
  participant Crew as Crew (out of scope ops)

  Grid->>Grid: Span breaks
  Grid->>Dev: Downstream poles lose power
  Dev->>Sys: power_lost / silence / heartbeats stop
  Note over Sys: Dedup, wait, filter noise
  Sys->>Sys: Find LIVE→DARK edge
  Sys->>Op: One ticket + map + PIN
  Op->>Op: Ack + assign
  Op->>Crew: Dispatch (human process)
  Crew->>Grid: Repair span
  Grid->>Dev: Power returns
  Dev->>Sys: boot + power_restored / LIVE heartbeat
  Sys->>Sys: Verify affected poles LIVE
  Sys->>Op: Ticket verified → closed
```

---

## 12. Decision cheat-sheet (quick)

```mermaid
flowchart TD
  Q1{Poles dark?} -->|No| IDLE[Idle]
  Q1 -->|Yes| Q2{Impossible pattern?<br/>dark but child LIVE}
  Q2 -->|Yes| SENS[Sensor failure]
  Q2 -->|No| Q3{Matches active schedule<br/>AND expected scope?}
  Q3 -->|Yes| SCH[Scheduled — no fault ticket]
  Q3 -->|No| Q4{Whole feeder?}
  Q4 -->|Yes| FF[Feeder fault ticket]
  Q4 -->|No| Q5{Whole DT?}
  Q5 -->|Yes| DF[DT fault ticket]
  Q5 -->|No| SF[Span fault at LIVE→DARK edge]
```

---

*When implementing, this file is the story; `ARCHITECTURE.md` is the machinery.*
