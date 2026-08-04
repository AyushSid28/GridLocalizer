import { useEffect, useState } from 'react';
import './styles.css';
import { Breadcrumb } from './components/Breadcrumb';
import MultifaultSelector from './components/MultifaultSelector';
import * as api from './api';

// API URL settings
const apiBase = import.meta.env.VITE_API_URL ?? "";

type Health = {
  status: string;
  service: string;
};

type Summary = {
  poles: number;
  dts: number;
  devices: number;
  active_devices: number;
  heartbeat_freshness_sec: number | null;
  ingestion_rate_per_min: number;
  processed_events: number;
  processing_latency_ms: number | null;
  wiring_known_dts: number;
  wiring_unknown_dts: number;
  inferred_poles: number;
};

type DT = {
  dt_id: string;
  feeder_id: string;
  lat: number;
  lon: number;
  households: number;
  wiring_known: boolean;
  pole_count: number;
  dark_poles?: number;
};

type PoleDetail = {
  pole_id: string;
  lat: number;
  lon: number;
  parent_id: string | null;
  true_parent_id: string | null;
  seq_on_line: number | null;
  pincode: string | null;
  device_id: string | null;
  topology_source: string;
  energized: boolean | null;
  status?: "healthy" | "offline" | "suspect_sensor";
  suspect_sensor?: boolean;
  battery_mv?: number | null;
  firmware: string | null;
  last_event?: string | null;
  last_seen_at?: string | null;
};

type DTDetail = {
  dt_id: string;
  feeder_id: string;
  lat: number;
  lon: number;
  wiring_known: boolean;
  poles: PoleDetail[];
};

type Incident = {
  id: string;
  kind: "span" | "dt" | "feeder" | "sensor";
  status: "detected" | "acknowledged" | "crew_assigned" | "resolved" | "verified" | "closed";
  feeder_id: string | null;
  dt_id: string | null;
  span_from: string | null;
  span_to: string | null;
  lat: number | null;
  lon: number | null;
  pincode: string | null;
  affected_poles: number;
  confidence: number;
  reasons: string[];
  topology_mode: string;
  summary: string | null;
  crew_label: string | null;
  verify_note: string | null;
  scheduled_outage?: {
    id: string;
    scope: string;
    target_id: string;
    starts_at: string;
    ends_at: string;
    reason: string;
  } | null;
  created_at: string | null;
  closed_at: string | null;
  evidence?: {
    positive: string[];
    negative: string[];
  };
};

const activeStatuses: Incident["status"][] = ["detected", "acknowledged", "crew_assigned", "resolved"];

function isActiveIncident(incident: Incident) {
  return activeStatuses.includes(incident.status);
}

function isDtSourceOutage(dtId: string, feederId: string | null, allIncidents: Incident[]): boolean {
  return allIncidents.some(
    (incident) =>
      isActiveIncident(incident) &&
      (
        (incident.kind === "dt" && incident.dt_id === dtId) ||
        (incident.kind === "feeder" && feederId !== null && incident.feeder_id === feederId)
      )
  );
}

function hasChildFaultTicket(dtId: string, allIncidents: Incident[]): boolean {
  return allIncidents.some(
    (incident) =>
      isActiveIncident(incident) &&
      incident.dt_id === dtId &&
      incident.kind !== "dt" &&
      incident.kind !== "feeder"
  );
}

function getStatusLabel(status: Incident["status"]) {
  const labels: Record<Incident["status"], string> = {
    detected: "Active",
    acknowledged: "Acknowledged",
    crew_assigned: "Crew Assigned",
    resolved: "Awaiting Verification",
    verified: "Verified Restored",
    closed: "Resolved",
  };
  return labels[status];
}

function getFaultType(incident: Incident) {
  const labels: Record<Incident["kind"], string> = {
    feeder: "Feeder outage",
    dt: "Transformer outage",
    span: "Span fault",
    sensor: "Sensor anomaly",
  };
  return labels[incident.kind];
}

function getFaultLocation(incident: Incident) {
  if (incident.kind === "span") return `${incident.span_from || "DT"} -> ${incident.span_to || "Unknown pole"}`;
  if (incident.kind === "dt") return `Transformer ${incident.dt_id || "Unknown"}`;
  if (incident.kind === "feeder") return `Feeder ${incident.feeder_id || "Unknown"}`;
  return incident.dt_id ? `Near ${incident.dt_id}` : "Unknown location";
}

function formatDetectedTime(value: string | null) {
  if (!value) return "Unknown";
  return new Date(value).toLocaleString([], {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(seconds: number | null | undefined) {
  if (seconds == null) return "No telemetry";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function getApiErrorMessage(errData: any, fallback: string) {
  if (!errData) return fallback;
  if (typeof errData.detail === "string") return errData.detail;
  if (Array.isArray(errData.detail)) {
    return errData.detail.map((item: any) => item.msg || JSON.stringify(item)).join("; ");
  }
  if (errData.detail) return JSON.stringify(errData.detail);
  return fallback;
}

function getLifecycleStage(status: Incident["status"]) {
  const stages = ["Fault detected", "Incident created", "Acknowledged", "Crew assigned", "Repair started", "Waiting for restoration telemetry", "Verified restored", "Closed"];
  const activeIndex: Record<Incident["status"], number> = {
    detected: 1,
    acknowledged: 2,
    crew_assigned: 4,
    resolved: 5,
    verified: 6,
    closed: 7,
  };
  return { stages, activeIndex: activeIndex[status] };
}


export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [dts, setDts] = useState<DT[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);
  const [selectedDT, setSelectedDT] = useState<DTDetail | null>(null);
  const [selectedDTId, setSelectedDTId] = useState<string | null>(null);
  const [focusedPole, setFocusedPole] = useState<PoleDetail | null>(null);
  const [incidentSummary, setIncidentSummary] = useState<{ text: string; source: string } | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  // Filter/Sort states
  const [incidentFilter, setIncidentFilter] = useState<"all" | "active" | "closed">("active");
  const [incidentSort, setIncidentSort] = useState<"newest" | "severity">("newest");

  // Simulation settings
  const [simKind, setSimKind] = useState<"feeder" | "dt" | "span" | "pole">("dt");
  const [simTargetId, setSimTargetId] = useState("");
  const [simSpanFrom, setSimSpanFrom] = useState("");
  const [simSpanTo, setSimSpanTo] = useState("");
  const [simNoiseKind, setSimNoiseKind] = useState("dead_sensor");
  const [simNoiseTarget, setSimNoiseTarget] = useState("");
  const [simResponse, setSimResponse] = useState<string | null>(null);
  const [showSimulation, setShowSimulation] = useState(false);

  // FSM Action inputs
  const [crewLabelInput, setCrewLabelInput] = useState("");
  const [showCrewInput, setShowCrewInput] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // SVG Map Display Layers
  const [showPolesLayer, setShowPolesLayer] = useState(true);
  const [showTransformersLayer, setShowTransformersLayer] = useState(true);
  const [showFaultBoundaries, setShowFaultBoundaries] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);

  // Poll DB state
  useEffect(() => {
    async function fetchData() {
      try {
        const [healthData, summaryData, dtData, incData] = await Promise.all([
          api.fetchHealth(),
          api.fetchSummary(),
          api.fetchDTs(),
          api.fetchIncidents(),
        ]);
        setHealth(healthData);
        setSummary(summaryData);
        setDts(dtData);
        setIncidents(incData);
        
        // Keep selection updated
        if (selectedIncident) {
          const updated: Incident | undefined = incData.find((i: Incident) => i.id === selectedIncident.id);
          if (updated) setSelectedIncident(updated);
        }
      } catch (err) {
        console.error("Error polling data", err);
      }
    }

    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, [selectedIncident, refreshTick]);

  // Load detailed DT data when selected
  useEffect(() => {
    if (!selectedDTId) {
      setSelectedDT(null);
      return;
    }
    async function fetchDTDetail() {
      try {
      const dtDetail = await api.fetchDTDetail(selectedDTId as string);
      setSelectedDT(dtDetail);
      } catch (err) {
        console.error("Error fetching DT details", err);
      }
    }
    fetchDTDetail();
  }, [selectedDTId, incidents, refreshTick]);

  // Auto focus map to DT when selecting an incident
  useEffect(() => {
    if (selectedIncident && selectedIncident.dt_id) {
      setSelectedDTId(selectedIncident.dt_id);
    }
  }, [selectedIncident]);

  // FSM Event Handlers
  async function handleAcknowledge(id: string) {
    setActionError(null);
    try {
      await api.acknowledgeIncident(id);
    } catch (err: any) {
      setActionError(err.message);
    }
  }

  async function handleAssignCrew(id: string) {
    setActionError(null);
    if (!crewLabelInput.trim()) return;
    try {
      await api.assignCrew(id, crewLabelInput);
      setShowCrewInput(false);
      setCrewLabelInput("");
    } catch (err: any) {
      setActionError(err.message);
    }
  }

  async function handleResolve(id: string) {
    setActionError(null);
    try {
      await api.resolveIncident(id);
    } catch (err: any) {
      setActionError(err.message);
    }
  }

  async function summarizeIncident(id: string) {
    setSummaryLoading(true);
    setIncidentSummary(null);
    setActionError(null);
    try {
      const res = await fetch(`${apiBase}/incidents/${id}/explain`, { method: "POST" });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(getApiErrorMessage(errData, `HTTP error ${res.status}`));
      }
      const data = await res.json();
      setIncidentSummary({ text: data.explanation, source: data.source });
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setSummaryLoading(false);
    }
  }

  // Simulation Controls
  async function triggerSimulation(action: "inject" | "repair") {
    setSimResponse(null);
    
    // Client-side validation
    if (simKind === "feeder" && !simTargetId) {
      setSimResponse("Error: Please select a Feeder ID");
      return;
    }
    if (simKind === "dt" && !simTargetId) {
      setSimResponse("Error: Please select a Distribution Transformer (DT) ID");
      return;
    }
    if (simKind === "pole" && !simTargetId.trim()) {
      setSimResponse("Error: Please enter a Pole ID");
      return;
    }
    if (simKind === "span" && (!simSpanFrom.trim() || !simSpanTo.trim())) {
      setSimResponse("Error: Please enter both 'From' and 'To' Pole IDs for the span");
      return;
    }

    try {
      let data;
      if (action === "inject") {
        data = await api.injectOutage({
          kind: simKind,
          target_id: simTargetId || undefined,
          span_from: simSpanFrom || undefined,
          span_to: simSpanTo || undefined,
        });
      } else {
        data = await api.repairSimulation({
          kind: simKind,
          target_id: simTargetId || undefined,
          span_from: simSpanFrom || undefined,
          span_to: simSpanTo || undefined,
        });
      }
      setSimResponse(`Success: ${action === "inject" ? "Outage injected" : "Outage repaired"} (${data.affected_devices} telemetry devices signaled)`);
      // Nudge pollers so map colors catch up after worker processes telemetry
      window.setTimeout(() => setRefreshTick((n) => n + 1), 800);
      window.setTimeout(() => setRefreshTick((n) => n + 1), 2500);
    } catch (err: any) {
      setSimResponse(`Error: ${err.message}`);
    }
  }

  async function triggerNoise() {
    setSimResponse(null);
    if (!simNoiseTarget.trim()) {
      setSimResponse("Error: Please enter a Target Pole ID");
      return;
    }
    try {
      const data = await api.injectNoise({
        kind: simNoiseKind,
        target_id: simNoiseTarget,
      });
      setSimResponse(`Success: Noise injected (${data.kind} on ${data.pole_id})`);
    } catch (err: any) {
      setSimResponse(`Error: ${err.message}`);
    }
  }

  async function triggerClearNoise() {
    setSimResponse(null);
    if (!simNoiseTarget.trim()) {
      setSimResponse("Error: Please enter a Target Pole ID");
      return;
    }
    try {
      const res = await fetch(`${apiBase}/sim/clear_noise`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_id: simNoiseTarget }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(getApiErrorMessage(errData, `HTTP error ${res.status}`));
      }
      const data = await res.json();
      setSimResponse(`Success: Telemetry restored on pole ${data.target_id}`);
    } catch (err: any) {
      setSimResponse(`Error: ${err.message}`);
    }
  }

  // Scaling logic to position DTs / Poles inside a 600x450 coordinate box
  const getCoordinates = (lat: number, lon: number) => {
    if (dts.length === 0) return { x: 300, y: 225 };
    const lats = dts.map(d => d.lat);
    const lons = dts.map(d => d.lon);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);

    const x = maxLon === minLon ? 300 : 40 + ((lon - minLon) / (maxLon - minLon)) * 520;
    const y = maxLat === minLat ? 225 : 410 - ((lat - minLat) / (maxLat - minLat)) * 370;
    return { x, y };
  };

  // Filter and Sort Incidents
  const sortedIncidents = incidents
    .filter(inc => {
      if (incidentFilter === "active") return isActiveIncident(inc);
      if (incidentFilter === "closed") return inc.status === "closed" || inc.status === "verified";
      return true;
    })
    .sort((a, b) => {
      if (incidentSort === "severity") {
        const severityMap = { feeder: 3, dt: 2, span: 1, sensor: 0 };
        return severityMap[b.kind] - severityMap[a.kind];
      }
      return 1; // Default order from API (newest)
    });

  // Unique Feeders list for Simulation selection
  const uniqueFeeders = Array.from(new Set(dts.map(d => d.feeder_id)));
  const selectedLifecycle = selectedIncident ? getLifecycleStage(selectedIncident.status) : null;

  return (
    <div className="app-shell">
      {/* 1. Header */}
      <header className="app-header">
        <div className="header-brand">
          <span className="brand-logo">GC</span>
          <div>
            <h1>Grid Control Center</h1>
            <p className="subdivision">KSPDB Division SD-07</p>
          </div>
        </div>
        
        <div className="header-metrics">
          <div className="metric">
            <span className="metric-label">System State</span>
            <span className="metric-value status-indicator">
              <span className={`dot ${health ? "dot-green" : "dot-red"}`}></span> {health ? "Operational" : "Offline"}
            </span>
          </div>
          <div className="metric">
            <span className="metric-label">Active Outages</span>
            <span className={`metric-value ${incidents.filter(isActiveIncident).length > 0 ? "has-outage" : ""}`}>
              {incidents.filter(isActiveIncident).length}
            </span>
          </div>
          <div className="metric">
            <span className="metric-label">Heartbeat Freshness</span>
            <span className="metric-value">{formatDuration(summary?.heartbeat_freshness_sec)}</span>
          </div>
          <div className="metric">
            <span className="metric-label">Modem Telemetry</span>
            <span className="metric-value">{summary?.active_devices ?? 0}/{summary?.poles ?? 0} online</span>
          </div>
          <div className="metric">
            <span className="metric-label">Ingestion Rate</span>
            <span className="metric-value">{summary?.ingestion_rate_per_min ?? 0}/min</span>
          </div>
        </div>
      </header>

      {/* Main 3-Column Layout */}
      <div className="dashboard-grid">
        {/* 2. Incident Center (Left Column) */}
        <section className="panel column-left">
          <div className="panel-header">
            <h2>Incident Center</h2>
            <div className="filter-bar">
              <select value={incidentFilter} onChange={e => setIncidentFilter(e.target.value as any)}>
                <option value="active">Active Outages</option>
                <option value="closed">Resolved Log</option>
                <option value="all">All Tickets</option>
              </select>
              <select value={incidentSort} onChange={e => setIncidentSort(e.target.value as any)}>
                <option value="newest">Newest First</option>
                <option value="severity">Outage Severity</option>
              </select>
            </div>
          </div>

          <div className="incident-list">
            {sortedIncidents.length === 0 ? (
              <p className="empty-muted">{incidentFilter === "active" ? "No active incidents" : "No incidents matching filter"}</p>
            ) : (
              sortedIncidents.map(inc => {
                const isSelected = selectedIncident?.id === inc.id;
                return (
                  <div
                    key={inc.id}
                    className={`incident-card severity-${inc.kind} ${isSelected ? "selected" : ""}`}
                    onClick={() => {
                      setSelectedIncident(inc);
                      setFocusedPole(null);
                      setIncidentSummary(null);
                    }}
                  >
                    <div className="card-top">
                      <span className="severity-badge">{getFaultType(inc)}</span>
                      <span className={`status-badge ${inc.status}`}>{getStatusLabel(inc.status)}</span>
                    </div>
                    
                    <h3>{getFaultLocation(inc)}</h3>

                    <div className="card-details">
                      <div>
                        <span className="label">Confidence</span>
                        <span className="value">{(inc.confidence * 100).toFixed(0)}%</span>
                      </div>
                      <div>
                        <span className="label">Total Fault Scope</span>
                        <span className="value">{inc.affected_poles} poles</span>
                      </div>
                      <div>
                        <span className="label">Detected</span>
                        <span className="value">{formatDetectedTime(inc.created_at)}</span>
                      </div>
                    </div>

                    <div className="card-badges">
                      {inc.topology_mode === "recorded" ? (
                        <span className="badge badge-surveyed">Surveyed</span>
                      ) : (
                        <span className="badge badge-inferred">Inferred</span>
                      )}
                      <span className="time-badge">{inc.pincode || "Location pending"}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* 3. Center Panel - SVG Topology Map */}
        <section className="panel column-center">
          <div className="panel-header map-header">
            <div className="map-header-top">
              <h2>Grid Topology Map</h2>
              <div className="layer-controls">
                <label>
                  <input type="checkbox" checked={showTransformersLayer} onChange={e => setShowTransformersLayer(e.target.checked)} />
                  Transformers
                </label>
                <label>
                  <input type="checkbox" checked={showPolesLayer} onChange={e => setShowPolesLayer(e.target.checked)} />
                  Poles
                </label>
                <label>
                  <input type="checkbox" checked={showFaultBoundaries} onChange={e => setShowFaultBoundaries(e.target.checked)} />
                  Outage Bounds
                </label>
                {selectedDTId && (
                  <button className="btn-back" onClick={() => { setSelectedDTId(null); setFocusedPole(null); }}>
                    Return to Grid View
                  </button>
                )}
              </div>
            </div>
            {selectedDTId && (
              <div className="map-breadcrumb-row">
                <Breadcrumb dtId={selectedDTId} apiBase={apiBase} />
              </div>
            )}
          </div>

          <div className="map-canvas-container">
            <svg viewBox="0 0 600 450" className="topology-svg">
              {/* Grid Background Lines */}
              <defs>
                <pattern id="gridPattern" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#222e3b" strokeWidth="0.5" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#gridPattern)" />

              {/* RENDER VIEW 1: Global Grid (All Transformers) */}
              {!selectedDTId && dts.map(dt => {
                const { x, y } = getCoordinates(dt.lat, dt.lon);
                const isSourceOutage = isDtSourceOutage(dt.dt_id, dt.feeder_id, incidents);
                const hasChildFault = hasChildFaultTicket(dt.dt_id, incidents);

                return (
                  <g
                    key={dt.dt_id}
                    className="map-node transformer-node"
                    transform={`translate(${x}, ${y})`}
                    onClick={() => {
                      setSelectedDTId(dt.dt_id);
                      setFocusedPole(null);
                    }}
                  >
                    <rect
                      x="-12"
                      y="-12"
                      width="24"
                      height="24"
                      rx="3"
                      className={`transformer-rect ${isSourceOutage ? "dark" : "live"}${hasChildFault && !isSourceOutage ? " ticket-open" : ""}`}
                    />
                    <text y="24" className="node-label" textAnchor="middle">
                      {dt.dt_id}
                    </text>
                  </g>
                );
              })}

              {/* RENDER VIEW 2: Detailed Tree for Selected DT */}
              {selectedDTId && selectedDT && (
                <>
                  {/* Spans (Edges) */}
                  {selectedDT.poles.map(pole => {
                    if (!pole.parent_id) return null;
                    const parent = selectedDT.poles.find(p => p.pole_id === pole.parent_id);
                    if (!parent) return null;

                    const coordFrom = getCoordinates(parent.lat, parent.lon);
                    const coordTo = getCoordinates(pole.lat, pole.lon);

                    // Check if this span is faulted (highlighted)
                    const isFaultedSpan = incidents.some(
                      i => i.dt_id === selectedDTId &&
                           isActiveIncident(i) &&
                           i.span_from === parent.pole_id &&
                           i.span_to === pole.pole_id
                    );

                    return (
                      <g key={`span-${parent.pole_id}-${pole.pole_id}`}>
                        <line
                          x1={coordFrom.x}
                          y1={coordFrom.y}
                          x2={coordTo.x}
                          y2={coordTo.y}
                          className={`grid-span-line ${isFaultedSpan ? "faulted" : ""}`}
                        />
                        {isFaultedSpan && showFaultBoundaries && (
                          <g transform={`translate(${(coordFrom.x + coordTo.x) / 2}, ${(coordFrom.y + coordTo.y) / 2})`}>
                            <circle r="12" fill="#d9534f" />
                            <text dy="4" fill="#fff" fontSize="10" textAnchor="middle" fontWeight="bold">X</text>
                          </g>
                        )}
                      </g>
                    );
                  })}

                    {/* Root Node (Transformer itself) */}
                    {showTransformersLayer && (() => {
                      const coord = getCoordinates(selectedDT.lat, selectedDT.lon);
                      const isSourceOutage = isDtSourceOutage(selectedDT.dt_id, selectedDT.feeder_id, incidents);
                      const hasChildFault = hasChildFaultTicket(selectedDT.dt_id, incidents);
                      return (
                        <g
                          key={`root-${selectedDT.dt_id}`}
                          className={`map-node transformer-node${isSourceOutage ? " faulted" : ""}`}
                          transform={`translate(${coord.x}, ${coord.y})`}
                        >
                          <rect
                            x="-14"
                            y="-14"
                            width="28"
                            height="28"
                            rx="4"
                            className={`transformer-rect ${isSourceOutage ? "dark" : "live"}${hasChildFault && !isSourceOutage ? " ticket-open" : ""}`}
                            stroke="#fff"
                            strokeWidth="1.5"
                          />
                          <text y="24" className="node-label" textAnchor="middle">{selectedDT.dt_id}</text>
                        </g>
                      );
                    })()}

                  {/* Pole Nodes */}
                  {showPolesLayer && selectedDT.poles.map(pole => {
                    const { x, y } = getCoordinates(pole.lat, pole.lon);
                    
                    // Node color status
                    let statusColorClass = "live";
                    if (pole.suspect_sensor || pole.status === "suspect_sensor") {
                      statusColorClass = "suspect";
                    } else if (pole.energized === false) {
                      statusColorClass = "dark";
                    }

                    return (
                      <g
                        key={pole.pole_id}
                        className={`map-node pole-node ${statusColorClass} ${focusedPole?.pole_id === pole.pole_id ? "selected" : ""}`}
                        transform={`translate(${x}, ${y})`}
                        onClick={() => setFocusedPole(pole)}
                      >
                        <circle r="7" className="pole-circle" />
                        <text y="16" className="node-label" textAnchor="middle">
                          {pole.pole_id}
                        </text>
                      </g>
                    );
                  })}
                </>
              )}
            </svg>
          </div>
        </section>

        {/* 4. Incident Inspector (Right Column) */}
        <section className="panel column-right">
          <div className="panel-header">
            <h2>{focusedPole ? "Pole Inspector" : "Incident Inspector"}</h2>
          </div>

          <div className="inspector-content">
            {focusedPole ? (
              <div className="pole-details">
                <div className="pole-quick-card">
                  <div className="info-row">
                    <span className="label">Pole ID</span>
                    <span className="value">{focusedPole.pole_id}</span>
                  </div>
                  <div className="info-row">
                    <span className="label">Attached DT</span>
                    <span className="value">{selectedDT?.dt_id || "Unknown"}</span>
                  </div>
                  <div className="info-row">
                    <span className="label">Pin</span>
                    <span className="value">{focusedPole.pincode || "Unknown"}</span>
                  </div>
                </div>
                <button className="btn-back" onClick={() => setFocusedPole(null)}>Close</button>
              </div>
            ) : selectedIncident ? (
              <div className="incident-details">
                <div className="inspector-top">
                  <h3>INCIDENT: #{selectedIncident.id.slice(0, 8).toUpperCase()}</h3>
                  <span className={`status-badge large ${selectedIncident.status}`}>{getStatusLabel(selectedIncident.status)}</span>
                </div>

                <div className="info-grid">
                  <div className="info-row">
                    <span className="label">Fault Type</span>
                    <span className="value">{getFaultType(selectedIncident)}</span>
                  </div>
                  <div className="info-row">
                    <span className="label">Fault Location</span>
                    <span className="value">{getFaultLocation(selectedIncident)}</span>
                  </div>
                  <div className="info-row">
                    <span className="label">Confidence</span>
                    <span className="value font-bold">{(selectedIncident.confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="info-row">
                    <span className="label">Total Fault Scope</span>
                    <span className="value">{selectedIncident.affected_poles}</span>
                  </div>
                  <div className="info-row">
                    <span className="label">Location</span>
                    <span className="value">{selectedIncident.pincode || "Unknown"}</span>
                  </div>
                  <div className="info-row">
                    <span className="label">Detected</span>
                    <span className="value">{formatDetectedTime(selectedIncident.created_at)}</span>
                  </div>
                  <div className="info-row">
                    <span className="label">Source</span>
                    <span className="value capitalize">{selectedIncident.topology_mode === "recorded" ? "Surveyed" : "Inferred"}</span>
                  </div>
                </div>

                {selectedLifecycle && (
                  <div className="lifecycle-strip" aria-label="Incident lifecycle">
                    {selectedLifecycle.stages.map((stage, index) => (
                      <div
                        key={stage}
                        className={`lifecycle-step ${index <= selectedLifecycle.activeIndex ? "complete" : ""} ${index === selectedLifecycle.activeIndex ? "current" : ""}`}
                      >
                        <span className="lifecycle-dot" />
                        <span>{stage}</span>
                      </div>
                    ))}
                  </div>
                )}

                <div className={`outage-context ${selectedIncident.scheduled_outage ? "expected" : "unexpected"}`}>
                  <strong>{selectedIncident.scheduled_outage ? "Expected Outage" : "Unexpected Fault"}</strong>
                  {selectedIncident.scheduled_outage ? (
                    <p>
                      Scheduled Maintenance: {selectedIncident.scheduled_outage.scope.toUpperCase()} {selectedIncident.scheduled_outage.target_id} · {formatDetectedTime(selectedIncident.scheduled_outage.starts_at)} - {formatDetectedTime(selectedIncident.scheduled_outage.ends_at)}
                    </p>
                  ) : (
                    <p>No active scheduled outage matches this incident scope.</p>
                  )}
                </div>

                {/* Evidence Breakdown */}
                <div className="evidence-section">
                  <h4>Evidence</h4>
                  {selectedIncident.reasons.length > 0 && (
                    <ul className="evidence-list reason-list">
                      {selectedIncident.reasons.map((reason, i) => (
                        <li key={"reason-" + i} className="evidence-item">
                          <span className="evidence-marker" /> {reason}
                        </li>
                      ))}
                    </ul>
                  )}
                  {selectedIncident.evidence && (
                    <div>
                      <h5>Positive Factors</h5>
                      <ul className="evidence-list">
                        {selectedIncident.evidence.positive.map((p: string, i: number) => (
                          <li key={"pos-"+i} className="evidence-item">
                            <span className="check-icon">+</span> {p}
                          </li>
                        ))}
                      </ul>
                      <h5>Negative Factors</h5>
                      <ul className="evidence-list">
                        {selectedIncident.evidence.negative.map((n: string, i: number) => (
                          <li key={"neg-"+i} className="evidence-item">
                            <span className="x-icon">-</span> {n}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                <div className="summary-section">
                  <div className="summary-header">
                    <h4>Operator Summary</h4>
                    <button
                      className="btn btn-secondary summary-button"
                      disabled={summaryLoading}
                      onClick={() => summarizeIncident(selectedIncident.id)}
                    >
                      {summaryLoading ? "Summarizing..." : "Summarize Evidence"}
                    </button>
                  </div>
                  {incidentSummary ? (
                    <>
                      <p>{incidentSummary.text}</p>
                      <span className="summary-source">Source: {incidentSummary.source}</span>
                    </>
                  ) : (
                    <p className="summary-empty">Uses only the deterministic evidence shown above.</p>
                  )}
                </div>

                {/* FSM Actions */}
                <div className="actions-section">
                  <h4>Actions</h4>
                  
                  {actionError && <div className="error-alert">{actionError}</div>}

                  <div className="btn-group">
                    {selectedIncident.status === "detected" && (
                      <button className="btn btn-primary" onClick={() => handleAcknowledge(selectedIncident.id)}>
                        Acknowledge
                      </button>
                    )}

                    {(selectedIncident.status === "detected" || selectedIncident.status === "acknowledged") && (
                      <div>
                        {!showCrewInput ? (
                          <button className="btn btn-primary" onClick={() => setShowCrewInput(true)}>
                            Assign Crew
                          </button>
                        ) : (
                          <div className="crew-input-group">
                            <input
                              type="text"
                              placeholder="Crew ID/Name"
                              value={crewLabelInput}
                              onChange={e => setCrewLabelInput(e.target.value)}
                            />
                            <button className="btn btn-success" onClick={() => handleAssignCrew(selectedIncident.id)}>
                              Confirm
                            </button>
                            <button className="btn btn-cancel" onClick={() => setShowCrewInput(false)}>
                              Cancel
                            </button>
                          </div>
                        )}
                      </div>
                    )}

                    {selectedIncident.status === "crew_assigned" && (
                      <button className="btn btn-success" onClick={() => handleResolve(selectedIncident.id)}>
                        Resolve
                      </button>
                    )}

                    {(selectedIncident.status === "resolved" || selectedIncident.status === "closed") && (
                      <div className="verify-note">
                        <strong>{selectedIncident.status === "resolved" ? "Awaiting Verification" : "Resolved"}</strong>
                        <p>{selectedIncident.verify_note || "System waiting for automatic closure..."}</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <p className="empty-muted">Select an incident to investigate</p>
            )}
          </div>
        </section>
      </div>

      {/* 8. Simulator (Bottom Drawer Panel) */}
      <footer className={`simulation-drawer ${showSimulation ? "expanded" : "collapsed"}`}>
        <div className="drawer-header">
          <h3>Simulation Mode</h3>
          <div className="drawer-status">
            {simResponse && <span className="sim-log">Result: {simResponse}</span>}
            <button className="btn btn-secondary drawer-toggle" onClick={() => setShowSimulation(value => !value)}>
              {showSimulation ? "Collapse" : "Expand"}
            </button>
          </div>
        </div>
        {showSimulation && <div className="simulator-grid">
          <div className="sim-group">
            <h4>Outage Injection</h4>
            <div className="sim-controls">
              <select value={simKind} onChange={e => { setSimKind(e.target.value as any); setSimTargetId(""); }}>
                <option value="feeder">Feeder Outage</option>
                <option value="dt">DT Outage</option>
                <option value="pole">Single Pole Outage</option>
                <option value="span">Span Fault</option>
              </select>

              {simKind === "pole" && (
                <input type="text" placeholder="Pole ID" value={simTargetId} onChange={e => setSimTargetId(e.target.value)} />
              )}

              {simKind === "feeder" && (
                <select value={simTargetId} onChange={e => setSimTargetId(e.target.value)}>
                  <option value="">Select Feeder</option>
                  {uniqueFeeders.map(f => (
                    <option key={f} value={f}>{f}</option>
                  ))}
                </select>
              )}

              {simKind === "dt" && (
                <select value={simTargetId} onChange={e => setSimTargetId(e.target.value)}>
                  <option value="">Select DT</option>
                  {dts.map(d => (
                    <option key={d.dt_id} value={d.dt_id}>{d.dt_id}</option>
                  ))}
                </select>
              )}

              {simKind === "span" && (
                <div className="span-inputs">
                  <input type="text" placeholder="From Pole ID" value={simSpanFrom} onChange={e => setSimSpanFrom(e.target.value)} />
                  <input type="text" placeholder="To Pole ID" value={simSpanTo} onChange={e => setSimSpanTo(e.target.value)} />
                </div>
              )}
            </div>
            <div className="sim-actions">
              <button className="btn btn-danger" onClick={() => triggerSimulation("inject")}>
                Inject Outage
              </button>
              <button className="btn btn-success" onClick={() => triggerSimulation("repair")}>
                Repair / Restore
              </button>
            </div>
          </div>

          <div className="sim-group">
            <h4>Sensor Noise Injection</h4>
            <div className="sim-controls">
              <select value={simNoiseKind} onChange={e => setSimNoiseKind(e.target.value)}>
                <option value="dead_sensor">Dead Sensor Silence</option>
                <option value="duplicate">Duplicate Event Noise</option>
                <option value="delayed">Delayed Telemetry</option>
                <option value="reorder">Out-of-Order Telemetry</option>
              </select>
              <input type="text" placeholder="Target Pole ID" value={simNoiseTarget} onChange={e => setSimNoiseTarget(e.target.value)} />
            </div>
            <div className="sim-actions">
              <button className="btn btn-secondary" onClick={triggerNoise}>
                Inject Noise
              </button>
              <button className="btn btn-success" onClick={triggerClearNoise}>
                Restore Pole
              </button>
            </div>
          </div>

           <div className="sim-group scenario-group">
             <MultifaultSelector
               dts={dts}
               feeders={uniqueFeeders}
               onResult={(msg) => {
                 setSimResponse(msg);
                 window.setTimeout(() => setRefreshTick((n) => n + 1), 800);
                 window.setTimeout(() => setRefreshTick((n) => n + 1), 2500);
               }}
             />
          </div>
        </div>}
      </footer>
    </div>
  );
}
