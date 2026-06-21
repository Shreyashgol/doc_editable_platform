import { create } from "zustand";
import { persist } from "zustand/middleware";

export type ThemeMode = "light" | "dark" | "system";

function systemPrefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

/** Resolve a mode to the concrete theme to apply. */
export function resolveTheme(mode: ThemeMode): "light" | "dark" {
  return mode === "system" ? (systemPrefersDark() ? "dark" : "light") : mode;
}

/** Apply the resolved theme to <html data-theme>. */
export function applyTheme(mode: ThemeMode): void {
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", resolveTheme(mode));
  }
}

interface ThemeState {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
  cycle: () => void;
}

export const useTheme = create<ThemeState>()(
  persist(
    (set, get) => ({
      mode: "system",
      setMode: (mode) => {
        applyTheme(mode);
        set({ mode });
      },
      cycle: () => {
        const order: ThemeMode[] = ["light", "dark", "system"];
        const next = order[(order.indexOf(get().mode) + 1) % order.length];
        applyTheme(next);
        set({ mode: next });
      },
    }),
    { name: "docai-theme" },
  ),
);

// Re-apply when the OS theme changes while in "system" mode.
if (typeof window !== "undefined" && window.matchMedia) {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (useTheme.getState().mode === "system") applyTheme("system");
  });
}
