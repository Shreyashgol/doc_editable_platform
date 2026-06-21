import type { ProcessingStatus } from "@/types/api";

const VARIANT: Record<ProcessingStatus, string> = {
  COMPLETED: "badge--success",
  FAILED: "badge--danger",
  CANCELLED: "badge",
  UPLOADED: "badge--info",
  VALIDATING: "badge--warning",
  QUEUED: "badge--warning",
  PROCESSING: "badge--warning",
  OCR_RUNNING: "badge--warning",
  CLASSIFYING: "badge--warning",
  EMBEDDING: "badge--warning",
  RETRYING: "badge--warning",
};

const ACTIVE = new Set<ProcessingStatus>([
  "UPLOADED", "VALIDATING", "QUEUED", "PROCESSING", "OCR_RUNNING",
  "CLASSIFYING", "EMBEDDING", "RETRYING",
]);

export function StatusBadge({ status }: { status: ProcessingStatus }) {
  return (
    <span className={`badge ${VARIANT[status]}`}>
      {ACTIVE.has(status) && <span className="pulse" />}
      {status}
    </span>
  );
}
