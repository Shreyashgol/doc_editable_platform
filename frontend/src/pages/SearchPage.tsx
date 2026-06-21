import { useState } from "react";
import { api } from "@/api/client";
import type { SearchHit } from "@/types/api";

export function SearchPage() {
  const [text, setText] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    try {
      const res = await api.searchSimilar({ text, top_k: 20 });
      setHits(res.hits);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <h2>Semantic search</h2>
      <p style={{ color: "#777" }}>
        Cross-modal text → symbol search over the vector index (foundation for RAG).
      </p>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          style={{ flex: 1 }}
          placeholder="e.g. pressure transmitter"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
        />
        <button onClick={run} disabled={!text || loading}>{loading ? "…" : "Search"}</button>
      </div>
      <ul>
        {hits.map((h) => (
          <li key={h.symbol.id}>
            <strong>{h.symbol.label ?? h.symbol.type}</strong> ({h.symbol.type}) — score{" "}
            {h.score.toFixed(3)} · page {h.symbol.page_number}
          </li>
        ))}
      </ul>
      {hits.length === 0 && !loading && <p style={{ color: "#777" }}>No results yet.</p>}
    </div>
  );
}
