import React, { useEffect, useState } from "react";
import * as api from "../api";

type BreadcrumbData = {
  substation_id: string;
  feeder_id: string;
  dt_id: string;
  pole_count: number;
  affected_poles: number;
};

type Props = {
  dtId: string | null;
};

export const Breadcrumb: React.FC<Props> = ({ dtId }) => {
  const [data, setData] = useState<BreadcrumbData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!dtId) {
      setData(null);
      return;
    }
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const json = (await api.fetchBreadcrumb(dtId)) as BreadcrumbData;
        if (!cancelled) setData(json);
      } catch (e) {
        console.error("Breadcrumb fetch error", e);
        if (!cancelled) setError("Failed to load hierarchy");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [dtId]);

  if (!dtId) return null;
  if (loading) return <div className="breadcrumb muted">Loading hierarchy…</div>;
  if (error) return <div className="breadcrumb error">{error}</div>;
  if (!data) return null;

  const parts = [data.substation_id, data.feeder_id, data.dt_id].filter(Boolean);

  return (
    <div className="breadcrumb">
      <nav aria-label="Network path" className="breadcrumb-nav">
        {parts.map((part, index) => (
          <React.Fragment key={`${part}-${index}`}>
            {index > 0 && <span className="breadcrumb-sep" aria-hidden="true">›</span>}
            <span className={`breadcrumb-part ${index === parts.length - 1 ? "active" : ""}`}>
              {part}
            </span>
          </React.Fragment>
        ))}
      </nav>
      <div className="breadcrumb-stats">
        Poles: {data.pole_count} · Dark now: {data.affected_poles}
      </div>
    </div>
  );
};
