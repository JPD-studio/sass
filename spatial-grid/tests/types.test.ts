import { describe, test, expect } from "@jest/globals";
import { DEFAULT_MOUNT } from "../src/types.js";

describe("DEFAULT_MOUNT", () => {
  test("デフォルト値が正しく設定されている", () => {
    expect(DEFAULT_MOUNT.position.lat).toBe(0);
    expect(DEFAULT_MOUNT.position.lng).toBe(0);
    expect(DEFAULT_MOUNT.position.alt).toBe(0);
    expect(DEFAULT_MOUNT.orientation.heading).toBe(0);
    expect(DEFAULT_MOUNT.orientation.pitch).toBe(0);
    expect(DEFAULT_MOUNT.orientation.roll).toBe(0);
    expect(DEFAULT_MOUNT.mounting_type).toBe("pole_mounted");
  });
});
