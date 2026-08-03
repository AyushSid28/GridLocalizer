// src/api.ts
// Centralized API wrapper for simulation and network endpoints.
// This file abstracts fetch calls used throughout the UI.
// It expects the base URL to be provided via the VITE_API_URL env variable.

const apiBase = import.meta.env.VITE_API_URL ?? '';

export async function fetchHealth() {
  const res = await fetch(`${apiBase}/health`);
  if (!res.ok) throw new Error(`Health fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchSummary() {
  const res = await fetch(`${apiBase}/network/summary`);
  if (!res.ok) throw new Error(`Summary fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchDTs() {
  const res = await fetch(`${apiBase}/network/dts`);
  if (!res.ok) throw new Error(`DTs fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchDTDetail(dtId: string) {
  const res = await fetch(`${apiBase}/network/dts/${dtId}`);
  if (!res.ok) throw new Error(`DT detail fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchIncidents() {
  const res = await fetch(`${apiBase}/incidents`);
  if (!res.ok) throw new Error(`Incidents fetch failed: ${res.status}`);
  return res.json();
}

export async function injectOutage(payload: any) {
  const res = await fetch(`${apiBase}/sim/inject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function injectNoise(payload: any) {
  const res = await fetch(`${apiBase}/sim/noise`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function repairSimulation(payload: any) {
  const res = await fetch(`${apiBase}/sim/repair`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function createScenario(faults: any[]) {
  const res = await fetch(`${apiBase}/sim/scenario`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ faults }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function acknowledgeIncident(id: string) {
  const res = await fetch(`${apiBase}/incidents/${id}/acknowledge`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function assignCrew(id: string, crew_label: string) {
  const res = await fetch(`${apiBase}/incidents/${id}/assign_crew`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ crew_label }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function resolveIncident(id: string) {
  const res = await fetch(`${apiBase}/incidents/${id}/resolve`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}
