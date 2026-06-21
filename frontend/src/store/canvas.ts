import { create } from "zustand";

// UI-only canvas state (server state lives in React Query). Tracks selection, zoom and pan.
interface CanvasState {
  selectedIds: Set<string>;
  scale: number;
  position: { x: number; y: number };
  select: (id: string, additive?: boolean) => void;
  clearSelection: () => void;
  setScale: (scale: number) => void;
  setPosition: (pos: { x: number; y: number }) => void;
}

export const useCanvas = create<CanvasState>((set) => ({
  selectedIds: new Set(),
  scale: 1,
  position: { x: 0, y: 0 },
  select: (id, additive = false) =>
    set((s) => {
      const next = additive ? new Set(s.selectedIds) : new Set<string>();
      next.has(id) ? next.delete(id) : next.add(id);
      return { selectedIds: next };
    }),
  clearSelection: () => set({ selectedIds: new Set() }),
  setScale: (scale) => set({ scale: Math.min(8, Math.max(0.1, scale)) }),
  setPosition: (position) => set({ position }),
}));
