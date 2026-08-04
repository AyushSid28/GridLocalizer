import React, { useState } from 'react';
import * as api from '../api';

type FaultKind = 'feeder' | 'dt' | 'span' | 'pole';

type Fault = {
  id: number | string;
  kind: FaultKind;
  target_id?: string;
  span_from?: string;
  span_to?: string;
};

type DT = {
  dt_id: string;
  feeder_id: string;
};

type RestorableIncident = {
  id: string;
  kind: 'feeder' | 'dt' | 'span' | 'sensor';
  status: 'detected' | 'acknowledged' | 'crew_assigned' | 'resolved' | 'verified' | 'closed';
  feeder_id: string | null;
  dt_id: string | null;
  span_from: string | null;
  span_to: string | null;
};

const LAST_SCENARIO_KEY = 'grid:lastInjectedScenario';

function loadLastInjectedScenario(): Fault[] {
  try {
    const raw = window.localStorage.getItem(LAST_SCENARIO_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveLastInjectedScenario(faults: Fault[]) {
  window.localStorage.setItem(LAST_SCENARIO_KEY, JSON.stringify(faults));
}

function clearLastInjectedScenario() {
  window.localStorage.removeItem(LAST_SCENARIO_KEY);
}

interface MultifaultSelectorProps {
  dts: DT[];
  feeders: string[];
  incidents: RestorableIncident[];
  onResult: (result: string | null) => void;
}

const MultifaultSelector: React.FC<MultifaultSelectorProps> = ({ dts, feeders, incidents, onResult }) => {
  void dts;
  void feeders;

  const [faults, setFaults] = useState<Fault[]>([]);
  // Remember the last injected faults so Restore can replay them
  const [lastInjected, setLastInjected] = useState<Fault[]>(loadLastInjectedScenario);
  const [type, setType] = useState<FaultKind>('dt');
  const [targetId, setTargetId] = useState('');
  const [spanFrom, setSpanFrom] = useState('');
  const [spanTo, setSpanTo] = useState('');
  const [isInjecting, setIsInjecting] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const resetDraft = () => {
    setTargetId('');
    setSpanFrom('');
    setSpanTo('');
    setType('dt');
  };

  const addFault = () => {
    if (type === 'span' && (!spanFrom.trim() || !spanTo.trim())) {
      setMessage('Error: Span requires both From and To IDs');
      return;
    }
    if (type !== 'span' && !targetId.trim()) {
      setMessage('Error: Target ID required');
      return;
    }
    const newFault: Fault = {
      id: Date.now(),
      kind: type,
      target_id: type !== 'span' ? targetId.trim() : undefined,
      span_from: type === 'span' ? spanFrom.trim() : undefined,
      span_to: type === 'span' ? spanTo.trim() : undefined,
    };
    setFaults(prev => [...prev, newFault]);
    resetDraft();
    setMessage(null);
  };

  const removeFault = (id: number | string) => {
    setFaults(prev => prev.filter(f => f.id !== id));
  };

  const openIncidentFaults: Fault[] = incidents.reduce<Fault[]>((acc, incident) => {
    if (['verified', 'closed'].includes(incident.status)) return acc;

      if (incident.kind === 'dt' && incident.dt_id) {
        acc.push({ id: incident.id, kind: 'dt', target_id: incident.dt_id });
        return acc;
      }
      if (incident.kind === 'feeder' && incident.feeder_id) {
        acc.push({ id: incident.id, kind: 'feeder', target_id: incident.feeder_id });
        return acc;
      }
      if (incident.kind === 'span' && incident.span_from && incident.span_to) {
        acc.push({ id: incident.id, kind: 'span', span_from: incident.span_from, span_to: incident.span_to });
        return acc;
      }
      return acc;
    }, []);

  const injectFaults = async () => {
    if (faults.length === 0) {
      setMessage('Error: No faults to inject');
      return;
    }
    setIsInjecting(true);
    try {
      const data = await api.createScenario(faults);
      const affected = data?.affected_devices ?? 0;
      const injectedFaults = [...faults];
      setMessage(`Injected: ${affected} telemetry devices signaled. Click "Restore All" to undo.`);
      setLastInjected(injectedFaults);
      saveLastInjectedScenario(injectedFaults);
      setFaults([]);
      onResult(affected.toString());
    } catch (e: any) {
      setMessage(`Error: ${e.message}`);
      onResult(null);
    } finally {
      setIsInjecting(false);
    }
  };

  const restoreAll = async () => {
    const savedFaults = lastInjected.length > 0 ? lastInjected : loadLastInjectedScenario();
    const faultsToRestore = savedFaults.length > 0 ? savedFaults : openIncidentFaults;
    if (faultsToRestore.length === 0) {
      setMessage('No open outage incidents available to restore.');
      return;
    }
    setLastInjected(faultsToRestore);
    setIsRestoring(true);
    setMessage(null);
    try {
      await Promise.all(
        faultsToRestore.map(f =>
          api.repairSimulation({
            kind: f.kind,
            target_id: f.target_id ?? null,
            span_from: f.span_from ?? null,
            span_to: f.span_to ?? null,
          })
        )
      );
      setMessage(`Restore telemetry sent for ${faultsToRestore.length} outage(s).`);
      setLastInjected([]);
      clearLastInjectedScenario();
      onResult(null);
    } catch (e: any) {
      setMessage(`Restore error: ${e.message}`);
    } finally {
      setIsRestoring(false);
    }
  };

  const savedInjected = lastInjected.length > 0 ? lastInjected : loadLastInjectedScenario();
  const restoreCount = savedInjected.length || openIncidentFaults.length;
  const visibleFaults = faults.length > 0 ? faults : (savedInjected.length > 0 ? savedInjected : openIncidentFaults);
  const showingLastInjected = faults.length === 0 && savedInjected.length > 0;
  const showingOpenIncidents = faults.length === 0 && savedInjected.length === 0 && openIncidentFaults.length > 0;

  return (
    <div className="multifault-selector">
      <h4>Multifault Selector</h4>

      <div className="multi-draft">
        <select value={type} onChange={e => setType(e.target.value as FaultKind)}>
          <option value="dt">DT Fault</option>
          <option value="span">Span Fault</option>
          <option value="feeder">Feeder Fault</option>
          <option value="pole">Single Pole Outage</option>
        </select>
        {(type === 'dt' || type === 'feeder' || type === 'pole') && (
          <input
            placeholder={type === 'pole' ? 'Pole ID' : 'Target ID (e.g. D-0005)'}
            value={targetId}
            onChange={e => setTargetId(e.target.value)}
          />
        )}
        {type === 'span' && (
          <div className="multi-span-inputs">
            <input placeholder="From Pole ID" value={spanFrom} onChange={e => setSpanFrom(e.target.value)} />
            <input placeholder="To Pole ID" value={spanTo} onChange={e => setSpanTo(e.target.value)} />
          </div>
        )}
        <button className="btn btn-secondary" onClick={addFault}>Add Fault</button>
      </div>

      <div className="sim-actions multifault-actions">
        <button
          className="btn btn-danger"
          onClick={injectFaults}
          disabled={isInjecting || isRestoring || faults.length === 0}
        >
          {isInjecting ? 'Injecting...' : 'Inject Faults'}
        </button>

        <button
          className="btn btn-success"
          onClick={restoreAll}
          disabled={isRestoring || isInjecting}
          title={restoreCount === 0 ? 'Inject faults first to enable restore' : `Restore ${restoreCount} fault(s)`}
        >
          {isRestoring ? 'Restoring...' : `Restore All${restoreCount > 0 ? ` (${restoreCount})` : ''}`}
        </button>
      </div>

      <ul className="selected-fault-list">
        {visibleFaults.length === 0 && <li className="empty-compact">No scenario faults added</li>}
        {showingLastInjected && <li className="empty-compact">Last injected scenario</li>}
        {showingOpenIncidents && <li className="empty-compact">Open incidents available to restore</li>}
        {visibleFaults.map(f => (
          <li key={f.id} className="selected-fault-row">
            <span>{f.kind.toUpperCase()} - {f.kind === 'span' ? `${f.span_from} to ${f.span_to}` : f.target_id}</span>
            {showingLastInjected || showingOpenIncidents ? (
              <span className="fault-row-state">{showingOpenIncidents ? 'Open' : 'Injected'}</span>
            ) : (
              <button className="btn btn-cancel" onClick={() => removeFault(f.id)}>Remove</button>
            )}
          </li>
        ))}
      </ul>

      {message && <div className="msg">{message}</div>}
    </div>
  );
};

export default MultifaultSelector;
