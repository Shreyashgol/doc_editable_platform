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
      <h2>Upload PDF</h2>
      <p>P&amp;IDs, engineering drawings, flowcharts, schematics. Max 50 MB.</p>
      <input type="file" accept="application/pdf" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      <button disabled={!file || upload.isPending} onClick={submit} style={{ marginLeft: 8 }}>
        {upload.isPending ? "Uploading…" : "Upload & process"}
      </button>
      {upload.isError && (
        <p style={{ color: "crimson" }}>
          {(upload.error as any)?.response?.data?.detail ?? "Upload failed"}
        </p>
      )}
    </div>
  );
}
