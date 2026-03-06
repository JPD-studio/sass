import { describe, it, expect } from "@jest/globals";
import { StaticThreshold } from "../../src/threshold/static-threshold.js";

describe("StaticThreshold", () => {
  it("delta > threshold のとき true", () => {
    const t = new StaticThreshold(5);
    expect(t.isIntrusion(6, 0, 0)).toBe(true);
  });

  it("delta === threshold のとき false", () => {
    const t = new StaticThreshold(5);
    expect(t.isIntrusion(5, 0, 0)).toBe(false);
  });

  it("delta < threshold のとき false", () => {
    const t = new StaticThreshold(5);
    expect(t.isIntrusion(3, 0, 0)).toBe(false);
  });

  it("bgMean / bgStddev は無視される", () => {
    const t = new StaticThreshold(10);
    expect(t.isIntrusion(11, 999, 999)).toBe(true);
    expect(t.isIntrusion(9, 999, 999)).toBe(false);
  });
});
