import { useTheme } from "@/store/theme";

const ICON: Record<string, string> = { light: "☀️", dark: "🌙", system: "🖥️" };
const LABEL: Record<string, string> = { light: "Light", dark: "Dark", system: "System" };

export function ThemeToggle() {
  const { mode, cycle } = useTheme();
  return (
    <button
      className="btn btn--ghost btn--icon"
      onClick={cycle}
      title={`Theme: ${LABEL[mode]} (click to change)`}
      aria-label={`Theme: ${LABEL[mode]}`}
    >
      {ICON[mode]}
    </button>
  );
}
