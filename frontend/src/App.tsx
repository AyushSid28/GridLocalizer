from { useEffect, useState } from "react";

type Health = {
  status: string;
  service: string;
};

type Summary = {
  poles: number;
  dts: number;
  devices: number;
  wiring_known_dts: number;
  wiring_unknown_dts: number;
  inferred_poles: number;
};

const apiBase = import.meta.env.VITE_API_URL ?? "";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      try {
        const [hRes, sRes] = await Promise.all([
          fetch(`${apiBase}/health`),
          fetch(`${apiBase}/network/summary`),
        ]);
        if (!hRes.ok) throw new Error(`health HTTP ${hRes.status}`);
        const healthBody = (await hRes.json()) as Health;
        const summaryBody = sRes.ok ? ((await sRes.json()) as Summary) : null;
        if (!cancelled) {
          setHealth(healthBody);
          setSummary(summaryBody);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "unreachable");
          setHealth(null);
        }
      }
    }

    refresh();
    const id = window.setInterval(refresh, 5000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">KSPDB · Subdivision SD-07</p>
          <h1>Control room</h1>
        </div>
        <div className={`pill ${health ? "ok" : "bad"}`}>
          {health ? `API ${health.status}` : error ? `API down · ${error}` : "Checking…"}
        </div>
      </header>

      {summary && (
        <section className="stats">
          <div>
            <strong>{summary.poles.toLocaleString()}</strong>
            <span>poles</span>
          </div>
          <div>
            <strong>{summary.dts}</strong>
            <span>transformers</span>
          </div>
          <div>
            <strong>{summary.devices.toLocaleString()}</strong>
            <span>devices</span>
          </div>
          <div>
            <strong>
              {summary.wiring_known_dts}/{summary.dts}
            </strong>
            <span>wiring known</span>
          </div>
        </section>
      )}

      <main className="board">
        <section className="panel list-panel">
          <h2>Open incidents</h2>
          <p className="muted">
            Network is seeded. Localization and tickets come next — inject a fault after P3.
          </p>
        </section>

        <section className="panel map-panel">
          <h2>Network map</h2>
          <p className="muted">
            {summary
              ? `${summary.inferred_poles.toLocaleString()} poles sit on inferred topology (digitization gap).`
              : "Waiting for network summary…"}
          </p>
        </section>
      </main>
    </div>
  );
}
