import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { SymbolResponse } from "@/types/api";

const SYMBOL_TYPES = [
  "Valve", "PressureVessel", "HeatExchanger", "PressureTransmitter", "Controller",
  "Pump", "Compressor", "Tank", "Instrument", "PipeFitting", "Unknown",
];

export function PropertyEditor({
  symbol,
  typeColor,
}: {
  symbol: SymbolResponse | null;
  typeColor: (t: string) => string;
}) {
  const [rows, setRows] = useState<{ key: string; value: string }[]>([]);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setRows(symbol ? symbol.properties.map((p) => ({ key: p.key, value: String(p.value) })) : []);
    setSaved(false);
  }, [symbol?.id]);

  if (!symbol) {
    return (
      <aside className="card">
        <p className="muted" style={{ margin: 0 }}>Select a symbol to edit its properties.</p>
      </aside>
    );
  }

  async function saveType(type: string) {
    await api.editSymbol(symbol!.id, { type });
  }
  async function saveProps() {
    await api.upsertProperties(
      symbol!.id,
      rows.filter((r) => r.key).map((r) => ({ key: r.key, value_type: "string", value: r.value })),
    );
    setSaved(true);
  }

  return (
    <aside className="card stack">
      <div className="row" style={{ gap: 8 }}>
        <span style={{ width: 12, height: 12, borderRadius: 3, background: typeColor(symbol.type) }} />
        <h3 style={{ margin: 0 }}>{symbol.label ?? "Symbol"}</h3>
      </div>
      <p className="hint" style={{ margin: 0 }}>
        v{symbol.version} · page {symbol.page_number} ·{" "}
        conf {symbol.classification_confidence?.toFixed(2) ?? "—"} ·{" "}
        {symbol.has_embedding ? "embedded" : "no embedding"}
      </p>

      <div className="field" style={{ marginBottom: 0 }}>
        <span className="label">Type</span>
        <select className="select" defaultValue={symbol.type} onChange={(e) => saveType(e.target.value)}>
          {SYMBOL_TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
      </div>

      <div>
        <span className="label">Custom properties</span>
        <div className="stack" style={{ gap: 6, marginTop: 6 }}>
          {rows.map((r, i) => (
            <div key={i} className="row" style={{ gap: 6 }}>
              <input className="input" placeholder="key" value={r.key}
                onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))} />
              <input className="input" placeholder="value" value={r.value}
                onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
            </div>
          ))}
        </div>
      </div>
      <div className="row">
        <button className="btn btn--ghost" onClick={() => setRows((rs) => [...rs, { key: "", value: "" }])}>
          + property
        </button>
        <button className="btn btn--primary" onClick={saveProps}>Save</button>
        {saved && <span className="badge badge--success">Saved</span>}
      </div>
    </aside>
  );
}
