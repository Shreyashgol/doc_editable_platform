import { beforeEach, describe, expect, it } from "vitest";
import { useAuth } from "./auth";

describe("auth store", () => {
  beforeEach(() => useAuth.getState().clear());

  it("stores and clears tokens", () => {
    useAuth.getState().setTokens("access-1", "refresh-1");
    expect(useAuth.getState().accessToken).toBe("access-1");
    expect(useAuth.getState().refreshToken).toBe("refresh-1");
    useAuth.getState().clear();
    expect(useAuth.getState().accessToken).toBeNull();
  });
});
