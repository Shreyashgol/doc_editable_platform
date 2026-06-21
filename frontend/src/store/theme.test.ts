import { beforeEach, describe, expect, it } from "vitest";
import { resolveTheme, useTheme } from "./theme";

describe("theme store", () => {
  beforeEach(() => useTheme.getState().setMode("light"));

  it("resolves explicit modes", () => {
    expect(resolveTheme("light")).toBe("light");
    expect(resolveTheme("dark")).toBe("dark");
  });

  it("applies data-theme to <html>", () => {
    useTheme.getState().setMode("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("cycles light → dark → system → light", () => {
    useTheme.getState().setMode("light");
    useTheme.getState().cycle();
    expect(useTheme.getState().mode).toBe("dark");
    useTheme.getState().cycle();
    expect(useTheme.getState().mode).toBe("system");
    useTheme.getState().cycle();
    expect(useTheme.getState().mode).toBe("light");
  });
});
