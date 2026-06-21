import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUpload } from "@/api/hooks";

export function UploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const upload = useUpload();
  const navigate = useNavigate();

  async function submit() {
    if (!file) return;
    const res = await upload.mutateAsync(file);
    navigate(`/documents/${res.id}/canvas`);
  }

  return (
    <div>
      <div className="page-title"><h2>Upload drawing</h2></div>
      <div className="card stack" style={{ maxWidth: 560 }}>
        <p className="text-secondary" style={{ margin: 0 }}>
          P&amp;IDs, engineering drawings, flowcharts, schematics, symbol libraries. PDF only, max 50&nbsp;MB.
        </p>
        <label className="field" style={{ marginBottom: 0 }}>
          <span className="label">PDF file</span>
          <input className="input" type="file" accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        {file && <p className="hint">Selected: {file.name} ({(file.size / 1024).toFixed(0)} KB)</p>}
        <div className="row">
          <button className="btn btn--primary" disabled={!file || upload.isPending} onClick={submit}>
            {upload.isPending ? "Uploading…" : "Upload & process"}
          </button>
        </div>
        {upload.isError && (
          <p className="error-text">
            {(upload.error as any)?.response?.data?.detail ?? "Upload failed"}
          </p>
        )}
      </div>
    </div>
  );
}
