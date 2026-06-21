import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { ProcessingStatus } from "@/types/api";

const TERMINAL: ProcessingStatus[] = ["COMPLETED", "FAILED", "CANCELLED"];

export function useDocuments() {
  return useQuery({ queryKey: ["documents"], queryFn: () => api.listDocuments() });
}

export function useDocumentStatus(id: string) {
  return useQuery({
    queryKey: ["document-status", id],
    queryFn: () => api.documentStatus(id),
    // Poll while the document is still processing; stop once terminal.
    refetchInterval: (q) =>
      q.state.data && TERMINAL.includes(q.state.data.status) ? false : 2000,
  });
}

export function useSymbols(documentId: string, page?: number) {
  return useQuery({
    queryKey: ["symbols", documentId, page],
    queryFn: () => api.listSymbols(documentId, page),
    enabled: !!documentId,
  });
}

export function useGraph(documentId: string) {
  return useQuery({
    queryKey: ["graph", documentId],
    queryFn: () => api.graph(documentId),
    enabled: !!documentId,
  });
}

export function useEditSymbol(documentId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: Record<string, unknown> }) =>
      api.editSymbol(id, patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["symbols", documentId] }),
  });
}

export function useUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.uploadDocument(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}
