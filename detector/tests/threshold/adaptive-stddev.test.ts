import { describe, it, expect } from "@jest/globals";
import { AdaptiveStddevThreshold } from "../../src/threshold/adaptive-stddev.js";

describe("AdaptiveStddevThreshold", () => {
  it("delta > sigma * bgStddev のとき true", () => {
    const t = new AdaptiveStddevThreshold(2.0);
    expect(t.isIntrusion(11, 0, 5)).toBe(true); // 11 > 2*5=10
  });

  it("delta === sigma * bgStddev のとき false", () => {
    const t = new AdaptiveStddevThreshold(2.0);
    expect(t.isIntrusion(10, 0, 5)).toBe(false);
  });

  it("bgStddev=0 のとき delta>0 なら true", () => {
    const t = new AdaptiveStddevThreshold(2.0);
    expect(t.isIntrusion(1, 0, 0)).toBe(true);
    expect(t.isIntrusion(0, 0, 0)).toBe(false);
    expect(t.isIntrusion(-1, 0, 0)).toBe(false);
  });

  it("sigma を変更できる", () => {
    const t = new AdaptiveStddevThreshold(3.0);
    expect(t.isIntrusion(31, 0, 10)).toBe(true);  // 31 > 30
    expect(t.isIntrusion(30, 0, 10)).toBe(false); // 30 > 30 is false
  });
});
