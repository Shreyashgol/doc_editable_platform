import { useMemo } from "react";
import { useTheme } from "@/store/theme";

// Konva renders to <canvas>, so it can't use CSS variables directly. This hook reads the
// resolved CSS custom properties (recomputing whenever the theme mode changes) plus a
// theme-aware symbol-type palette.
export function useThemeColors() {
  const mode = useTheme((s) => s.mode);

  return useMemo(() => {
    const css = (name: string, fallback: string) => {
      if (typeof window === "undefined") return fallback;
      const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      return v || fallback;
    };
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    const TYPE: Record<string, string> = dark
      ? {
          Valve: "#60a5fa", Pump: "#4ade80", PressureVessel: "#c084fc",
          HeatExchanger: "#fb923c", PressureTransmitter: "#2dd4bf", Controller: "#f87171",
          Unknown: "#94a3b8",
        }
      : {
          Valve: "#2563eb", Pump: "#16a34a", PressureVessel: "#7c3aed",
          HeatExchanger: "#ea580c", PressureTransmitter: "#0d9488", Controller: "#dc2626",
          Unknown: "#64748b",
        };
    return {
      bg: css("--canvas-bg", dark ? "#0e1421" : "#ffffff"),
      grid: css("--canvas-grid", dark ? "#1a2233" : "#eef1f5"),
      label: css("--canvas-label", dark ? "#e6ebf2" : "#1b2330"),
      typeColor: (t: string) => TYPE[t] ?? TYPE.Unknown,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);
}
