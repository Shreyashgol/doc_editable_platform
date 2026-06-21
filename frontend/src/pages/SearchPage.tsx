import { useState } from "react";
import { api } from "@/api/client";
import type { SearchHit } from "@/types/api";

export function SearchPage() {
  const [text, setText] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [loading, setLoading] = useState(false);

  async function run() {
    if (!text) return;
    setLoading(true);
    try {
      setHits((await api.searchSimilar({ text, top_k: 20 })).hits);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="page-title"><h2>Semantic search</h2></div>
      <div className="card stack">
        <p className="text-secondary" style={{ margin: 0 }}>
          Cross-modal text → symbol search over the pgvector index (foundation for RAG).
        </p>
        <div className="row">
          <input
            className="input"
            placeholder="e.g. pressure transmitter"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && run()}
          />
          <button className="btn btn--primary" onClick={run} disabled={!text || loading}>
            {loading ? "…" : "Search"}
          </button>
        </div>
      </div>

      {hits && (
        <div className="card card--pad-0" style={{ marginTop: 16 }}>
          {hits.length === 0 ? (
            <p className="muted" style={{ padding: 20 }}>No matching symbols.</p>
          ) : (
            <table className="table">
              <thead>
                <tr><th>Symbol</th><th>Type</th><th>Page</th><th>Score</th></tr>
              </thead>
              <tbody>
                {hits.map((h) => (
                  <tr key={h.symbol.id}>
                    <td style={{ fontWeight: 500 }}>{h.symbol.label ?? "—"}</td>
                    <td>{h.symbol.type}</td>
                    <td>{h.symbol.page_number}</td>
                    <td className="text-secondary">{h.score.toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
