import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { SymbolResponse } from "@/types/api";

const SYMBOL_TYPES = [
  "Valve", "PressureVessel", "HeatExchanger", "PressureTransmitter", "Controller",
  "Pump", "Compressor", "Tank", "Instrument", "PipeFitting", "Unknown",
];

export function PropertyEditor({ symbol }: { symbol: SymbolResponse | null }) {
  const [rows, setRows] = useState<{ key: string; value: string }[]>([]);

  useEffect(() => {
    setRows(symbol ? symbol.properties.map((p) => ({ key: p.key, value: String(p.value) })) : []);
  }, [symbol?.id]);

  if (!symbol) return <aside style={{ color: "#777" }}>Select a symbol to edit its properties.</aside>;

  async function saveType(type: string) {
    await api.editSymbol(symbol!.id, { type });
  }
  async function saveProps() {
    await api.upsertProperties(
      symbol!.id,
      rows.filter((r) => r.key).map((r) => ({ key: r.key, value_type: "string", value: r.value })),
    );
  }

  return (
    <aside style={{ borderLeft: "1px solid #eee", paddingLeft: 12 }}>
      <h3>{symbol.label ?? "Symbol"}</h3>
      <p style={{ fontSize: 12, color: "#777" }}>
        v{symbol.version} · conf {symbol.classification_confidence?.toFixed(2) ?? "—"} ·
        {symbol.has_embedding ? " embedded" : " no embedding"}
      </p>

      <label>Type</label>
      <select defaultValue={symbol.type} onChange={(e) => saveType(e.target.value)} style={{ width: "100%" }}>
        {SYMBOL_TYPES.map((t) => <option key={t}>{t}</option>)}
      </select>

      <h4>Custom properties</h4>
      {rows.map((r, i) => (
        <div key={i} style={{ display: "flex", gap: 4, marginBottom: 4 }}>
          <input
            placeholder="key"
            value={r.key}
            onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))}
          />
          <input
            placeholder="value"
            value={r.value}
            onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))}
          />
        </div>
      ))}
      <button onClick={() => setRows((rs) => [...rs, { key: "", value: "" }])}>+ property</button>
      <button onClick={saveProps} style={{ marginLeft: 8 }}>Save</button>
    </aside>
  );
}
