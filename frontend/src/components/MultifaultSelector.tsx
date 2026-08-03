import React, { useState } from 'react';
import * as api from '../api';

type FaultKind = 'feeder' | 'dt' | 'span' | 'sensor_noise';

type Fault = {
  id: number;
  kind: FaultKind;
  target_id?: string;
  span_from?: string;
  span_to?: string;
};

type DT = {
  dt_id: string;
  feeder_id: string;
};

interface MultifaultSelectorProps {
  dts: DT[];
  feeders: string[];
  onResult: (result: string | null) => void;
}

const MultifaultSelector: React.FC<MultifaultSelectorProps> = ({ dts, feeders, onResult }) => {
  void dts;
  void feeders;

  const [faults, setFaults] = useState<Fault[]>([]);
  // Remember the last injected faults so Restore can replay them
  const [lastInjected, setLastInjected] = useState<Fault[]>([]);
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

  const removeFault = (id: number) => {
    setFaults(prev => prev.filter(f => f.id !== id));
  };

  const injectFaults = async () => {
    if (faults.length === 0) {
      setMessage('Error: No faults to inject');
      return;
    }
    setIsInjecting(true);
    try {
      const data = await api.createScenario(faults);
      const affected = data?.affected_devices ?? 0;
      setMessage(`✅ Injected: ${affected} devices affected. Click "Restore All" to undo.`);
      setLastInjected(faults);  // save for restore
      setFaults([]);
      onResult(affected.toString());
    } catch (e: any) {
      setMessage(`❌ Error: ${e.message}`);
      onResult(null);
    } finally {
      setIsInjecting(false);
    }
  };

  const restoreAll = async () => {
    if (lastInjected.length === 0) {
      setMessage('Nothing to restore. Inject faults first.');
      return;
    }
    setIsRestoring(true);
    setMessage(null);
    try {
      // Call /sim/repair for each fault in the last injected scenario
      await Promise.all(
        lastInjected.map(f =>
          api.repairSimulation({
            kind: f.kind,
            target_id: f.target_id ?? null,
            span_from: f.span_from ?? null,
            span_to: f.span_to ?? null,
          })
        )
      );
      setMessage(`✅ Restored ${lastInjected.length} fault(s) successfully.`);
      setLastInjected([]);
      onResult(null);
    } catch (e: any) {
      setMessage(`❌ Restore error: ${e.message}`);
    } finally {
      setIsRestoring(false);
    }
  };

  return (
    <div className="multifault-selector">
      <h4>Multifault Selector</h4>

      <div className="draft">
        <select value={type} onChange={e => setType(e.target.value as FaultKind)}>
          <option value="dt">DT Fault</option>
          <option value="span">Span Fault</option>
          <option value="feeder">Feeder Fault</option>
          <option value="sensor_noise">Sensor Noise</option>
        </select>
        {(type === 'dt' || type === 'feeder' || type === 'sensor_noise') && (
          <input
            placeholder="Target ID (e.g. D-0005)"
            value={targetId}
            onChange={e => setTargetId(e.target.value)}
          />
        )}
        {type === 'span' && (
          <>
            <input placeholder="From Pole ID" value={spanFrom} onChange={e => setSpanFrom(e.target.value)} />
            <input placeholder="To Pole ID" value={spanTo} onChange={e => setSpanTo(e.target.value)} />
          </>
        )}
        <button onClick={addFault}>Add Fault</button>
      </div>

      <ul className="selected-list">
        {faults.map(f => (
          <li key={f.id}>
            <span>{f.kind.toUpperCase()} — {f.kind === 'span' ? `${f.span_from} → ${f.span_to}` : f.target_id}</span>
            <button onClick={() => removeFault(f.id)}>✕</button>
          </li>
        ))}
      </ul>

      {message && <div className="msg">{message}</div>}

      <div className="multifault-actions">
        <button
          className="btn btn-sim"
          onClick={injectFaults}
          disabled={isInjecting || isRestoring || faults.length === 0}
        >
          {isInjecting ? 'Injecting…' : '⚡ Inject Faults'}
        </button>

        <button
          className="btn btn-sim"
          onClick={restoreAll}
          disabled={isRestoring || isInjecting || lastInjected.length === 0}
          title={lastInjected.length === 0 ? 'Inject faults first to enable restore' : `Restore ${lastInjected.length} fault(s)`}
        >
          {isRestoring ? 'Restoring…' : `✅ Restore All${lastInjected.length > 0 ? ` (${lastInjected.length})` : ''}`}
        </button>
      </div>
    </div>
  );
};

export default MultifaultSelector;
