import { Link } from "react-router-dom";
import { useDocuments } from "@/api/hooks";
import type { ProcessingStatus } from "@/types/api";

const COLORS: Partial<Record<ProcessingStatus, string>> = {
  COMPLETED: "#157f3b",
  FAILED: "#c0392b",
  CANCELLED: "#7f8c8d",
};

export function DashboardPage() {
  const { data, isLoading } = useDocuments();
  if (isLoading) return <p>Loading…</p>;

  return (
    <div>
      <h2>Documents</h2>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ textAlign: "left", borderBottom: "1px solid #ccc" }}>
            <th>Filename</th><th>Status</th><th>Pages</th><th>Uploaded</th><th></th>
          </tr>
        </thead>
        <tbody>
          {data?.items.map((d) => (
            <tr key={d.id} style={{ borderBottom: "1px solid #eee" }}>
              <td>{d.filename}</td>
              <td style={{ color: COLORS[d.status] ?? "#2c3e50", fontWeight: 600 }}>{d.status}</td>
              <td>{d.page_count}</td>
              <td>{new Date(d.created_at).toLocaleString()}</td>
              <td>
                <Link to={`/documents/${d.id}/canvas`}>Canvas</Link>{" · "}
                <Link to={`/documents/${d.id}/graph`}>Graph</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {data?.items.length === 0 && <p>No documents yet. <Link to="/upload">Upload one.</Link></p>}
    </div>
  );
}
