// Types mirroring the backend's Pydantic response models (docs/02 API spec).

export type ProcessingStatus =
  | "UPLOADED" | "VALIDATING" | "QUEUED" | "PROCESSING" | "OCR_RUNNING"
  | "CLASSIFYING" | "EMBEDDING" | "COMPLETED" | "FAILED" | "RETRYING" | "CANCELLED";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface DocumentResponse {
  id: string;
  filename: string;
  status: ProcessingStatus;
  page_count: number;
  size_bytes: number;
  mime_type: string;
  created_at: string;
  updated_at: string;
}

export interface JobView {
  stage: string;
  stage_status: string;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  timings: Record<string, number>;
}

export interface DocumentStatusResponse {
  id: string;
  status: ProcessingStatus;
  page_count: number;
  job: JobView | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface BBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface SymbolProperty {
  key: string;
  value_type: "string" | "number" | "bool" | "date" | "json";
  value: unknown;
}

export interface SymbolResponse {
  id: string;
  document_id: string;
  page_number: number;
  type: string;
  label: string | null;
  bbox: BBox;
  centroid: { x: number; y: number };
  rotation: number;
  crop_uri: string;
  classification_method: string | null;
  classification_confidence: number | null;
  has_embedding: boolean;
  version: number;
  properties: SymbolProperty[];
  created_at: string;
  updated_at: string;
}

export interface GraphNode {
  id: string;
  type: string;
  label: string | null;
  page_number: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  confidence: number;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface SearchHit {
  score: number;
  symbol: SymbolResponse;
}

export interface SearchResponse {
  hits: SearchHit[];
}
