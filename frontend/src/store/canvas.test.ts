import { beforeEach, describe, expect, it } from "vitest";
import { useCanvas } from "./canvas";

describe("canvas store", () => {
  beforeEach(() => useCanvas.getState().clearSelection());

  it("toggles selection and supports additive multi-select", () => {
    useCanvas.getState().select("a");
    expect(useCanvas.getState().selectedIds.has("a")).toBe(true);
    useCanvas.getState().select("b", true); // additive
    expect(useCanvas.getState().selectedIds.size).toBe(2);
    useCanvas.getState().select("a", true); // toggle off
    expect(useCanvas.getState().selectedIds.has("a")).toBe(false);
  });

  it("clamps zoom scale", () => {
    useCanvas.getState().setScale(100);
    expect(useCanvas.getState().scale).toBeLessThanOrEqual(8);
    useCanvas.getState().setScale(0.001);
    expect(useCanvas.getState().scale).toBeGreaterThanOrEqual(0.1);
  });
});
