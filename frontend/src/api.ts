// Centralized API client. Production on Vercel uses same-origin paths (see vercel.json rewrites).
// Override with VITE_API_URL to call Render directly.

const RENDER_DEFAULT =
  "https://gridlocalizer-backend.onrender.com";

function resolveApiBase(): string {
  const fromEnv = import.meta.env.VITE_API_URL?.trim();
  if (fromEnv) return fromEnv.replace(/\/$/, "");
  if (import.meta.env.PROD && typeof window !== "undefined") {
    const host = window.location.hostname;
    if (host.includes("vercel.app") || host === "gridlocalizer.vercel.app") {
      return "";
    }
    return RENDER_DEFAULT;
  }
  return "";
}

export const apiBase = resolveApiBase();

const DEFAULT_TIMEOUT_MS = 90_000;

async function fetchWithTimeout(
  path: string,
  init?: RequestInit,
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(`${apiBase}${path}`, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timer);
  }
}

export async function fetchHealth() {
  const res = await fetchWithTimeout("/health");
  if (!res.ok) throw new Error(`Health fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchSummary() {
  const res = await fetchWithTimeout("/network/summary");
  if (!res.ok) throw new Error(`Summary fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchDTs() {
  const res = await fetchWithTimeout("/network/dts");
  if (!res.ok) throw new Error(`DTs fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchDTDetail(dtId: string) {
  const res = await fetchWithTimeout(`/network/dts/${dtId}`);
  if (!res.ok) throw new Error(`DT detail fetch failed: ${res.status}`);
  return res.json();
}

export async function fetchIncidents() {
  const res = await fetchWithTimeout("/incidents");
  if (!res.ok) throw new Error(`Incidents fetch failed: ${res.status}`);
  return res.json();
}

async function postJson(path: string, body?: unknown) {
  const res = await fetchWithTimeout(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string })?.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

export async function injectOutage(payload: unknown) {
  return postJson("/sim/inject", payload);
}

export async function injectNoise(payload: unknown) {
  return postJson("/sim/noise", payload);
}

export async function clearNoise(payload: unknown) {
  return postJson("/sim/clear_noise", payload);
}

export async function repairSimulation(payload: unknown) {
  return postJson("/sim/repair", payload);
}

export async function createScenario(faults: unknown[]) {
  return postJson("/sim/scenario", { faults });
}

export async function acknowledgeIncident(id: string) {
  return postJson(`/incidents/${id}/acknowledge`);
}

export async function assignCrew(id: string, crew_label: string) {
  return postJson(`/incidents/${id}/assign_crew`, { crew_label });
}

export async function resolveIncident(id: string) {
  return postJson(`/incidents/${id}/resolve`);
}
