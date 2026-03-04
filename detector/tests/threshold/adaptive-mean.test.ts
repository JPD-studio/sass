import { describe, it, expect } from "@jest/globals";
import { AdaptiveMeanThreshold } from "../../src/threshold/adaptive-mean.js";

describe("AdaptiveMeanThreshold", () => {
  it("delta > bgMean * 2.0 のとき true（デフォルト multiplier）", () => {
    const t = new AdaptiveMeanThreshold();
    expect(t.isIntrusion(11, 5, 0)).toBe(true); // 11 > 5*2=10
  });

  it("delta === bgMean * 2.0 のとき false", () => {
    const t = new AdaptiveMeanThreshold();
    expect(t.isIntrusion(10, 5, 0)).toBe(false); // 10 > 10 is false
  });

  it("multiplier を変更できる", () => {
    const t = new AdaptiveMeanThreshold(3.0);
    expect(t.isIntrusion(16, 5, 0)).toBe(true);  // 16 > 15
    expect(t.isIntrusion(15, 5, 0)).toBe(false); // 15 > 15 is false
  });

  it("bgMean=0 のとき delta>0 以外は false", () => {
    const t = new AdaptiveMeanThreshold();
    expect(t.isIntrusion(0, 0, 0)).toBe(false);
    expect(t.isIntrusion(-1, 0, 0)).toBe(false);
  });
});
