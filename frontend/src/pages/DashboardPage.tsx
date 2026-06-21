import { Link } from "react-router-dom";
import { StatusBadge } from "@/components/StatusBadge";
import { useDocuments } from "@/api/hooks";

export function DashboardPage() {
  const { data, isLoading } = useDocuments();

  return (
    <div>
      <div className="page-title">
        <h2>Documents</h2>
        <Link className="btn btn--primary" to="/upload">Upload PDF</Link>
      </div>

      {isLoading ? (
        <p className="muted">Loading…</p>
      ) : data && data.items.length > 0 ? (
        <div className="card card--pad-0">
          <table className="table">
            <thead>
              <tr>
                <th>Filename</th><th>Status</th><th>Pages</th><th>Uploaded</th><th></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((d) => (
                <tr key={d.id}>
                  <td style={{ fontWeight: 500 }}>{d.filename}</td>
                  <td><StatusBadge status={d.status} /></td>
                  <td>{d.page_count}</td>
                  <td className="text-secondary">{new Date(d.created_at).toLocaleString()}</td>
                  <td>
                    <div className="row" style={{ gap: 8 }}>
                      <Link className="btn btn--ghost" to={`/documents/${d.id}/canvas`}>Canvas</Link>
                      <Link className="btn btn--ghost" to={`/documents/${d.id}/graph`}>Graph</Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="card" style={{ textAlign: "center", padding: 48 }}>
          <p className="muted">No documents yet.</p>
          <Link className="btn btn--primary" to="/upload">Upload your first drawing</Link>
        </div>
      )}
    </div>
  );
}
