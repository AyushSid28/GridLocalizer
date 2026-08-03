import React, { useEffect, useState } from "react";

type BreadcrumbData = {
  substation_id: string;
  feeder_id: string;
  dt_id: string;
  pole_count: number;
  affected_poles: number;
};

type Props = {
  dtId: string | null;
  apiBase: string;
};

export const Breadcrumb: React.FC<Props> = ({ dtId, apiBase }) => {
  const [data, setData] = useState<BreadcrumbData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!dtId) {
      setData(null);
      return;
    }
    const fetchBreadcrumb = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${apiBase}/breadcrumb/dt/${dtId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        setData(json);
      } catch (e) {
        console.error("Breadcrumb fetch error", e);
        setError("Failed to load hierarchy");
      } finally {
        setLoading(false);
      }
    };
    fetchBreadcrumb();
  }, [dtId, apiBase]);

  if (!dtId) return null;
  if (loading) return <div className="breadcrumb loading">Loading hierarchy…</div>;
  if (error) return <div className="breadcrumb error">{error}</div>;
  if (!data) return null;

  return (
    <div className="breadcrumb">
      <nav aria-label="breadcrumb" className="breadcrumb-nav">
        <ol className="breadcrumb-list" style={{ display: "flex", gap: "0.5rem", alignItems: "center", fontSize: "0.85rem", color: "var(--text-muted)" }}>
          <li className="breadcrumb-item">{data.substation_id}</li>
          <li className="breadcrumb-separator">›</li>
          <li className="breadcrumb-item">{data.feeder_id}</li>
          <li className="breadcrumb-separator">›</li>
          <li className="breadcrumb-item active" aria-current="page">{data.dt_id}</li>
        </ol>
      </nav>
      <div className="breadcrumb-stats" style={{ marginTop: "0.25rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
        Poles: {data.pole_count} | Affected: {data.affected_poles}
      </div>
    </div>
  );
};
