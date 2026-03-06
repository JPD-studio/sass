import { describe, it, expect } from "@jest/globals";
import { IntrusionDetector } from "../src/intrusion-detector.js";
import { StaticThreshold } from "../src/threshold/static-threshold.js";
import { AdaptiveStddevThreshold } from "../src/threshold/adaptive-stddev.js";
import type { VoxelDiffEntry } from "../../voxel/src/types.js";

function makeDiff(key: string, delta: number, bgMean = 0): VoxelDiffEntry {
  return { key, delta, currentCount: delta, backgroundMean: bgMean };
}

describe("IntrusionDetector", () => {
  it("インスタンスを生成できる", () => {
    const d = new IntrusionDetector(new StaticThreshold(5));
    expect(d).toBeDefined();
  });

  it("閾値を超える diff は IntrusionEvent として返る", () => {
    const d = new IntrusionDetector(new StaticThreshold(5));
    const events = d.evaluate([makeDiff("0:0:0", 10)]);
    expect(events.length).toBe(1);
    expect(events[0].key).toBe("0:0:0");
    expect(events[0].delta).toBe(10);
    expect(typeof events[0].timestamp).toBe("number");
  });

  it("閾値以下の diff は返らない", () => {
    const d = new IntrusionDetector(new StaticThreshold(5));
    const events = d.evaluate([makeDiff("0:0:0", 3)]);
    expect(events.length).toBe(0);
  });

  it("複数 diff のうち条件を満たすもののみ返す", () => {
    const d = new IntrusionDetector(new StaticThreshold(5));
    const events = d.evaluate([
      makeDiff("0:0:0", 10),
      makeDiff("1:1:1", 2),
      makeDiff("2:2:2", 8),
    ]);
    expect(events.length).toBe(2);
    expect(events.map((e) => e.key)).toContain("0:0:0");
    expect(events.map((e) => e.key)).toContain("2:2:2");
  });

  it("空の diffs は空配列を返す", () => {
    const d = new IntrusionDetector(new StaticThreshold(5));
    expect(d.evaluate([])).toEqual([]);
  });

  it("setStrategy でストラテジーを切り替えられる", () => {
    const d = new IntrusionDetector(new StaticThreshold(100));
    // 最初は全てスルー
    expect(d.evaluate([makeDiff("0:0:0", 10)]).length).toBe(0);
    // ストラテジー変更
    d.setStrategy(new AdaptiveStddevThreshold(2.0));
    // bgStddev=0 なので delta>0 なら全部検知
    const events = d.evaluate([makeDiff("0:0:0", 1)]);
    expect(events.length).toBe(1);
  });
});
